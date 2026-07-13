"""Public imaging API for raster layers and project previews."""

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
    "MAX_RASTER_DIMENSION",
    "MAX_RASTER_PIXELS",
    "MissingRasterAssetError",
    "ProjectRenderError",
    "RasterAsset",
    "RasterImageError",
    "RenderedProject",
    "normalize_raster_image",
    "point_hits_layer",
    "render_project_preview",
    "transformed_layer_bounds",
]
