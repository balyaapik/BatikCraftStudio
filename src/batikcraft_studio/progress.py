"""Thread-safe progress primitives shared by desktop long-running tasks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProgressUpdate:
    """One persistence-free status update emitted by a background operation."""

    stage: str
    message: str
    completed: float | None = None
    total: float | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        stage = str(self.stage).strip() or "working"
        message = str(self.message).strip() or "Sedang memproses…"
        completed = self.completed
        total = self.total
        if completed is not None:
            completed = max(0.0, float(completed))
        if total is not None:
            total = max(0.0, float(total))
        if completed is not None and total is not None and total > 0:
            completed = min(completed, total)
        object.__setattr__(self, "stage", stage)
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "completed", completed)
        object.__setattr__(self, "total", total)
        object.__setattr__(self, "detail", str(self.detail).strip())

    @property
    def determinate(self) -> bool:
        """Return True when this update has a usable numerator and denominator."""

        return self.completed is not None and self.total is not None and self.total > 0

    @property
    def fraction(self) -> float | None:
        """Return a clamped 0..1 fraction, or None for indeterminate work."""

        if not self.determinate:
            return None
        return min(1.0, max(0.0, float(self.completed) / float(self.total)))

    @property
    def percent(self) -> int | None:
        """Return an integer percentage suitable for compact UI labels."""

        fraction = self.fraction
        return None if fraction is None else round(fraction * 100)


class OperationCancelledError(RuntimeError):
    """Raised when a cooperative background operation observes cancellation."""


ProgressCallback = Callable[[ProgressUpdate], object]
CancelCheck = Callable[[], bool]


def report_progress(
    callback: ProgressCallback | None,
    stage: str,
    message: str,
    completed: float | None = None,
    total: float | None = None,
    *,
    detail: str = "",
) -> None:
    """Emit an update only when a consumer is present."""

    if callback is not None:
        callback(
            ProgressUpdate(
                stage=stage,
                message=message,
                completed=completed,
                total=total,
                detail=detail,
            )
        )


def ensure_not_cancelled(cancelled: CancelCheck | None) -> None:
    """Raise a normalized cancellation exception when requested by the UI."""

    if cancelled is not None and cancelled():
        raise OperationCancelledError("Proses dibatalkan oleh pengguna.")


def format_byte_progress(completed: int, total: int | None = None) -> str:
    """Format downloaded or written bytes for a human-readable progress detail."""

    left = _format_bytes(max(0, int(completed)))
    if total is None or total <= 0:
        return left
    return f"{left} / {_format_bytes(int(total))}"


def _format_bytes(value: int) -> str:
    number = float(value)
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if number < 1024.0 or unit == units[-1]:
            return f"{number:.0f} {unit}" if unit == "B" else f"{number:.1f} {unit}"
        number /= 1024.0
    return f"{number:.1f} TB"


__all__ = [
    "CancelCheck",
    "OperationCancelledError",
    "ProgressCallback",
    "ProgressUpdate",
    "ensure_not_cancelled",
    "format_byte_progress",
    "report_progress",
]
