import logging
from collections.abc import Callable

import anyio
import hypercorn
import hypercorn.asyncio

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

    async def run(self, *, task_status=anyio.TASK_STATUS_IGNORED) -> None:
        cfg = hypercorn.config.Config()
        cfg.bind = f"0.0.0.0:{self._port}"
        cfg.accesslog = logging.getLogger("hypercorn.accesslog")
        cfg.access_log_format = '%(h)s "%(R)s" %(s)s %(b)s "%(f)s" "%(a)s"'
        cfg.errorlog = logging.getLogger("hypercorn.errorlog")

        event = anyio.Event()
        async with anyio.create_task_group() as tg:
            await tg.start(self._serve, cfg, event)
            task_status.started()
            try:
                await anyio.sleep_forever()
            finally:
                # See comment in _serve.
                with anyio.move_on_after(1, shield=True):
                    event.set()

    async def _serve(
        self,
        cfg: hypercorn.Config,
        event: anyio.Event,
        *,
        task_status=anyio.TASK_STATUS_IGNORED,
    ) -> None:
        async with self._app as app:
            task_status.started()
            # We shield hypercorn from direct cancellation, and terminate it using
            # shutdown_trigger. This works around https://github.com/pgjones/hypercorn/issues/184.
            with anyio.CancelScope(shield=True):
                await hypercorn.asyncio.serve(
                    app,
                    cfg,
                    # Without this, hypercorn installs its own interrupt handler.
                    shutdown_trigger=event.wait,
                )

    def schedule_update(self) -> None:
        self._app.schedule_update()

    async def update(self) -> None:
        await self._app.update()
