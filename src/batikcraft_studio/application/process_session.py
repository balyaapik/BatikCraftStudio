"""Persist Batik production plans and export workshop-ready process packets."""

from __future__ import annotations

import csv
import json
import zipfile
from dataclasses import replace
from io import StringIO
from pathlib import Path

from batikcraft_studio.domain import Layer, LayerKind, LayerNodeKind
from batikcraft_studio.domain.batik_process import BatikProcessPlan, ProcessStep

from .multi_object_session import GROUP_ID_KEY, MultiObjectProjectSession
from .session import ProjectSessionError

BATIK_PROCESS_EXTENSION = ".batikprocess"
_PROCESS_ROLE_KEY = "internal_role"
_PROCESS_ROLE_VALUE = "batik_process_plan"
_PROCESS_PLAN_KEY = "batik_process_plan"
_INTERNAL_HIDDEN_KEY = "internal_hidden"


class BatikProcessProjectSession(MultiObjectProjectSession):
    """Store a process plan inside a non-rendering internal project group."""

    @property
    def process_plan(self) -> BatikProcessPlan:
        layer = self._process_layer()
        if layer is None:
            return BatikProcessPlan()
        raw = layer.properties.get(_PROCESS_PLAN_KEY)
        if raw is None:
            return BatikProcessPlan()
        try:
            return BatikProcessPlan.from_dict(raw)
        except Exception as exc:
            raise ProjectSessionError(f"Data proses batik pada project tidak valid: {exc}") from exc

    def set_process_plan(self, plan: BatikProcessPlan) -> BatikProcessPlan:
        if not isinstance(plan, BatikProcessPlan):
            raise ProjectSessionError("Process plan tidak valid.")
        project = self.require_project()
        existing = self._process_layer()
        properties = {
            _PROCESS_ROLE_KEY: _PROCESS_ROLE_VALUE,
            _INTERNAL_HIDDEN_KEY: True,
            _PROCESS_PLAN_KEY: plan.to_dict(),
        }

        def mutation() -> None:
            if existing is None:
                project.add_layer(
                    Layer(
                        name="Batik Process Data",
                        kind=LayerKind.GROUP,
                        node_kind=LayerNodeKind.GROUP,
                        visible=False,
                        locked=True,
                        properties=properties,
                    ),
                    select=False,
                )
            else:
                project.update_layer(existing.layer_id, properties=properties)

        self._commit_mutation(mutation)
        return plan

    def assign_selected_objects_to_step(self, step_id: str) -> ProcessStep:
        plan = self.process_plan
        selected = self.selected_objects
        if not selected:
            raise ProjectSessionError("Pilih minimal satu objek sebelum menghubungkannya ke tahap.")
        group_ids = tuple(
            dict.fromkeys(
                str(item.properties[GROUP_ID_KEY])
                for item in selected
                if item.properties.get(GROUP_ID_KEY)
            )
        )
        replacement: ProcessStep | None = None
        steps: list[ProcessStep] = []
        for step in plan.steps:
            if step.step_id == step_id:
                replacement = replace(
                    step,
                    object_ids=tuple(item.object_id for item in selected),
                    group_ids=group_ids,
                )
                steps.append(replacement)
            else:
                steps.append(step)
        if replacement is None:
            raise ProjectSessionError("Tahap proses yang dipilih tidak ditemukan.")
        self.set_process_plan(replace(plan, steps=tuple(steps)))
        return replacement

    def export_process_package(
        self,
        destination: Path | str,
        *,
        plan: BatikProcessPlan | None = None,
    ) -> Path:
        active_plan = plan or self.process_plan
        output = Path(destination)
        if output.suffix.casefold() != BATIK_PROCESS_EXTENSION:
            output = output.with_suffix(BATIK_PROCESS_EXTENSION)
        output.parent.mkdir(parents=True, exist_ok=True)
        project = self.require_project()
        object_names = {
            item.object_id: item.name
            for layer in project.layers
            for item in layer.objects
        }
        source_names = {source.source_id: source.name for source in active_plan.dye_sources}
        recipe_names = {recipe.recipe_id: recipe.name for recipe in active_plan.color_recipes}
        files = {
            "process.json": json.dumps(
                active_plan.to_dict(), ensure_ascii=False, indent=2, sort_keys=True
            ),
            "dye-sources.csv": _dye_sources_csv(active_plan),
            "color-recipes.csv": _color_recipes_csv(active_plan, source_names),
            "steps.csv": _steps_csv(active_plan, recipe_names, object_names),
            "README.md": _readme(active_plan, recipe_names, source_names, object_names),
        }
        temporary = output.with_name(f".{output.name}.tmp")
        try:
            with zipfile.ZipFile(
                temporary,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
            ) as archive:
                for name, content in files.items():
                    archive.writestr(name, content.encode("utf-8"))
            temporary.replace(output)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return output

    def _process_layer(self) -> Layer | None:
        project = self.project
        if project is None:
            return None
        return next(
            (
                layer
                for layer in project.layers
                if layer.properties.get(_PROCESS_ROLE_KEY) == _PROCESS_ROLE_VALUE
            ),
            None,
        )


