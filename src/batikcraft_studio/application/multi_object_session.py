"""Transient multi-selection and persistent object grouping services."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from batikcraft_studio.domain import LayerObject, ObjectNotFoundError, Transform
from batikcraft_studio.imaging import transformed_object_bounds

from .offline_ai_session import OfflineAIProjectSession
from .session import HISTORY_LIMIT, ProjectSessionError, _SessionState

GROUP_ID_KEY = "object_group_id"
GROUP_NAME_KEY = "object_group_name"


@dataclass(frozen=True, slots=True)
class MultiObjectSelection:
    """Current transient editor selection."""

    object_ids: tuple[str, ...]
    primary_object_id: str | None


class MultiObjectProjectSession(OfflineAIProjectSession):
    """Add multi-object selection, grouping, and one-step collective movement."""

    def __init__(self, model_root: Path | str | None = None) -> None:
        super().__init__(model_root)
        self._selected_object_ids: list[str] = []
        self._multi_move_before: _SessionState | None = None
        self._multi_move_originals: dict[str, Transform] = {}

    @property
    def selected_object_ids(self) -> tuple[str, ...]:
        self._prune_selection()
        return tuple(self._selected_object_ids)

    @property
    def selection(self) -> MultiObjectSelection:
        ids = self.selected_object_ids
        return MultiObjectSelection(
            object_ids=ids,
            primary_object_id=ids[-1] if ids else None,
        )

    @property
    def selected_objects(self) -> tuple[LayerObject, ...]:
        project = self.project
        if project is None:
            return ()
        return tuple(
            project.get_object(object_id)
            for object_id in self.selected_object_ids
        )

    @property
    def multi_move_active(self) -> bool:
        return self._multi_move_before is not None

    def set_selected_objects(
        self,
        object_ids: tuple[str, ...] | list[str],
        *,
        expand_groups: bool = False,
    ) -> tuple[LayerObject, ...]:
        project = self.require_project()
        normalized: list[str] = []
        for object_id in object_ids:
            item = project.get_object(str(object_id))
            group_id = item.properties.get(GROUP_ID_KEY)
            targets = (
                self._group_member_ids(group_id)
                if expand_groups and isinstance(group_id, str) and group_id
                else (item.object_id,)
            )
            for target in targets:
                if target not in normalized:
                    normalized.append(target)
        self._selected_object_ids = normalized
        project.set_active_object(normalized[-1] if normalized else None)
        return self.selected_objects

    def select_object_for_editing(
        self,
        object_id: str,
        *,
        extend: bool = False,
        toggle: bool = False,
        include_group: bool = True,
    ) -> tuple[LayerObject, ...]:
        project = self.require_project()
        item = project.get_object(object_id)
        group_id = item.properties.get(GROUP_ID_KEY)
        targets = (
            list(self._group_member_ids(group_id))
            if include_group and isinstance(group_id, str) and group_id
            else [item.object_id]
        )
        current = list(self.selected_object_ids)
        if toggle:
            if all(target in current for target in targets):
                current = [value for value in current if value not in targets]
            else:
                current.extend(value for value in targets if value not in current)
        elif extend:
            current.extend(value for value in targets if value not in current)
        else:
            current = targets
        return self.set_selected_objects(current)

    def clear_object_selection(self) -> None:
        project = self.project
        self._selected_object_ids = []
        if project is not None:
            project.set_active_object(None)

    def select_objects_in_rectangle(
        self,
        bounds: tuple[float, float, float, float],
        *,
        extend: bool = False,
        include_groups: bool = True,
        fully_contained: bool = False,
    ) -> tuple[LayerObject, ...]:
        project = self.require_project()
        left, top, right, bottom = _normalized_bounds(bounds)
        hits: list[str] = []
        for layer in project.layers:
            if not project.is_layer_effectively_visible(layer.layer_id):
                continue
            for item in layer.objects:
                if not item.visible:
                    continue
                item_left, item_top, item_right, item_bottom = transformed_object_bounds(item)
                selected = (
                    left <= item_left
                    and top <= item_top
                    and item_right <= right
                    and item_bottom <= bottom
                    if fully_contained
                    else not (
                        item_right < left
                        or item_left > right
                        or item_bottom < top
                        or item_top > bottom
                    )
                )
                if selected:
                    hits.append(item.object_id)
        current = list(self.selected_object_ids) if extend else []
        current.extend(object_id for object_id in hits if object_id not in current)
        return self.set_selected_objects(current, expand_groups=include_groups)

    def group_selected_objects(self, name: str | None = None) -> str:
        project = self.require_project()
        selected = self._expand_existing_groups(self.selected_object_ids)
        if len(selected) < 2:
            raise ProjectSessionError("Pilih minimal dua objek untuk membuat grup.")
        group_id = str(uuid4())
        group_name = str(name).strip() if name is not None else ""
        if not group_name:
            existing = {
                str(item.properties.get(GROUP_ID_KEY))
                for layer in project.layers
                for item in layer.objects
                if item.properties.get(GROUP_ID_KEY)
            }
            group_name = f"Grup Objek {len(existing) + 1}"

        def mutation() -> None:
            for object_id in selected:
                item = project.get_object(object_id)
                properties = dict(item.properties)
                properties[GROUP_ID_KEY] = group_id
                properties[GROUP_NAME_KEY] = group_name
                project.update_object(object_id, properties=properties)

        self._commit_mutation(mutation)
        self.set_selected_objects(list(selected))
        return group_id

    def ungroup_selected_objects(self) -> tuple[str, ...]:
        project = self.require_project()
        group_ids = {
            str(item.properties.get(GROUP_ID_KEY))
            for item in self.selected_objects
            if item.properties.get(GROUP_ID_KEY)
        }
        if not group_ids:
            raise ProjectSessionError("Seleksi tidak memiliki grup yang dapat dilepas.")
        targets = tuple(
            item.object_id
            for layer in project.layers
            for item in layer.objects
            if item.properties.get(GROUP_ID_KEY) in group_ids
        )

        def mutation() -> None:
            for object_id in targets:
                item = project.get_object(object_id)
                properties = {
                    key: value
                    for key, value in item.properties.items()
                    if key not in {GROUP_ID_KEY, GROUP_NAME_KEY}
                }
                project.update_object(object_id, properties=properties)

        self._commit_mutation(mutation)
        self.set_selected_objects(list(targets))
        return tuple(sorted(group_ids))

    def selection_bounds(self) -> tuple[float, float, float, float] | None:
        items = self.selected_objects
        if not items:
            return None
        bounds = [transformed_object_bounds(item) for item in items]
        return (
            min(value[0] for value in bounds),
            min(value[1] for value in bounds),
            max(value[2] for value in bounds),
            max(value[3] for value in bounds),
        )

    def begin_interactive_multi_move(
        self,
        object_ids: tuple[str, ...] | list[str] | None = None,
    ) -> tuple[LayerObject, ...]:
        if self.interactive_transform_active:
            self.cancel_interactive_object_transform()
        if self._multi_move_before is not None:
            self.cancel_interactive_multi_move()
        ids = tuple(object_ids) if object_ids is not None else self.selected_object_ids
        if not ids:
            raise ProjectSessionError("Tidak ada objek yang dipilih.")
        project = self.require_project()
        originals: dict[str, Transform] = {}
        for object_id in ids:
            item = self._require_unlocked_object(object_id)
            originals[item.object_id] = item.transform
        self._multi_move_before = self._capture_state()
        self._multi_move_originals = originals
        self.set_selected_objects(list(originals))
        return tuple(project.get_object(object_id) for object_id in originals)

    def preview_interactive_multi_move(
        self,
        delta_x: float,
        delta_y: float,
    ) -> tuple[LayerObject, ...]:
        if self._multi_move_before is None:
            raise ProjectSessionError("Pemindahan multi-objek belum dimulai.")
        project = self.require_project()
        updated: list[LayerObject] = []
        for object_id, original in self._multi_move_originals.items():
            self._require_unlocked_object(object_id)
            updated.append(
                project.update_object(
                    object_id,
                    transform=replace(
                        original,
                        x=original.x + float(delta_x),
                        y=original.y + float(delta_y),
                    ),
                )
            )
        return tuple(updated)

    def commit_interactive_multi_move(self) -> bool:
        before = self._multi_move_before
        if before is None:
            return False
        changed = before.project is not None and self._project is not None and (
            before.project.revision != self._project.revision
        )
        if changed:
            self._undo_stack.append(before)
            if len(self._undo_stack) > HISTORY_LIMIT:
                del self._undo_stack[0]
            self._redo_stack.clear()
        self._multi_move_before = None
        self._multi_move_originals = {}
        return changed

    def cancel_interactive_multi_move(self) -> bool:
        before = self._multi_move_before
        if before is None:
            return False
        self._restore_state(before)
        self._multi_move_before = None
        self._multi_move_originals = {}
        self._prune_selection()
        return True

    def undo(self) -> bool:
        changed = super().undo()
        self._prune_selection()
        return changed

    def redo(self) -> bool:
        changed = super().redo()
        self._prune_selection()
        return changed

    def _expand_existing_groups(self, object_ids: tuple[str, ...]) -> tuple[str, ...]:
        project = self.require_project()
        result: list[str] = []
        for object_id in object_ids:
            item = project.get_object(object_id)
            group_id = item.properties.get(GROUP_ID_KEY)
            targets = (
                self._group_member_ids(group_id)
                if isinstance(group_id, str) and group_id
                else (object_id,)
            )
            for target in targets:
                if target not in result:
                    result.append(target)
        return tuple(result)

    def _group_member_ids(self, group_id: object) -> tuple[str, ...]:
        if not isinstance(group_id, str) or not group_id:
            return ()
        project = self.require_project()
        return tuple(
            item.object_id
            for layer in project.layers
            for item in layer.objects
            if item.properties.get(GROUP_ID_KEY) == group_id
        )

    def _prune_selection(self) -> None:
        project = self.project
        if project is None:
            self._selected_object_ids = []
            return
        valid: list[str] = []
        for object_id in self._selected_object_ids:
            try:
                project.get_object(object_id)
            except ObjectNotFoundError:
                continue
            valid.append(object_id)
        self._selected_object_ids = valid
        if valid:
            project.set_active_object(valid[-1])
        elif project.active_object_id is not None:
            self._selected_object_ids = [project.active_object_id]


def _normalized_bounds(
    bounds: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = (float(value) for value in bounds)
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


__all__ = [
    "GROUP_ID_KEY",
    "GROUP_NAME_KEY",
    "MultiObjectProjectSession",
    "MultiObjectSelection",
]
