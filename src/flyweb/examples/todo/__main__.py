#!/usr/bin/env python3

from __future__ import annotations

import logging
import sys

import anyio
import flyweb
from flyweb import components

try:
    import hypercorn  # noqa: F401
except ImportError:
    raise RuntimeError("install extras with flyweb[examples] to run this!") from None


# CSS fragment that will be sent to frontend.
_CSS = """
h1 {
  color: #444;
  text-decoration: underline;
}
"""


class TodoList:
    """Example todo list application."""

    def __init__(self):
        self._items = {
            1: TodoItem(id=1, title="write code", completed=True, parent=self),
            2: TodoItem(id=2, title="write more code", parent=self),
        }
        self._add = components.TextInput(
            id="add",
            placeholder="do what?",
            clear_on_escape=True,
            on_enter=self.add_todo,
        )
        self._next_id = 3

    def delete_todo(self, id: int) -> None:
        if id in self._items:
            del self._items[id]

    def add_todo(self, title: str) -> None:
        if not title:
            return
        self._items[self._next_id] = TodoItem(
            id=self._next_id, title=title, parent=self
        )
        self._next_id += 1

    def render(self, w: flyweb.FlyWeb):
        with w.div():
            w.h1("To Do")

        with w.div():
            with w.ul():
                for item in self._items.values():
                    item.render(w)
            with w.span():
                w.text("add:")
                self._add.render(w)
                w.button("add", onclick=self._on_add_clicked)

    def _on_add_clicked(self, _: flyweb.MouseEvent) -> None:
        self.add_todo(self._add.value)
        self._add.value = flyweb.ForceValue("")


class TodoItem:
    def __init__(self, *, id: int, title: str, parent: TodoList, completed=False):
        self.id = id
        self.title = title
        self.parent = parent
        self._completed = components.CheckBox(key="checkbox", checked=completed)
        self._editing: components.TextInput | None = None

    def render(self, w: flyweb.FlyWeb):
        with w.li(key=self.id):
            with w.div():
                with w.label():
                    self._completed.render(w)
                    if self._editing:
                        self._editing.render(w)
                    else:
                        w.text(self.title)
                    w.elem("button", "edit", onclick=self._on_edit_clicked)
                    w.elem("button", "delete", onclick=self._on_delete_clicked)

    def _on_edit_clicked(self, _) -> None:
        self._editing = components.TextInput(
            key="edit",
            value=self.title,
            onblur=self._on_blur,
            on_enter=self._replace_title,
            # "afterCreate" is a maquette hook that gets called when the
            # element gets attached to the real DOM.
            # TODO: flesh out a more detailed example.
            afterCreate=flyweb.FrontendFunction("function(el) { el.focus(); }"),
        )

    def _replace_title(self, new_title: str) -> None:
        self.title = new_title
        self._editing = None

    def _on_blur(self, event: flyweb.Event) -> None:
        if "target_value" in event:
            self._replace_title(event["target_value"])

    def _on_enter_key(self, value: str) -> None:
        self.title = value
        self._editing = None

    def _on_delete_clicked(self, ev: flyweb.MouseEvent) -> None:
        self.parent.delete_todo(self.id)


async def main(port=8000):
    todo_list = TodoList()
    server = flyweb.Server(todo_list.render, port=port, extra_css=[_CSS])
    await server.run()


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    anyio.run(main)
