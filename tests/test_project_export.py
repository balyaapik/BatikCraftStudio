from __future__ import annotations

from io import BytesIO

from PIL import Image

from batikcraft_studio.domain import (
    CanvasSpec,
    Layer,
    LayerObject,
    ObjectBounds,
    ObjectKind,
    Project,
)
from batikcraft_studio.project_export import (
    creator_id_suggestion,
    discover_project_colors,
    discover_project_motifs,
    render_project_jpeg,
)


def test_render_project_jpeg_uses_full_canvas_dimensions() -> None:
    project = Project.create(
        "Export",
        "Creator",
        canvas=CanvasSpec(width=80, height=60, background_color="#F0E0C0"),
    )

    content = render_project_jpeg(project, {})

    with Image.open(BytesIO(content)) as image:
        assert image.format == "JPEG"
        assert image.size == (80, 60)
        assert image.mode == "RGB"


def test_discover_project_colors_and_motifs_reads_nested_properties() -> None:
    motif = LayerObject(
        name="Kawung Utama",
        kind=ObjectKind.MOTIF,
        bounds=ObjectBounds(20, 20),
        properties={
            "fill": "#7A3E21",
            "gradient": {"stops": ["#F2D6A2", "#7A3E21"]},
            "motif_type": "Kawung",
        },
    )
    project = Project.create(
        "Metadata",
        "Creator",
        canvas=CanvasSpec(width=100, height=100, background_color="#FFF8E8"),
    )
    project.add_layer(
        Layer(
            name="Motif",
            objects=(motif,),
            properties={"batik_style": "Klasik Yogyakarta"},
        )
    )

    assert discover_project_colors(project) == (
        "#FFF8E8",
        "#7A3E21",
        "#F2D6A2",
    )
    assert discover_project_motifs(project) == (
        "Klasik Yogyakarta",
        "Kawung Utama",
        "Kawung",
    )


def test_creator_id_suggestion_is_web_safe() -> None:
    assert creator_id_suggestion("Balya Rochmadi / Studio") == "Balya-Rochmadi-Studio"
