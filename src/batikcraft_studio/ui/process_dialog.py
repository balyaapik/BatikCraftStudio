"""Editor for Batik production steps, dye sources, and color recipes."""

from __future__ import annotations

import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk

from batikcraft_studio.application import BatikProcessProjectSession, ProjectSessionError
from batikcraft_studio.domain.batik_process import (
    BatikProcessPlan,
    ColorRecipe,
    DyeSource,
    DyeSourceKind,
    ProcessAction,
    ProcessStep,
)
from batikcraft_studio.i18n import tr


class BatikProcessStudioWindow(tk.Toplevel):
    """Edit a project's non-rendering workshop process plan."""

    def __init__(self, parent: tk.Misc, session: BatikProcessProjectSession) -> None:
        super().__init__(parent)
        self.session = session
        self.title(tr("process.title"))
        self.geometry("980x680")
        self.minsize(880, 600)
        self.transient(parent.winfo_toplevel())
        plan = session.process_plan
        self._sources = list(plan.dye_sources)
        self._recipes = list(plan.color_recipes)
        self._steps = list(plan.steps)
        self._step_object_ids: tuple[str, ...] = ()
        self._step_group_ids: tuple[str, ...] = ()

        self.plan_title = tk.StringVar(value=plan.title)
        self.fabric = tk.StringVar(value=plan.fabric)
        self.technique = tk.StringVar(value=plan.technique)

        self.source_name = tk.StringVar()
        self.source_kind = tk.StringVar(value=DyeSourceKind.NATURAL.value)
        self.source_material = tk.StringVar()
        self.source_part = tk.StringVar()
        self.source_origin = tk.StringVar()

        self.recipe_name = tk.StringVar()
        self.recipe_color = tk.StringVar(value="#8A5A3B")
        self.recipe_source = tk.StringVar()
        self.recipe_mordant = tk.StringVar()
        self.recipe_ratio = tk.StringVar()
        self.recipe_temperature = tk.StringVar()

        self.step_name = tk.StringVar()
        self.step_action = tk.StringVar(value=ProcessAction.SKETCH.value)
        self.step_recipe = tk.StringVar()
        self.step_duration = tk.StringVar()
        self.step_selection_label = tk.StringVar(value=tr("process.no_selection"))

        self._build()
        self._refresh_all()

    def _build(self) -> None:
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        general = ttk.LabelFrame(body, text=tr("process.general"), padding=10)
        general.grid(row=0, column=0, sticky="ew")
        general.columnconfigure(1, weight=1)
        general.columnconfigure(3, weight=1)
        self._entry(general, 0, 0, "process.plan_title", self.plan_title)
        self._entry(general, 0, 2, "process.fabric", self.fabric)
        self._entry(general, 1, 0, "process.technique", self.technique)
        ttk.Label(general, text=tr("process.notes")).grid(
            row=2,
            column=0,
            sticky="nw",
            padx=(0, 6),
            pady=4,
        )
        self.plan_notes = tk.Text(general, height=3, wrap="word")
        self.plan_notes.grid(row=2, column=1, columnspan=3, sticky="ew", pady=4)
        self.plan_notes.insert("1.0", self.session.process_plan.notes)

        notebook = ttk.Notebook(body)
        notebook.grid(row=1, column=0, sticky="nsew", pady=(10, 10))
        source_tab = ttk.Frame(notebook, padding=10)
        recipe_tab = ttk.Frame(notebook, padding=10)
        step_tab = ttk.Frame(notebook, padding=10)
        notebook.add(source_tab, text=tr("process.sources"))
        notebook.add(recipe_tab, text=tr("process.recipes"))
        notebook.add(step_tab, text=tr("process.steps"))
        self._build_source_tab(source_tab)
        self._build_recipe_tab(recipe_tab)
        self._build_step_tab(step_tab)

        actions = ttk.Frame(body)
        actions.grid(row=2, column=0, sticky="ew")
        ttk.Button(actions, text=tr("common.close"), command=self.destroy).pack(side="right")
        ttk.Button(actions, text=tr("process.export"), command=self._export).pack(
            side="right",
            padx=(0, 6),
        )
        ttk.Button(actions, text=tr("process.save"), command=self._save).pack(
            side="right",
            padx=(0, 6),
        )

    def _build_source_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)
        self.source_tree = ttk.Treeview(
            parent,
            columns=("kind", "material", "origin"),
            show="tree headings",
            selectmode="browse",
        )
        self.source_tree.heading("#0", text=tr("process.name"))
        self.source_tree.heading("kind", text=tr("process.kind"))
        self.source_tree.heading("material", text=tr("process.material"))
        self.source_tree.heading("origin", text=tr("process.origin"))
        self.source_tree.column("#0", width=190)
        self.source_tree.column("kind", width=90)
        self.source_tree.column("material", width=150)
        self.source_tree.column("origin", width=130)
        self.source_tree.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.source_tree.bind("<<TreeviewSelect>>", self._load_source)

        form = ttk.LabelFrame(parent, text=tr("process.sources"), padding=10)
        form.grid(row=0, column=1, sticky="nsew")
        form.columnconfigure(1, weight=1)
        self._entry(form, 0, 0, "process.name", self.source_name)
        ttk.Label(form, text=tr("process.kind")).grid(row=1, column=0, sticky="w", pady=4)
        ttk.Combobox(
            form,
            textvariable=self.source_kind,
            values=tuple(value.value for value in DyeSourceKind),
            state="readonly",
        ).grid(row=1, column=1, sticky="ew", pady=4)
        self._entry(form, 2, 0, "process.material", self.source_material)
        self._entry(form, 3, 0, "process.part", self.source_part)
        self._entry(form, 4, 0, "process.origin", self.source_origin)
        ttk.Label(form, text=tr("process.notes")).grid(row=5, column=0, sticky="nw", pady=4)
        self.source_notes = tk.Text(form, height=5, wrap="word")
        self.source_notes.grid(row=5, column=1, sticky="ew", pady=4)
        self._form_actions(
            form,
            6,
            add=self._add_source,
            update=self._update_source,
            remove=self._remove_source,
        )

    def _build_recipe_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)
        self.recipe_tree = ttk.Treeview(
            parent,
            columns=("color", "source", "mordant"),
            show="tree headings",
            selectmode="browse",
        )
        self.recipe_tree.heading("#0", text=tr("process.name"))
        self.recipe_tree.heading("color", text=tr("process.color"))
        self.recipe_tree.heading("source", text=tr("process.source"))
        self.recipe_tree.heading("mordant", text=tr("process.mordant"))
        self.recipe_tree.column("#0", width=180)
        self.recipe_tree.column("color", width=80)
        self.recipe_tree.column("source", width=150)
        self.recipe_tree.column("mordant", width=120)
        self.recipe_tree.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.recipe_tree.bind("<<TreeviewSelect>>", self._load_recipe)

        form = ttk.LabelFrame(parent, text=tr("process.recipes"), padding=10)
        form.grid(row=0, column=1, sticky="nsew")
        form.columnconfigure(1, weight=1)
        self._entry(form, 0, 0, "process.name", self.recipe_name)
        ttk.Label(form, text=tr("process.color")).grid(row=1, column=0, sticky="w", pady=4)
        color_holder = ttk.Frame(form)
        color_holder.grid(row=1, column=1, sticky="ew", pady=4)
        color_holder.columnconfigure(0, weight=1)
        ttk.Entry(color_holder, textvariable=self.recipe_color).grid(row=0, column=0, sticky="ew")
        ttk.Button(color_holder, text="…", width=3, command=self._choose_recipe_color).grid(
            row=0,
            column=1,
            padx=(5, 0),
        )
        ttk.Label(form, text=tr("process.source")).grid(row=2, column=0, sticky="w", pady=4)
        self.recipe_source_combo = ttk.Combobox(
            form,
            textvariable=self.recipe_source,
            state="readonly",
        )
        self.recipe_source_combo.grid(row=2, column=1, sticky="ew", pady=4)
        self._entry(form, 3, 0, "process.mordant", self.recipe_mordant)
        self._entry(form, 4, 0, "process.ratio", self.recipe_ratio)
        self._entry(form, 5, 0, "process.temperature", self.recipe_temperature)
        ttk.Label(form, text=tr("process.notes")).grid(row=6, column=0, sticky="nw", pady=4)
        self.recipe_notes = tk.Text(form, height=4, wrap="word")
        self.recipe_notes.grid(row=6, column=1, sticky="ew", pady=4)
        self._form_actions(
            form,
            7,
            add=self._add_recipe,
            update=self._update_recipe,
            remove=self._remove_recipe,
        )

    def _build_step_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)
        self.step_tree = ttk.Treeview(
            parent,
            columns=("action", "recipe", "objects"),
            show="tree headings",
            selectmode="browse",
        )
        self.step_tree.heading("#0", text=tr("process.name"))
        self.step_tree.heading("action", text=tr("process.action"))
        self.step_tree.heading("recipe", text=tr("process.recipe"))
        self.step_tree.heading("objects", text=tr("process.objects"))
        self.step_tree.column("#0", width=200)
        self.step_tree.column("action", width=120)
        self.step_tree.column("recipe", width=150)
        self.step_tree.column("objects", width=80)
        self.step_tree.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.step_tree.bind("<<TreeviewSelect>>", self._load_step)

        form = ttk.LabelFrame(parent, text=tr("process.steps"), padding=10)
        form.grid(row=0, column=1, sticky="nsew")
        form.columnconfigure(1, weight=1)
        self._entry(form, 0, 0, "process.name", self.step_name)
        ttk.Label(form, text=tr("process.action")).grid(row=1, column=0, sticky="w", pady=4)
        ttk.Combobox(
            form,
            textvariable=self.step_action,
            values=tuple(value.value for value in ProcessAction),
            state="readonly",
        ).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(form, text=tr("process.recipe")).grid(row=2, column=0, sticky="w", pady=4)
        self.step_recipe_combo = ttk.Combobox(
            form,
            textvariable=self.step_recipe,
            state="readonly",
        )
        self.step_recipe_combo.grid(row=2, column=1, sticky="ew", pady=4)
        self._entry(form, 3, 0, "process.duration", self.step_duration)
        ttk.Label(form, text=tr("process.objects")).grid(row=4, column=0, sticky="nw", pady=4)
        selection_holder = ttk.Frame(form)
        selection_holder.grid(row=4, column=1, sticky="ew", pady=4)
        selection_holder.columnconfigure(0, weight=1)
        ttk.Label(selection_holder, textvariable=self.step_selection_label).grid(
            row=0,
            column=0,
            sticky="w",
        )
        ttk.Button(
            selection_holder,
            text=tr("process.use_selection"),
            command=self._use_selected_objects,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(form, text=tr("process.notes")).grid(row=5, column=0, sticky="nw", pady=4)
        self.step_notes = tk.Text(form, height=5, wrap="word")
        self.step_notes.grid(row=5, column=1, sticky="ew", pady=4)
        self._form_actions(
            form,
            6,
            add=self._add_step,
            update=self._update_step,
            remove=self._remove_step,
        )

    def _entry(
        self,
        parent: ttk.Frame,
        row: int,
        column: int,
        label_key: str,
        variable: tk.StringVar,
    ) -> None:
        ttk.Label(parent, text=tr(label_key)).grid(
            row=row,
            column=column,
            sticky="w",
            padx=(0, 6),
            pady=4,
        )
        ttk.Entry(parent, textvariable=variable).grid(
            row=row,
            column=column + 1,
            sticky="ew",
            pady=4,
        )

    def _form_actions(
        self,
        parent: ttk.Frame,
        row: int,
        *,
        add: object,
        update: object,
        remove: object,
    ) -> None:
        actions = ttk.Frame(parent)
        actions.grid(row=row, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(actions, text=tr("process.add"), command=add).pack(side="left")
        ttk.Button(actions, text=tr("process.update"), command=update).pack(
            side="left",
            padx=(6, 0),
        )
        ttk.Button(actions, text=tr("process.remove"), command=remove).pack(
            side="left",
            padx=(6, 0),
        )

    def _refresh_all(self) -> None:
        self._refresh_sources()
        self._refresh_recipes()
        self._refresh_steps()

    def _refresh_sources(self) -> None:
        self._replace_tree(
            self.source_tree,
            [
                (
                    source.source_id,
                    source.name,
                    (source.kind.value, source.material, source.origin),
                )
                for source in self._sources
            ],
        )
        names = [source.name for source in self._sources]
        self.recipe_source_combo.configure(values=("", *names))
        if self.recipe_source.get() not in names:
            self.recipe_source.set("")

    def _refresh_recipes(self) -> None:
        source_names = {source.source_id: source.name for source in self._sources}
        self._replace_tree(
            self.recipe_tree,
            [
                (
                    recipe.recipe_id,
                    recipe.name,
                    (
                        recipe.hex_color,
                        ", ".join(source_names.get(value, value) for value in recipe.source_ids),
                        recipe.mordant,
                    ),
                )
                for recipe in self._recipes
            ],
        )
        names = [recipe.name for recipe in self._recipes]
        self.step_recipe_combo.configure(values=("", *names))
        if self.step_recipe.get() not in names:
            self.step_recipe.set("")

    def _refresh_steps(self) -> None:
        recipe_names = {recipe.recipe_id: recipe.name for recipe in self._recipes}
        self._replace_tree(
            self.step_tree,
            [
                (
                    step.step_id,
                    f"{index}. {step.name}",
                    (
                        step.action.value,
                        recipe_names.get(step.recipe_id or "", ""),
                        len(step.object_ids),
                    ),
                )
                for index, step in enumerate(self._steps, start=1)
            ],
        )

    @staticmethod
    def _replace_tree(
        tree: ttk.Treeview,
        rows: list[tuple[str, str, tuple[object, ...]]],
    ) -> None:
        for item in tree.get_children():
            tree.delete(item)
        for item_id, text, values in rows:
            tree.insert("", "end", iid=item_id, text=text, values=values)

    def _selected_id(self, tree: ttk.Treeview) -> str | None:
        selection = tree.selection()
        return selection[0] if selection else None

    def _source_from_form(self, source_id: str | None = None) -> DyeSource:
        return DyeSource(
            source_id=source_id or str(__import__("uuid").uuid4()),
            name=self.source_name.get(),
            kind=self.source_kind.get(),
            material=self.source_material.get(),
            plant_part=self.source_part.get(),
            origin=self.source_origin.get(),
            notes=self.source_notes.get("1.0", "end").strip(),
        )

    def _recipe_from_form(self, recipe_id: str | None = None) -> ColorRecipe:
        source = next(
            (value for value in self._sources if value.name == self.recipe_source.get()),
            None,
        )
        temperature_text = self.recipe_temperature.get().strip()
        return ColorRecipe(
            recipe_id=recipe_id or str(__import__("uuid").uuid4()),
            name=self.recipe_name.get(),
            hex_color=self.recipe_color.get(),
            source_ids=() if source is None else (source.source_id,),
            mordant=self.recipe_mordant.get(),
            ratio=self.recipe_ratio.get(),
            bath_temperature_celsius=(
                None if not temperature_text else float(temperature_text)
            ),
            notes=self.recipe_notes.get("1.0", "end").strip(),
        )

    def _step_from_form(self, step_id: str | None = None) -> ProcessStep:
        recipe = next(
            (value for value in self._recipes if value.name == self.step_recipe.get()),
            None,
        )
        duration_text = self.step_duration.get().strip()
        return ProcessStep(
            step_id=step_id or str(__import__("uuid").uuid4()),
            name=self.step_name.get(),
            action=self.step_action.get(),
            object_ids=self._step_object_ids,
            group_ids=self._step_group_ids,
            recipe_id=None if recipe is None else recipe.recipe_id,
            duration_minutes=None if not duration_text else int(duration_text),
            notes=self.step_notes.get("1.0", "end").strip(),
        )

    def _add_source(self) -> None:
        try:
            self._sources.append(self._source_from_form())
        except Exception as exc:
            self._error(exc)
            return
        self._clear_source_form()
        self._refresh_all()

    def _update_source(self) -> None:
        item_id = self._selected_id(self.source_tree)
        if item_id is None:
            self._select_item_error()
            return
        try:
            replacement = self._source_from_form(item_id)
            self._sources = [replacement if value.source_id == item_id else value for value in self._sources]
        except Exception as exc:
            self._error(exc)
            return
        self._refresh_all()

    def _remove_source(self) -> None:
        item_id = self._selected_id(self.source_tree)
        if item_id is None:
            self._select_item_error()
            return
        self._sources = [value for value in self._sources if value.source_id != item_id]
        self._recipes = [
            replace(value, source_ids=tuple(source for source in value.source_ids if source != item_id))
            for value in self._recipes
        ]
        self._clear_source_form()
        self._refresh_all()

    def _add_recipe(self) -> None:
        try:
            self._recipes.append(self._recipe_from_form())
        except Exception as exc:
            self._error(exc)
            return
        self._clear_recipe_form()
        self._refresh_all()

    def _update_recipe(self) -> None:
        item_id = self._selected_id(self.recipe_tree)
        if item_id is None:
            self._select_item_error()
            return
        try:
            replacement = self._recipe_from_form(item_id)
            self._recipes = [replacement if value.recipe_id == item_id else value for value in self._recipes]
        except Exception as exc:
            self._error(exc)
            return
        self._refresh_all()

    def _remove_recipe(self) -> None:
        item_id = self._selected_id(self.recipe_tree)
        if item_id is None:
            self._select_item_error()
            return
        self._recipes = [value for value in self._recipes if value.recipe_id != item_id]
        self._steps = [
            replace(value, recipe_id=None) if value.recipe_id == item_id else value
            for value in self._steps
        ]
        self._clear_recipe_form()
        self._refresh_all()

    def _add_step(self) -> None:
        try:
            self._steps.append(self._step_from_form())
        except Exception as exc:
            self._error(exc)
            return
        self._clear_step_form()
        self._refresh_all()

    def _update_step(self) -> None:
        item_id = self._selected_id(self.step_tree)
        if item_id is None:
            self._select_item_error()
            return
        try:
            replacement = self._step_from_form(item_id)
            self._steps = [replacement if value.step_id == item_id else value for value in self._steps]
        except Exception as exc:
            self._error(exc)
            return
        self._refresh_all()

    def _remove_step(self) -> None:
        item_id = self._selected_id(self.step_tree)
        if item_id is None:
            self._select_item_error()
            return
        self._steps = [value for value in self._steps if value.step_id != item_id]
        self._clear_step_form()
        self._refresh_all()

    def _load_source(self, _event: tk.Event[tk.Misc]) -> None:
        item_id = self._selected_id(self.source_tree)
        source = next((value for value in self._sources if value.source_id == item_id), None)
        if source is None:
            return
        self.source_name.set(source.name)
        self.source_kind.set(source.kind.value)
        self.source_material.set(source.material)
        self.source_part.set(source.plant_part)
        self.source_origin.set(source.origin)
        self._set_text(self.source_notes, source.notes)

    def _load_recipe(self, _event: tk.Event[tk.Misc]) -> None:
        item_id = self._selected_id(self.recipe_tree)
        recipe = next((value for value in self._recipes if value.recipe_id == item_id), None)
        if recipe is None:
            return
        source_names = {value.source_id: value.name for value in self._sources}
        self.recipe_name.set(recipe.name)
        self.recipe_color.set(recipe.hex_color)
        self.recipe_source.set(source_names.get(recipe.source_ids[0], "") if recipe.source_ids else "")
        self.recipe_mordant.set(recipe.mordant)
        self.recipe_ratio.set(recipe.ratio)
        self.recipe_temperature.set(
            "" if recipe.bath_temperature_celsius is None else str(recipe.bath_temperature_celsius)
        )
        self._set_text(self.recipe_notes, recipe.notes)

    def _load_step(self, _event: tk.Event[tk.Misc]) -> None:
        item_id = self._selected_id(self.step_tree)
        step = next((value for value in self._steps if value.step_id == item_id), None)
        if step is None:
            return
        recipe_names = {value.recipe_id: value.name for value in self._recipes}
        self.step_name.set(step.name)
        self.step_action.set(step.action.value)
        self.step_recipe.set(recipe_names.get(step.recipe_id or "", ""))
        self.step_duration.set("" if step.duration_minutes is None else str(step.duration_minutes))
        self._step_object_ids = step.object_ids
        self._step_group_ids = step.group_ids
        self._refresh_selection_label()
        self._set_text(self.step_notes, step.notes)

    def _use_selected_objects(self) -> None:
        selected = self.session.selected_objects
        if not selected:
            messagebox.showerror(self.title(), tr("process.no_selection"), parent=self)
            return
        self._step_object_ids = tuple(value.object_id for value in selected)
        self._step_group_ids = tuple(
            dict.fromkeys(
                str(value.properties["object_group_id"])
                for value in selected
                if value.properties.get("object_group_id")
            )
        )
        self._refresh_selection_label()

    def _refresh_selection_label(self) -> None:
        self.step_selection_label.set(
            tr(
                "process.selection_count",
                count=len(self._step_object_ids),
                groups=len(self._step_group_ids),
            )
        )

    def _choose_recipe_color(self) -> None:
        _rgb, selected = colorchooser.askcolor(
            color=self.recipe_color.get(),
            parent=self,
            title=tr("process.color"),
        )
        if selected:
            self.recipe_color.set(selected.upper())

    def _build_plan(self) -> BatikProcessPlan:
        return BatikProcessPlan(
            plan_id=self.session.process_plan.plan_id,
            title=self.plan_title.get(),
            fabric=self.fabric.get(),
            technique=self.technique.get(),
            notes=self.plan_notes.get("1.0", "end").strip(),
            dye_sources=tuple(self._sources),
            color_recipes=tuple(self._recipes),
            steps=tuple(self._steps),
        )

    def _save(self) -> BatikProcessPlan | None:
        try:
            plan = self._build_plan()
            self.session.set_process_plan(plan)
        except (ProjectSessionError, ValueError, TypeError) as exc:
            self._error(exc)
            return None
        messagebox.showinfo(self.title(), tr("process.saved"), parent=self)
        return plan

    def _export(self) -> None:
        try:
            plan = self._build_plan()
        except (ValueError, TypeError) as exc:
            self._error(exc)
            return
        selected = filedialog.asksaveasfilename(
            parent=self,
            title=tr("process.export"),
            defaultextension=".batikprocess",
            filetypes=[("Batik Process", "*.batikprocess"), ("All files", "*.*")],
        )
        if not selected:
            return
        try:
            self.session.set_process_plan(plan)
            output = self.session.export_process_package(Path(selected), plan=plan)
        except (ProjectSessionError, OSError) as exc:
            self._error(exc)
            return
        messagebox.showinfo(
            self.title(),
            tr("process.exported", path=output),
            parent=self,
        )

    def _clear_source_form(self) -> None:
        self.source_name.set("")
        self.source_material.set("")
        self.source_part.set("")
        self.source_origin.set("")
        self._set_text(self.source_notes, "")

    def _clear_recipe_form(self) -> None:
        self.recipe_name.set("")
        self.recipe_source.set("")
        self.recipe_mordant.set("")
        self.recipe_ratio.set("")
        self.recipe_temperature.set("")
        self._set_text(self.recipe_notes, "")

    def _clear_step_form(self) -> None:
        self.step_name.set("")
        self.step_recipe.set("")
        self.step_duration.set("")
        self._step_object_ids = ()
        self._step_group_ids = ()
        self.step_selection_label.set(tr("process.no_selection"))
        self._set_text(self.step_notes, "")

    @staticmethod
    def _set_text(widget: tk.Text, value: str) -> None:
        widget.delete("1.0", "end")
        widget.insert("1.0", value)

    def _select_item_error(self) -> None:
        messagebox.showerror(self.title(), tr("process.select_item"), parent=self)

    def _error(self, exc: Exception) -> None:
        messagebox.showerror(
            self.title(),
            tr("process.invalid", error=str(exc)),
            parent=self,
        )


__all__ = ["BatikProcessStudioWindow"]
