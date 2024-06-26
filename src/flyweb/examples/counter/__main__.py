#!/usr/bin/env python3

import logging
import sys

import anyio
import flyweb

try:
    import hypercorn  # noqa: F401
except ImportError:
    raise RuntimeError("install extras with flyweb[examples] to run this!") from None


class Counter:
    """Example with a counter and an [INCREMENT] button."""

    def __init__(self):
        self._count = 0

    def render(self, w: flyweb.FlyWeb) -> None:
        w.set_title(f"Counter: {self._count}")
        with w.div():
            w.text(f"count is {self._count}")
        with w.div():
            w.button("INCREMENT", onclick=self._increment)

    def _increment(self, _) -> None:
        self._count += 1


async def main():
    counter = Counter()
    await flyweb.Server(counter.render, port=8000).run()


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    anyio.run(main)
