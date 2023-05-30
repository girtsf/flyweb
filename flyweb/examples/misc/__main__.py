#!/usr/bin/env python3

from __future__ import annotations

import logging
import sys

import anyio

import flyweb
from flyweb import components

try:
    import hypercorn as _  # noqa: F401
except ImportError:
    raise RuntimeError("install extras with flyweb[examples] to run this!")


# CSS fragment that will be sent to frontend.
_CSS = """
table {
  border-collapse: collapse;
}
table td {
  border: 1px solid black;
  padding: 5px;
}
"""


class MiscExample:
    """Demo of different elements and events.

    This is also used for regression tests in browser_tests.py.
    """

    def __init__(self):
        self.checkbox1 = components.CheckBox(
            id="checkbox1", onclick=self._handle_checkbox_onclick
        )
        self.checkbox2 = components.CheckBox(
            id="checkbox2", checked=True, onclick=self._handle_checkbox_onclick
        )
        self.text_input = components.TextInput(
            id="text_input",
            value="foo",
            onblur=self._handle_text_input_onblur,
            individual_key_down_handlers={
                "Escape": self._handle_text_input_custom_key_down,
                "Enter": self._handle_text_input_custom_key_down,
            },
        )
        self.message = ""

    def render(self, w: flyweb.FlyWeb):
        w.h1("Demo of different elements and events")
        with w.table():
            with w.tr():
                with w.td():
                    self.checkbox1.render(w)
                with w.td():
                    w.text("checkbox (starts out unchecked)")
                with w.td():
                    w.text(f"checkbox1 checked = {self.checkbox1.checked}")
            with w.tr():
                with w.td():
                    self.checkbox2.render(w)
                with w.td():
                    w.text("checkbox (starts out checked)")
                with w.td():
                    w.text(f"checkbox2 checked = {self.checkbox2.checked}")
            with w.tr():
                with w.td():
                    self.text_input.render(w)
                with w.td():
                    w.text("text input, handles Enter and Esc")
                with w.td():
                    w.text(f"value = {self.text_input.value}")
            with w.tr():
                with w.td():
                    w.span("click me", onclick=self._handle_span_onclick)
                with w.td():
                    w.span("<span> with onclick")
            with w.tr():
                with w.td():
                    w.span("mouse over me", onmouseover=self._handle_span_onmouseover)
                with w.td():
                    w.span("<span> with onmouseover")

            with w.tr():
                with w.td():
                    w.button("click me", onclick=self._handle_button_onclick)
                with w.td():
                    w.text("button")

        w.h2("Debug output")
        with w.textarea(rows=10, cols=80):
            w.text(self.message)

    def _show_message(self, msg: str) -> None:
        self.message = msg
        logging.info(msg)

    def _handle_checkbox_onclick(self, ev: flyweb.MouseEvent):
        self._show_message(f"checkbox clicked: {ev}")

    def _handle_text_input_onblur(self, ev: flyweb.Event):
        self._show_message(f"text input onblur: {ev}")

    def _handle_text_input_custom_key_down(self, ev: flyweb.KeyboardEvent):
        self._show_message(f"text input custom key down: {ev}")
        if ev.get("key") == "Esc":
            self.text_input.value = flyweb.ForceValue("")

    def _handle_span_onclick(self, ev: flyweb.MouseEvent):
        self._show_message(f"span clicked: {ev}")

    def _handle_span_onmouseover(self, ev: flyweb.MouseEvent):
        self._show_message(f"span onmouseover: {ev}")

    def _handle_button_onclick(self, ev: flyweb.MouseEvent):
        self._show_message(f"button onclick: {ev}")


async def main(port=8000):
    example = MiscExample()
    server = flyweb.Server(example.render, port=port, extra_css=[_CSS])
    await server.run()


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    anyio.run(main)
