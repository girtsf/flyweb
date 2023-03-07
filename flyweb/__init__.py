from loguru import logger

from ._app import App
from ._flyweb import Event
from ._flyweb import FlyWeb
from ._flyweb import FocusEvent
from ._flyweb import FrontendFunction
from ._flyweb import KeyboardEvent
from ._flyweb import MouseEvent
from ._flyweb import UIEvent
from ._server import Server

# Disable logging for "flyweb" namespace by default. You can opt in to logs
# with logger.enable("flyweb").

logger.disable("flyweb")

__all__ = [
    "App",
    "Event",
    "FlyWeb",
    "FrontendFunction",
    "FocusEvent",
    "KeyboardEvent",
    "MouseEvent",
    "Server",
    "UIEvent",
]
