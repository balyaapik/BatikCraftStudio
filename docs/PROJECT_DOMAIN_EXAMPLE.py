"""Small reference example for the Milestone 2A domain API."""

from batikcraft_studio.domain import Layer, LayerKind, Project

project = Project.create(
    "Flora Otomotif",
    "Balya Rochmadi",
    description="Object-inspired contemporary batik motif.",
    tags=("flora", "automotive", "contemporary"),
)
project.add_layer(
    Layer(
        name="Main Batikified Object",
        kind=LayerKind.BATIKIFIED_OBJECT,
        asset_ref="assets/main-object.png",
        properties={"style_id": "parang_contemporary", "seed": 72641},
    )
)

assert project.is_dirty
project.mark_saved()
assert not project.is_dirty
