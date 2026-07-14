# Milestone 4D — Context Grouping and Batik Process Foundations

## Selection correction

Marquee selection and Shift selection only change the current selection. They never create an
object group automatically.

Right-click the canvas after selecting objects to open:

```text
Kelompokkan Objek
Lepaskan Kelompok
Buka Studio Proses Batik
```

Group is enabled for two or more independent selected objects. Ungroup is enabled when the
selection contains at least one saved object group. Existing `Ctrl+G` and `Ctrl+Shift+G` shortcuts
remain available.

## Process data model

A project can now store one `BatikProcessPlan` containing:

- general process title, fabric, technique, and notes;
- dye sources;
- color recipes;
- ordered production steps;
- object and object-group references for each step.

Supported production actions are:

```text
sketch
canting_outline
canting_isen
wax_block
dye_bath
dry
wax_removal
finishing
```

The process plan is stored in a locked non-rendering group node using process schema `1.0`. This
does not change project schema `1.1` and remains compatible with existing `.batikcraft` files.

## Batik Process Studio

Open:

```text
Produksi → Studio Proses Batik…
Ctrl+Alt+P
```

### Dye sources

Record:

- natural, synthetic, or mixed source;
- material or botanical name;
- plant/material part;
- origin;
- notes.

Example:

```text
Name: Daun Indigofera
Kind: natural
Material: Indigofera tinctoria
Part: Daun
Origin: Indonesia
```

### Color recipes

Record:

- display color (`#RRGGBB`);
- dye source;
- mordant or fixative;
- material ratio;
- bath temperature;
- notes.

### Steps

Each step records:

- name and action;
- optional color recipe;
- duration;
- notes;
- selected object IDs;
- selected persistent group IDs.

Use **Gunakan Objek Terpilih** to connect the current canvas selection to the step.

## Process package export

The studio exports:

```text
*.batikprocess
```

The ZIP-compatible package contains:

```text
process.json
steps.csv
color-recipes.csv
dye-sources.csv
README.md
```

This packet is intended for workshop documentation, vendor handoff, teaching, and later visual
simulation. It does not yet generate stage-by-stage PNG previews.

## Next milestone

The next simulation milestone will interpret the saved actions as:

- wax/resist masks for canting and tembokan;
- sequential dye baths;
- protected and exposed regions;
- drying states;
- wax removal/pelorodan;
- one preview image per process step;
- a final PDF/HTML production sheet.
