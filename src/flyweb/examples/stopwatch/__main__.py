#!/usr/bin/env python3

import datetime
import logging
import sys

import anyio
import flyweb

try:
    import hypercorn  # noqa: F401
except ImportError:
    raise RuntimeError("install extras with flyweb[examples] to run this!") from None


class Stopwatch:
    """Example of a server-side stopwatch."""

    def __init__(self):
        self._elapsed = datetime.timedelta()
        # If stopwatch is running, this contains the time it was last started.
        self._start_time = None

    def _make_elapsed_string(self) -> str:
        seconds = self._elapsed.total_seconds()
        milliseconds = int(seconds * 1000) % 1000
        minutes = int(seconds) // 60
        seconds = int(seconds) % 60
        return f"{minutes:02}:{seconds:02}.{milliseconds:03}"

    def _on_reset(self, _) -> None:
        self._elapsed = datetime.timedelta()
        self._start_time = None

    def _on_start(self, _) -> None:
        self._start_time = datetime.datetime.now()

    def _on_stop(self, _) -> None:
        if not self._start_time:
            return
        self._elapsed += datetime.datetime.now() - self._start_time
        self._start_time = None

    def render(self, w: flyweb.FlyWeb) -> None:
        if self._start_time:
            self._elapsed += datetime.datetime.now() - self._start_time
            self._start_time = datetime.datetime.now()

        with w.div():
            w.text("Elapsed: ")
            w.text(self._make_elapsed_string())

        with w.div():
            w.button("RESET", key="reset", onclick=self._on_reset)
            if not self._start_time:
                w.button("START", key="start", onclick=self._on_start)
            else:
                w.button("STOP", key="stop", onclick=self._on_stop)


async def _update_task(server: flyweb.Server) -> None:
    while True:
        server.schedule_update()
        await anyio.sleep(0.25)


async def main():
    stopwatch = Stopwatch()
    server = flyweb.Server(stopwatch.render, port=8000)

    async with anyio.create_task_group() as tg:
        tg.start_soon(_update_task, server)
        await server.run()


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    anyio.run(main)
