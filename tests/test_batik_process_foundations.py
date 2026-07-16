from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path

from batikcraft_studio.application import GROUP_ID_KEY, BatikProcessProjectSession
from batikcraft_studio.domain import (
    BatikProcessPlan,
    ColorRecipe,
    DyeSource,
    DyeSourceKind,
    ProcessAction,
    ProcessStep,
)
from PIL import Image, ImageDraw


def _png() -> bytes:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 56, 56), outline=(75, 38, 24, 255), width=6)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _plan(object_ids: tuple[str, ...] = (), group_ids: tuple[str, ...] = ()) -> BatikProcessPlan:
    source = DyeSource(
        name="Daun Indigofera",
        kind=DyeSourceKind.NATURAL,
        material="Indigofera tinctoria",
        plant_part="Daun",
        origin="Indonesia",
    )
    recipe = ColorRecipe(
        name="Indigo Tua",
        hex_color="#2F4B7C",
        source_ids=(source.source_id,),
        mordant="Kapur",
        ratio="1:5",
        bath_temperature_celsius=28,
    )
    return BatikProcessPlan(
        title="Proses Batik Wayang",
        fabric="Katun primissima",
        technique="Batik tulis",
        dye_sources=(source,),
        color_recipes=(recipe,),
        steps=(
            ProcessStep(
                name="Canting garis utama",
                action=ProcessAction.CANTING_OUTLINE,
                object_ids=object_ids,
                group_ids=group_ids,
                duration_minutes=90,
            ),
            ProcessStep(
                name="Celup indigo",
                action=ProcessAction.DYE_BATH,
                recipe_id=recipe.recipe_id,
                duration_minutes=30,
            ),
        ),
    )


def test_process_plan_round_trip_dict() -> None:
    plan = _plan()

    loaded = BatikProcessPlan.from_dict(plan.to_dict())

    assert loaded == plan
    assert loaded.color_recipes[0].source_ids == (loaded.dye_sources[0].source_id,)
    assert loaded.steps[1].recipe_id == loaded.color_recipes[0].recipe_id


def test_process_plan_persists_in_project_without_changing_canvas_objects(
    tmp_path: Path,
) -> None:
    session = BatikProcessProjectSession(tmp_path / "models")
    session.new_project(title="Process", creator="Tester", width=256, height=256)
    first = session.import_raster_object("first.png", _png())
    second = session.import_raster_object("second.png", _png())
    session.set_selected_objects([first.object_id, second.object_id])
    group_id = session.group_selected_objects("Motif Utama")
    session.set_process_plan(_plan((first.object_id, second.object_id), (group_id,)))
    object_count = session.require_project().object_count
    path = tmp_path / "process.batikcraft"
    session.save_as(path)

    reopened = BatikProcessProjectSession(tmp_path / "models-reopened")
    reopened.open_project(path)

    assert reopened.require_project().object_count == object_count
    assert reopened.process_plan.title == "Proses Batik Wayang"
    assert reopened.process_plan.steps[0].group_ids == (group_id,)
    properties = reopened.require_project().get_object(first.object_id).properties
    assert properties[GROUP_ID_KEY] == group_id


def test_process_package_contains_machine_and_human_readable_files(tmp_path: Path) -> None:
    session = BatikProcessProjectSession(tmp_path / "models")
    session.new_project(title="Export", creator="Tester", width=128, height=128)
    session.set_process_plan(_plan())

    output = session.export_process_package(tmp_path / "workshop.batikprocess")

    with zipfile.ZipFile(output, "r") as archive:
        names = set(archive.namelist())
        assert names == {
            "README.md",
            "color-recipes.csv",
            "dye-sources.csv",
            "process.json",
            "steps.csv",
        }
        process = json.loads(archive.read("process.json").decode("utf-8"))
        readme = archive.read("README.md").decode("utf-8")
    assert process["title"] == "Proses Batik Wayang"
    assert "Daun Indigofera" in readme
    assert "Indigo Tua" in readme


def test_marquee_selection_does_not_group_objects_automatically(tmp_path: Path) -> None:
    session = BatikProcessProjectSession(tmp_path / "models")
    session.new_project(title="Selection", creator="Tester", width=300, height=200)
    first = session.import_raster_object("first.png", _png())
    second = session.import_raster_object("second.png", _png())
    session.update_object_transform(first.object_id, x=80, y=100)
    session.update_object_transform(second.object_id, x=220, y=100)

    selected = session.select_objects_in_rectangle((0, 0, 300, 200))

    assert {item.object_id for item in selected} == {first.object_id, second.object_id}
    assert all(GROUP_ID_KEY not in item.properties for item in selected)
