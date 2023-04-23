from __future__ import annotations

import contextlib
from importlib import resources
import logging
import pathlib
import re
import tempfile
from typing import Callable, Iterable

import anyio
import socketio

import flyweb

logger = logging.getLogger("flyweb")


class App:
    """Flyweb ASGI app.

    By default, FlyWeb doesn't include an ASGI server, so you can integrate it
    with whatever ASGI server you are using. See flyweb.Server for an optional
    batteries-included server.
    """

    def __init__(
        self,
        path: str,
        render_function: Callable[[flyweb.FlyWeb], None],
        *,
        # TODO: document that this can be either a string (CSS fragment) or
        # path to a file.
        extra_css: list[str | pathlib.Path] | None = None,
    ):
        self._path = path
        self._render_function = render_function
        self._extra_css = extra_css or []

        self._sio = socketio.AsyncServer(
            async_mode="asgi", socketio_path=path.removesuffix("/") + "/socket.io"
        )
        self._sio.on("connect", self._handle_socketio_connect)
        self._sio.on("event", self._handle_socketio_event)

        self._flyweb = flyweb.FlyWeb()
        self._sio_app = None
        self._ctx = None
        # Wait to initialize it until we are running. Otherwise, this blows up
        # if the object is instantiated before running in async context.
        self._update_requested: anyio.Event | None = None

    async def __aenter__(self) -> App:
        if self._ctx:
            raise RuntimeError("context is not reentrant")
        self._ctx = self._make_context()
        return await self._ctx.__aenter__()

    async def __aexit__(self, *args, **kwargs):
        if not self._ctx:
            raise RuntimeError("context was not entered")
        ctx, self._ctx = self._ctx, None
        return await ctx.__aexit__(*args, **kwargs)

    async def __call__(self, scope, receive, send):
        if not self._sio_app:
            raise RuntimeError("you must enter App's async context")
        await self._sio_app(scope, receive, send)

    @contextlib.asynccontextmanager
    async def _make_context(self):
        with self._make_static_dir() as static_files:
            self._sio_app = socketio.ASGIApp(
                self._sio,
                static_files=static_files,
            )
            async with anyio.create_task_group() as tg:
                tg.start_soon(self._update_task)
                yield self
                tg.cancel_scope.cancel()
        self._sio_app = None

    @contextlib.contextmanager
    def _make_static_dir(self):
        index_html_template = (
            resources.files(flyweb).joinpath("static/index.html").read_text()
        )
        # Create a temporary directory. We'll write index.html to it and any
        # CSS fragments that were passed in as strings.
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = pathlib.Path(tmp_dir)
            static_files = self._make_css_static_files_map(tmp_path)

            index_html = self._make_index_html(index_html_template, static_files.keys())
            (tmp_path / "index.html").write_text(index_html)
            static_files[self._path] = str(tmp_path / "index.html")

            with resources.as_file(
                resources.files(flyweb).joinpath("static")
            ) as flyweb_static_files:
                static_files[self._path.removesuffix("/") + "/static"] = str(
                    flyweb_static_files
                )
                yield static_files

    async def _update_task(self) -> None:
        self._update_requested = anyio.Event()
        while True:
            await self._update_requested.wait()
            self._update_requested = anyio.Event()
            await self._update()

    def _make_css_static_files_map(
        self, tmp_static_path: pathlib.Path
    ) -> dict[str, str]:
        static_files = {}
        for i, str_or_path in enumerate(self._extra_css):
            basename = f"{i}.css"
            if isinstance(str_or_path, pathlib.Path):
                # extra CSS is a file, add it to static file mappings.
                path = str_or_path
            else:
                # extra CSS is a string, write it out to temp file.
                path = tmp_static_path / basename
                path.write_text(str_or_path)
            static_files[self._path.removesuffix("/") + f"/static/{basename}"] = str(
                path
            )
        return static_files

    def _make_index_html(self, template: str, stylesheets: Iterable[str]) -> str:
        ss = [f'<link rel="stylesheet" href="{x}">' for x in stylesheets]
        return re.sub(r"(?m)^\s*<!-- STYLESHEETS -->\s*$", "\n".join(ss), template)

    def schedule_update(self) -> None:
        if self._update_requested is not None:
            self._update_requested.set()

    async def update(self) -> None:
        await self._update()

    async def _handle_socketio_connect(self, session_id: str, _) -> None:
        logger.debug(f'socket "{session_id}" connected')
        await self._update(session_id=session_id)

    async def _update(self, *, session_id: str | None = None) -> None:
        self._flyweb = flyweb.FlyWeb()
        self._render_function(self._flyweb)
        msg = self._flyweb._dom.serialize()
        await self._sio.emit("update", msg, to=session_id)

    async def _handle_socketio_event(self, _, msg) -> None:
        if not isinstance(msg, dict):
            logger.error(f"got unexpected message type: {type(msg).__name__}")
            return

        if self._flyweb._handle_event_from_frontend(msg):
            await self._update()
