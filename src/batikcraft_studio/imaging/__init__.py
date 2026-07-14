"""Public imaging API for raster, paint, shape, and project preview workflows."""

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
from batikcraft_studio.imaging.shape import (
    MAX_POLYGON_SIDES,
    MAX_SHAPE_STROKE_WIDTH,
    MIN_POLYGON_SIDES,
    SHAPE_TYPES,
    ShapeError,
    ShapeGeometry,
    build_shape_geometry,
    parse_shape_properties,
    render_shape_image,
    update_shape_properties,
)

__all__ = [
    "MAX_BRUSH_SIZE",
    "MAX_POLYGON_SIDES",
    "MAX_RASTER_DIMENSION",
    "MAX_RASTER_PIXELS",
    "MAX_SHAPE_STROKE_WIDTH",
    "MIN_POLYGON_SIDES",
    "MissingRasterAssetError",
    "PaintStrokeError",
    "ProjectRenderError",
    "RasterAsset",
    "RasterImageError",
    "RenderedProject",
    "SHAPE_TYPES",
    "ShapeError",
    "ShapeGeometry",
    "apply_paint_stroke",
    "build_shape_geometry",
    "create_transparent_canvas_png",
    "normalize_raster_image",
    "parse_shape_properties",
    "point_hits_layer",
    "render_project_preview",
    "render_shape_image",
    "smooth_stroke_points",
    "transformed_layer_bounds",
    "update_shape_properties",
]
