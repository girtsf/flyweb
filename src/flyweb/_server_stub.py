# This file is imported by __init__.py if the server optional dependencies are
# not installed.

from collections.abc import Callable

import flyweb


class Server:
    def __init__(
        self,
        render_function: Callable[[flyweb.FlyWeb], None],
        *,
        port: int = 8000,
        **kwargs,
    ):
        raise RuntimeError("install flyweb[server] to include an asgi server!")
