"""Authenticated bridge between BatikCraft Studio and BatikCraftWeb."""

from __future__ import annotations

import json
import mimetypes
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from batikcraft_studio.config import APP_VERSION
from batikcraft_studio.persistence.nft_package import load_batikcraft_nft

_DEFAULT_WEB_URL = "http://127.0.0.1:8000"
_CONFIG_SCHEMA = 1


class BatikCraftWebError(RuntimeError):
    """Raised when the website rejects or cannot complete a Studio action."""


@dataclass(frozen=True, slots=True)
class WebAccount:
    user_id: int
    username: str
    public_name: str
    email: str
    role: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "WebAccount":
        return cls(
            user_id=int(value["id"]),
            username=str(value["username"]),
            public_name=str(value.get("public_name") or value["username"]),
            email=str(value.get("email") or ""),
            role=str(value.get("role") or ""),
        )


@dataclass(frozen=True, slots=True)
class WebSession:
    base_url: str
    token: str
    account: WebAccount


class WebSessionStore:
    """Persist endpoint and token, preferring the OS credential vault."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else _default_config_path()

    def load_base_url(self) -> str:
        payload = self._load_payload()
        return normalize_base_url(str(payload.get("base_url") or _DEFAULT_WEB_URL))

    def load_token(self) -> str:
        payload = self._load_payload()
        account_name = str(payload.get("token_account") or "default")
        try:
            import keyring

            value = keyring.get_password("BatikCraftStudio.Web", account_name)
            if value:
                return str(value).strip()
        except Exception:
            pass
        return str(payload.get("token") or "").strip()

    def save(self, base_url: str, token: str, username: str) -> None:
        normalized = normalize_base_url(base_url)
        payload = {
            "schema_version": _CONFIG_SCHEMA,
            "base_url": normalized,
            "token_account": username,
        }
        token_stored = False
        try:
            import keyring

            keyring.set_password("BatikCraftStudio.Web", username, token)
            token_stored = True
        except Exception:
            payload["token"] = token
        self._write_payload(payload)
        if token_stored:
            self._remove_plain_token()

    def clear(self) -> None:
        payload = self._load_payload()
        account_name = str(payload.get("token_account") or "default")
        try:
            import keyring

            keyring.delete_password("BatikCraftStudio.Web", account_name)
        except Exception:
            pass
        base_url = normalize_base_url(str(payload.get("base_url") or _DEFAULT_WEB_URL))
        self._write_payload(
            {
                "schema_version": _CONFIG_SCHEMA,
                "base_url": base_url,
                "token_account": "default",
            }
        )

    def _load_payload(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _write_payload(self, payload: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(
            json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def _remove_plain_token(self) -> None:
        payload = self._load_payload()
        if "token" not in payload:
            return
        payload.pop("token", None)
        self._write_payload(payload)


def _slugify(value: str) -> str:
    slug = "".join(ch if ch.isalnum() else "-" for ch in value.casefold()).strip("-")
    return slug[:60] or "motif"


class BatikCraftWebClient:
    """Small urllib client for BatikCraftWeb's token-authenticated REST API."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        timeout: int = 60,
        session_store: WebSessionStore | None = None,
    ) -> None:
        self.session_store = session_store or WebSessionStore()
        self.base_url = normalize_base_url(
            base_url or self.session_store.load_base_url()
        )
        self.token = str(token if token is not None else self.session_store.load_token())
        self.timeout = max(10, int(timeout))

    @property
    def is_authenticated(self) -> bool:
        return bool(self.token)

    def login(self, username: str, password: str) -> WebSession:
        payload = self._request_json(
            "POST",
            "auth/token/",
            payload={"username": username.strip(), "password": password},
            authenticated=False,
        )
        token = str(payload.get("token") or "").strip()
        if not token:
            raise BatikCraftWebError("Website tidak mengembalikan token login.")
        self.token = token
        account = self.me()
        self.session_store.save(self.base_url, token, account.username)
        return WebSession(self.base_url, token, account)

    def restore_session(self) -> WebSession | None:
        if not self.token:
            return None
        try:
            account = self.me()
        except BatikCraftWebError:
            return None
        return WebSession(self.base_url, self.token, account)

    def logout(self) -> None:
        if self.token:
            try:
                self._request_json("POST", "auth/logout/", payload={})
            except BatikCraftWebError:
                pass
        self.token = ""
        self.session_store.clear()

    def me(self) -> WebAccount:
        return WebAccount.from_mapping(self._request_json("GET", "me/"))

    def list_nfts(self) -> list[dict[str, Any]]:
        return _result_list(self._request_json("GET", "nfts/"))

    def nft_bids(self, nft_id: int) -> list[dict[str, Any]]:
        """Riwayat bid satu NFT (kronologis) untuk analisis harga."""

        return _result_list(self._request_json("GET", f"nfts/{int(nft_id)}/bids/"))

    def nft_price_history(self, nft_id: int) -> list[tuple[str, float]]:
        """Deret (waktu, harga) dari riwayat bid, diurutkan berdasarkan waktu."""

        points: list[tuple[str, float]] = []
        for bid in self.nft_bids(nft_id):
            raw_amount = bid.get("amount") or bid.get("price") or 0
            try:
                amount = float(str(raw_amount).replace(",", ""))
            except (TypeError, ValueError):
                continue
            stamp = str(
                bid.get("created_at")
                or bid.get("timestamp")
                or bid.get("created")
                or ""
            )
            points.append((stamp, amount))
        points.sort(key=lambda item: item[0])
        return points

    def place_bid(self, nft_id: int, amount: str) -> dict[str, Any]:
        return self._request_json(
            "POST",
            f"nfts/{int(nft_id)}/bids/",
            payload={"amount": str(amount)},
        )

    def publish_nft_package(
        self,
        package_path: str | Path,
        *,
        starting_price: str,
        auction_ends_at: str = "",
    ) -> dict[str, Any]:
        bundle = load_batikcraft_nft(package_path)
        artwork = dict(bundle.manifest.get("artwork") or {})
        identity = dict(bundle.manifest.get("identity") or {})
        fields: dict[str, str] = {
            "title": str(identity.get("title") or bundle.project.metadata.title),
            "description": str(artwork.get("description") or artwork.get("philosophy") or ""),
            "source_project_id": bundle.project.project_id,
            "source_app_version": APP_VERSION,
            "starting_price": str(starting_price),
            "metadata": json.dumps(
                {
                    "package_id": bundle.package_id,
                    "motifs": artwork.get("motifs", []),
                    "colors": artwork.get("colors", []),
                    "license": artwork.get("license", ""),
                    "canvas": artwork.get("canvas", {}),
                },
                ensure_ascii=False,
            ),
        }
        if auction_ends_at.strip():
            fields["auction_ends_at"] = auction_ends_at.strip()
        item = self._request_multipart(
            "POST",
            "nfts/",
            fields=fields,
            files={
                "image": (
                    f"{bundle.package_id}.jpg",
                    bundle.preview_jpeg,
                    "image/jpeg",
                )
            },
        )
        nft_id = int(item["id"])
        return self._request_json("POST", f"nfts/{nft_id}/publish/", payload={})

    def publish_image_nft(
        self,
        image_png: bytes,
        *,
        title: str,
        description: str = "",
        starting_price: str = "0",
        auction_ends_at: str = "",
    ) -> dict[str, Any]:
        """Publikasikan NFT langsung dari gambar rata (PNG) dokumen raster.

        Berbeda dari publish_nft_package yang butuh paket .batikcraft berbasis
        objek, jalur ini menerima satu gambar rata — sesuai model kanvas raster
        di mana motif berasal dari dokumen penuh, bukan objek per objek.
        """

        clean_title = str(title).strip()
        if not clean_title:
            raise BatikCraftWebError("Judul NFT tidak boleh kosong.")
        if not image_png:
            raise BatikCraftWebError("Gambar NFT kosong.")
        fields: dict[str, str] = {
            "title": clean_title[:200],
            "description": str(description)[:2000],
            "source_app_version": APP_VERSION,
            "starting_price": str(starting_price),
            "metadata": json.dumps(
                {"source": "raster-document", "app_version": APP_VERSION},
                ensure_ascii=False,
            ),
        }
        if auction_ends_at.strip():
            fields["auction_ends_at"] = auction_ends_at.strip()
        item = self._request_multipart(
            "POST",
            "nfts/",
            fields=fields,
            files={"image": (f"{_slugify(clean_title)}.png", image_png, "image/png")},
        )
        nft_id = int(item["id"])
        return self._request_json("POST", f"nfts/{nft_id}/publish/", payload={})

    def list_models(self) -> list[dict[str, Any]]:
        return _result_list(self._request_json("GET", "models/"))

    def purchase_model(self, model_id: int) -> dict[str, Any]:
        return self._request_json(
            "POST",
            f"models/{int(model_id)}/purchase/",
            payload={},
        )

    def model_library(self) -> list[dict[str, Any]]:
        return _result_list(self._request_json("GET", "library/models/"))

    def publish_model_pack(
        self,
        model_path: str | Path,
        *,
        price: str,
        description: str = "",
        category: str = "ornament",
        license_type: str = "personal",
        commercial_use: bool = False,
        preview_path: str | Path | None = None,
    ) -> dict[str, Any]:
        path = Path(model_path)
        metadata = inspect_model_pack(path)
        model = dict(metadata["model"])
        fields = {
            "name": str(model.get("name") or path.stem),
            "description": description.strip()
            or str(model.get("description") or ""),
            "category": category.strip() or "ornament",
            "source_model_id": str(model.get("model_id") or path.stem),
            "source_app_version": APP_VERSION,
            "version": str(model.get("version") or "1.0.0"),
            "base_model_family": str(
                model.get("base_model_family") or "sdxl"
            ),
            "trigger_words": json.dumps(
                model.get("trigger_words") or [],
                ensure_ascii=False,
            ),
            "capabilities": json.dumps(
                model.get("capabilities") or [],
                ensure_ascii=False,
            ),
            "metadata": json.dumps(
                {"pack_format": metadata.get("format", "")},
                ensure_ascii=False,
            ),
            "price": str(price),
            "license_type": license_type,
            "commercial_use": "true" if commercial_use else "false",
        }
        files: dict[str, tuple[str, bytes, str]] = {
            "model_file": (
                path.name,
                path.read_bytes(),
                "application/zip",
            )
        }
        if preview_path:
            preview = Path(preview_path)
            if preview.is_file():
                files["preview"] = (
                    preview.name,
                    preview.read_bytes(),
                    mimetypes.guess_type(preview.name)[0]
                    or "application/octet-stream",
                )
        item = self._request_multipart(
            "POST",
            "models/",
            fields=fields,
            files=files,
        )
        model_id = int(item["id"])
        return self._request_json(
            "POST",
            f"models/{model_id}/publish/",
            payload={},
        )

    def download_model(self, model_id: int, destination: str | Path) -> Path:
        data, headers = self._request_bytes("GET", f"models/{int(model_id)}/download/")
        target = Path(destination)
        if target.is_dir():
            disposition = headers.get("Content-Disposition", "")
            filename = _filename_from_disposition(disposition) or f"model-{model_id}.batikmodel"
            target = target / filename
        if target.suffix.casefold() != ".batikmodel":
            target = target.with_suffix(".batikmodel")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.tmp")
        temporary.write_bytes(data)
        temporary.replace(target)
        return target

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(dict(payload)).encode("utf-8")
            headers["Content-Type"] = "application/json"
        data, _response_headers = self._open(
            method,
            path,
            body=body,
            headers=headers,
            authenticated=authenticated,
        )
        if not data:
            return {}
        try:
            value = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BatikCraftWebError("Respons JSON website tidak valid.") from exc
        if not isinstance(value, dict):
            raise BatikCraftWebError("Respons website harus berupa object JSON.")
        return value

    def _request_multipart(
        self,
        method: str,
        path: str,
        *,
        fields: Mapping[str, str],
        files: Mapping[str, tuple[str, bytes, str]],
    ) -> dict[str, Any]:
        body, content_type = _encode_multipart(fields, files)
        data, _headers = self._open(
            method,
            path,
            body=body,
            headers={
                "Accept": "application/json",
                "Content-Type": content_type,
            },
            authenticated=True,
        )
        try:
            value = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BatikCraftWebError("Respons upload website tidak valid.") from exc
        if not isinstance(value, dict):
            raise BatikCraftWebError("Respons upload harus berupa object JSON.")
        return value

    def _request_bytes(self, method: str, path: str) -> tuple[bytes, Mapping[str, str]]:
        return self._open(
            method,
            path,
            body=None,
            headers={"Accept": "application/octet-stream"},
            authenticated=True,
        )

    def _open(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None,
        headers: Mapping[str, str],
        authenticated: bool,
    ) -> tuple[bytes, Mapping[str, str]]:
        request_headers = dict(headers)
        if authenticated:
            if not self.token:
                raise BatikCraftWebError("Login ke BatikCraftWeb terlebih dahulu.")
            request_headers["Authorization"] = f"Token {self.token}"
        request = urllib.request.Request(
            self._api_url(path),
            data=body,
            method=method.upper(),
            headers=request_headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read(), dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            detail = _http_error_detail(exc)
            if exc.code == 401:
                detail = "Login tidak valid atau sesi sudah berakhir."
            raise BatikCraftWebError(f"Website menolak request ({exc.code}): {detail}") from exc
        except urllib.error.URLError as exc:
            raise BatikCraftWebError(
                f"Tidak dapat terhubung ke {self.base_url}: {exc.reason}"
            ) from exc

    def _api_url(self, path: str) -> str:
        return f"{self.base_url}/api/v1/{path.lstrip('/')}"


def inspect_model_pack(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if source.suffix.casefold() != ".batikmodel" or not source.is_file():
        raise BatikCraftWebError("Pilih file model dengan ekstensi .batikmodel.")
    try:
        with zipfile.ZipFile(source, "r") as archive:
            value = json.loads(archive.read("manifest.json").decode("utf-8"))
    except (OSError, KeyError, UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        raise BatikCraftWebError("Paket .batikmodel rusak atau tidak valid.") from exc
    if not isinstance(value, dict) or not isinstance(value.get("model"), dict):
        raise BatikCraftWebError("Manifest .batikmodel tidak memiliki metadata model.")
    return value


def normalize_base_url(value: str) -> str:
    text = str(value).strip().rstrip("/")
    if not text:
        text = _DEFAULT_WEB_URL
    parsed = urllib.parse.urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise BatikCraftWebError("URL web harus diawali http:// atau https://.")
    suffix = "/api/v1"
    if parsed.path.rstrip("/").endswith(suffix):
        text = text[: -len(suffix)].rstrip("/")
    return text


def _default_config_path() -> Path:
    appdata = os.environ.get("APPDATA")
    root = Path(appdata) if appdata else Path.home() / ".config"
    return root / "BatikCraftStudio" / "web_account.json"


def _result_list(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    value = payload.get("results", payload)
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    raise BatikCraftWebError("Daftar marketplace dari website tidak valid.")


def _encode_multipart(
    fields: Mapping[str, str],
    files: Mapping[str, tuple[str, bytes, str]],
) -> tuple[bytes, str]:
    boundary = f"----BatikCraftStudio{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                ).encode(),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    for name, (filename, content, content_type) in files.items():
        safe_name = Path(filename).name.replace('"', "")
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="{name}"; '
                    f'filename="{safe_name}"\r\n'
                ).encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                bytes(content),
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _http_error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return str(exc.reason)
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if detail:
            return str(detail)
        return "; ".join(f"{key}: {value}" for key, value in payload.items())
    return str(payload)


def _filename_from_disposition(value: str) -> str:
    marker = "filename="
    if marker not in value:
        return ""
    return value.split(marker, 1)[1].strip().strip('"')


__all__ = [
    "BatikCraftWebClient",
    "BatikCraftWebError",
    "WebAccount",
    "WebSession",
    "WebSessionStore",
    "inspect_model_pack",
    "normalize_base_url",
]
