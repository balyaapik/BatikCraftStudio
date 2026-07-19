"""BatikCraft Studio application package."""

from .config import APP_NAME, APP_VERSION
from .web_bridge_extensions import install_web_bridge_extensions

install_web_bridge_extensions()

__all__ = ["APP_NAME", "APP_VERSION"]
