# Milestone 4A — Structured Batification Foundations

Milestone 4A establishes a non-destructive rendering workflow. It does **not** flatten a
composition into one final bitmap.

## Object structure

For each Batification generation, BatikCraft keeps:

```text
Source object (editable, preserved)
├── Batik render v1
├── Isen/filler suggestion v1
├── Batik render v2
└── Isen/filler suggestion v2
```

Only the active generation is visible by default. Older generations remain stored and can be
recovered through Undo or by showing the latest generation after editing the source.

Object relationships are stored in existing object properties:

- `batification_role`: `source`, `render`, or `suggestion`;
- `batification_source_object_id`;
- `batification_generation_id`;
- `batification_version`;
- `batification_provider`;
- `batification_settings`;
- `batification_metadata`.

No project schema bump is required.

## Current provider

The active provider is:

```text
local-structured-foundation-v1
```

It is deterministic and runs offline with Pillow. It proves the complete workflow:

1. select a source object;
2. configure style, strength, isen density, colors, seed, and prompt;
3. create a separate Batik render object;
4. optionally create a separate isen/filler object;
5. edit, move, transform, recolor, hide, or delete each component independently;
6. show the original source;
7. edit the source;
8. render a new version.

This local provider is not presented as the final generative AI model.

## UI workflow

Use the **AI Batik / Batik AI** menu:

- **Batifikasi Objek Terpilih…** — render one source component;
- **Batifikasi Lapis / Folder…** — render every source object under the selected layer or
  folder as one Undo transaction;
- **Render Ulang Komponen** — create the next version using the previous settings and a new
  seed;
- **Tampilkan Sumber Editable** — hide generated components and show the source;
- **Tampilkan Render Terbaru** — hide the source and show the latest generation;
- **Reset Batification…** — remove generated components and return to the source.

Shortcuts:

```text
Ctrl+Alt+B  Batify selected object
Ctrl+Alt+G  Batify selected layer/folder
Ctrl+Alt+R  Re-render selected component
```

Text fields keep their native behavior because global commands are suppressed while a text
control has focus.

## Undo and persistence

- One object generation is one Undo step.
- One layer/folder generation is one Undo step, even when it creates many component objects.
- Reset is one Undo step.
- Source links, settings, versions, and generated PNG assets survive Save and Reopen.
- Existing `.batikcraft` projects remain compatible.

## AI provider contract

A future AI backend implements `StructuredBatificationProvider`:

```python
class StructuredBatificationProvider(Protocol):
    provider_id: str

    def render(
        self,
        source_content: bytes,
        request: BatificationRequest,
    ) -> BatificationRender:
        ...
```

The provider returns:

- one transparent PNG for the Batik-rendered source component;
- dimensions;
- provider metadata;
- optionally one separate transparent filler/isen PNG.

A provider must not return a flattened full-canvas image for object mode.

For group/full-composition AI in a later milestone, the backend should return a list of
component outputs with stable source IDs or masks. The application will then create one
editable object per returned component.

## Next milestone

Milestone 4B should connect a true generative backend while preserving this contract:

- export source PNG, alpha mask, edge map, palette, transform, and role metadata;
- batch objects using one shared style seed for visual consistency;
- accept multiple component outputs;
- create separate AI-added connectors, borders, and isen objects;
- provide asynchronous progress, cancellation, retry, and model configuration;
- support local Kaggle-produced models and an optional remote inference endpoint.
