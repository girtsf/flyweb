from __future__ import annotations

import contextlib
from importlib import resources
import pathlib
import re
import shutil
import tempfile
from typing import Callable

from loguru import logger
import socketio

import flyweb


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

    @contextlib.asynccontextmanager
    async def _make_context(self):
        index_html_template = (
            resources.files(flyweb).joinpath("static/index.html").read_text()
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = pathlib.Path(tmp_dir)

            # Copy static/ dir.
            s = resources.files(flyweb).joinpath("static")
            with resources.as_file(s) as static_dir:
                shutil.copytree(static_dir, tmp_path / "static")

            # Generate index.html and add any extra css files to static/.
            index_html = self._make_index_html(tmp_path, index_html_template)

            (tmp_path / "index.html").write_text(index_html)

            static_files = {
                self._path: str(tmp_path / "index.html"),
                self._path.removesuffix("/") + "/static": str(tmp_path / "static"),
            }
            self._sio_app = socketio.ASGIApp(
                self._sio,
                static_files=static_files,
            )
            yield self
        self._sio_app = None

    async def __call__(self, scope, receive, send):
        if not self._sio_app:
            raise RuntimeError("you must enter App's async context")
        await self._sio_app(scope, receive, send)

    def _make_index_html(self, static_files_path: pathlib.Path, template: str) -> str:
        ss = []
        for i, str_or_path in enumerate(self._extra_css):
            css_file = static_files_path / "static" / f"{i}.css"
            if isinstance(str_or_path, pathlib.Path):
                shutil.copy(str_or_path, css_file)
            else:
                css_file.write_text(str_or_path)
            ss += [f'<link rel="stylesheet" href="static/{i}.css">']
        return re.sub(r"(?m)^\s*<!-- STYLESHEETS -->\s*$", "\n".join(ss), template)

    async def update(self) -> None:
        await self._update()

    async def _handle_socketio_connect(self, session_id: str, _) -> None:
        logger.debug(f'socket "{session_id}" connected')
        await self._update(session_id=session_id)

    async def _update(self, *, session_id: str | None = None) -> None:
        self._flyweb = flyweb.FlyWeb()
        self._render_function(self._flyweb)
        vdom = self._flyweb._dom
        msg = vdom.serialize()
        await self._sio.emit("update", msg, to=session_id)

    async def _handle_socketio_event(self, _, msg) -> None:
        if not isinstance(msg, dict):
            logger.error(f"got unexpected message type: {type(msg).__name__}")
            return

        if self._flyweb._handle_event_from_frontend(msg):
            await self._update()
