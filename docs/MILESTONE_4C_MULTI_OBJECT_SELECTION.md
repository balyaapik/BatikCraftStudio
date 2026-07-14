# Milestone 4C — Multi-Object Selection and Grouping

Milestone 4C improves manual composition editing before paired AI training begins. It does not
require a trained LoRA.

## Canvas selection

Use the Select tool, then drag from an empty canvas area to draw a marquee rectangle.

- every visible object intersecting the rectangle is selected;
- dragging a new rectangle replaces the previous selection;
- hold **Shift** while dragging to add objects to the current selection;
- press **Escape** to cancel an active marquee.

Every selected object receives an individual outline. The overall selection receives a second
bounding rectangle and an object-count label.

## Shift selection

With the Select tool active:

- click an object to select it;
- Shift-click another object to add it;
- Shift-click an already selected object to remove it;
- clicking a member of a saved group selects the complete group;
- Shift-clicking a grouped member adds or removes the complete group.

The last selected object remains the primary object for the Layer Tree, transform fields, color
palette, copy, and Batification commands.

## Moving several objects

Drag any member of a multi-selection to move every selected object by the same delta.

- the relative spacing is preserved;
- locked objects prevent the collective move;
- live preview is rendered on the canvas;
- one drag creates one Undo entry;
- Escape restores every original position.

Single-object resize, rotation, shear, and corner handles keep their existing behavior. Multi-object
resize and rotation are intentionally deferred so this milestone does not destabilize the precise
single-object transform engine.

## Group and ungroup

Commands are available under Edit:

```text
Ctrl+G        Group Objects
Ctrl+Shift+G  Ungroup Objects
```

A group requires at least two selected objects. Group membership is stored using existing object
properties:

```text
object_group_id
object_group_name
```

No project schema bump is required. Groups survive Save and Reopen, and Group/Ungroup are each one
Undo transaction.

Objects can belong to different regular layers. Grouping does not move them between layers, so the
existing render order and Batification source links remain unchanged.

## Clipboard behavior

Copying one object from a group and pasting it creates an independent object. The pasted object does
not inherit `object_group_id` or `object_group_name`, preventing accidental membership in the
original group.

## Interaction with offline AI

Multi-selection does not require an AI model. The existing rectangle AI selection remains available
through `Ctrl+Alt+S` and has priority while active.

A future composition Batification milestone can use `selected_object_ids` as the explicit list of
source components while still returning one editable result per source object.
