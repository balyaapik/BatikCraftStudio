"""Domain-specific exceptions for BatikCraft projects."""

from __future__ import annotations


class ProjectDomainError(Exception):
    """Base exception for project-domain failures."""


class ProjectValidationError(ProjectDomainError, ValueError):
    """Raised when one or more project invariants are violated."""

    def __init__(self, issues: str | tuple[str, ...] | list[str]) -> None:
        normalized = (issues,) if isinstance(issues, str) else tuple(issues)
        if not normalized:
            normalized = ("Project validation failed.",)
        self.issues = normalized
        super().__init__("; ".join(normalized))


class LayerNotFoundError(ProjectDomainError, LookupError):
    """Raised when a layer ID does not exist in a project."""


class DuplicateLayerError(ProjectDomainError, ValueError):
    """Raised when a project receives a layer with an existing ID."""


class ObjectNotFoundError(ProjectDomainError, LookupError):
    """Raised when an object ID does not exist in a project."""


class DuplicateObjectError(ProjectDomainError, ValueError):
    """Raised when a project receives an object with an existing ID."""
