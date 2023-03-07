#!/usr/bin/env python3

import asyncio

from loguru import logger

import flyweb


class Counter:
    """Example with a counter and an [INCREMENT] button."""

    def __init__(self):
        self._count = 0

    def render(self, w: flyweb.FlyWeb) -> None:
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
    logger.enable("flyweb")
    asyncio.run(main())