def _csv_text(rows: list[list[object]]) -> str:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerows(rows)
    return output.getvalue()


def _dye_sources_csv(plan: BatikProcessPlan) -> str:
    rows: list[list[object]] = [
        ["id", "name", "kind", "material", "plant_part", "origin", "notes"]
    ]
    rows.extend(
        [
            source.source_id,
            source.name,
            source.kind.value,
            source.material,
            source.plant_part,
            source.origin,
            source.notes,
        ]
        for source in plan.dye_sources
    )
    return _csv_text(rows)


def _color_recipes_csv(plan: BatikProcessPlan, source_names: dict[str, str]) -> str:
    rows: list[list[object]] = [
        [
            "id",
            "name",
            "hex_color",
            "dye_sources",
            "mordant",
            "ratio",
            "bath_temperature_celsius",
            "notes",
        ]
    ]
    rows.extend(
        [
            recipe.recipe_id,
            recipe.name,
            recipe.hex_color,
            " | ".join(source_names.get(value, value) for value in recipe.source_ids),
            recipe.mordant,
            recipe.ratio,
            "" if recipe.bath_temperature_celsius is None else recipe.bath_temperature_celsius,
            recipe.notes,
        ]
        for recipe in plan.color_recipes
    )
    return _csv_text(rows)


def _steps_csv(
    plan: BatikProcessPlan,
    recipe_names: dict[str, str],
    object_names: dict[str, str],
) -> str:
    rows: list[list[object]] = [
        [
            "order",
            "id",
            "name",
            "action",
            "color_recipe",
            "duration_minutes",
            "objects",
            "group_ids",
            "notes",
        ]
    ]
    rows.extend(
        [
            index,
            step.step_id,
            step.name,
            step.action.value,
            recipe_names.get(step.recipe_id or "", ""),
            "" if step.duration_minutes is None else step.duration_minutes,
            " | ".join(object_names.get(value, value) for value in step.object_ids),
            " | ".join(step.group_ids),
            step.notes,
        ]
        for index, step in enumerate(plan.steps, start=1)
    )
    return _csv_text(rows)


def _readme(
    plan: BatikProcessPlan,
    recipe_names: dict[str, str],
    source_names: dict[str, str],
    object_names: dict[str, str],
) -> str:
    lines = [
        f"# {plan.title}",
        "",
        f"- Kain: {plan.fabric}",
        f"- Teknik: {plan.technique}",
        "",
        plan.notes or "Belum ada catatan umum.",
        "",
        "## Urutan proses",
        "",
    ]
    if not plan.steps:
        lines.append("Belum ada tahap proses.")
    for index, step in enumerate(plan.steps, start=1):
        lines.extend(
            [
                f"### {index}. {step.name}",
                f"- Aksi: `{step.action.value}`",
                f"- Resep warna: {recipe_names.get(step.recipe_id or '', '—')}",
                f"- Durasi: {step.duration_minutes if step.duration_minutes is not None else '—'} menit",
                "- Objek: "
                + (
                    ", ".join(object_names.get(value, value) for value in step.object_ids)
                    or "—"
                ),
                f"- Catatan: {step.notes or '—'}",
                "",
            ]
        )
    lines.extend(["## Sumber pewarna", ""])
    if not plan.dye_sources:
        lines.append("Belum ada sumber pewarna.")
    for source in plan.dye_sources:
        lines.append(
            f"- **{source.name}** ({source.kind.value}): "
            f"{source.material or 'bahan belum dicatat'}; "
            f"asal {source.origin or 'belum dicatat'}."
        )
    lines.extend(["", "## Resep warna", ""])
    if not plan.color_recipes:
        lines.append("Belum ada resep warna.")
    for recipe in plan.color_recipes:
        sources = ", ".join(source_names.get(value, value) for value in recipe.source_ids) or "—"
        lines.append(
            f"- **{recipe.name}** `{recipe.hex_color}` — sumber: {sources}; "
            f"mordan: {recipe.mordant or '—'}; rasio: {recipe.ratio or '—'}."
        )
    lines.append("")
    lines.append(
        "Paket ini adalah fondasi dokumentasi produksi. Preview visual per tahap akan dibuat "
        "oleh milestone simulasi canting dan pewarnaan berikutnya."
    )
    return "\n".join(lines)


__all__ = [
    "BATIK_PROCESS_EXTENSION",
    "BatikProcessProjectSession",
]
