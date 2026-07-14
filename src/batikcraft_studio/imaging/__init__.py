"""Public imaging API for raster layers, paint strokes, and project previews."""

from batikcraft_studio.imaging.paint import (
    MAX_BRUSH_SIZE,
    PaintStrokeError,
    apply_paint_stroke,
    create_transparent_canvas_png,
    smooth_stroke_points,
)
from batikcraft_studio.imaging.raster import (
    MAX_RASTER_DIMENSION,
    MAX_RASTER_PIXELS,
    RasterAsset,
    RasterImageError,
    normalize_raster_image,
)
from batikcraft_studio.imaging.renderer import (
    MissingRasterAssetError,
    ProjectRenderError,
    RenderedProject,
    point_hits_layer,
    render_project_preview,
    transformed_layer_bounds,
)

__all__ = [
    "MAX_BRUSH_SIZE",
    "MAX_RASTER_DIMENSION",
    "MAX_RASTER_PIXELS",
    "MissingRasterAssetError",
    "PaintStrokeError",
    "ProjectRenderError",
    "RasterAsset",
    "RasterImageError",
    "RenderedProject",
    "apply_paint_stroke",
    "create_transparent_canvas_png",
    "normalize_raster_image",
    "point_hits_layer",
    "render_project_preview",
    "smooth_stroke_points",
    "transformed_layer_bounds",
]
