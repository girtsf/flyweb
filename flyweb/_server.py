import asyncio
import functools
from typing import Callable

import flyweb


class Server:
    """Wrapper to serve your FlyWeb function with HyperCorn.

    You have to install flyweb with the "server" extra for this to be
    available ("pip install flyweb[server]").
    """

    def __init__(
        self,
        render_function: Callable[[flyweb.FlyWeb], None],
        *,
        port: int = 8000,
        **kwargs,
    ):
        self._port = port
        self._app = flyweb.App("/", render_function, **kwargs)

    async def run(self) -> None:
        try:
            import hypercorn
            import hypercorn.asyncio
        except ImportError:
            raise RuntimeError("install flyweb[server] to include an asgi server!")

        cfg = hypercorn.config.Config()
        cfg.bind = f"0.0.0.0:{self._port}"
        cfg.accesslog = "-"
        cfg.errorlog = "-"

        async with self._app as app:
            await hypercorn.asyncio.serve(
                app,
                cfg,
                # Without this, hypercorn installs its own interrupt handler.
                shutdown_trigger=functools.partial(asyncio.sleep, 2e9),
            )

    async def update(self) -> None:
        await self._app.update()
