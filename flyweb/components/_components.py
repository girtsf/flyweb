#!/usr/bin/env python3

from __future__ import annotations

from typing import Any, Callable, cast

from typing_extensions import Unpack

from flyweb import _flyweb


class Component:
    """Base class for components.

    A Component is a reusable class that emits one or more DomNodes when its
    "render" function is called. "render" function can be overridden in base
    classes, but by default, it will render as its html_tag, and take any
    instance variables that are not prefixed with "_" as its props.
    """

    def __init__(self, tag: str, **props: Unpack[_flyweb.DomNodeProperties]):
        self._tag = tag
        self._props = props

    @property
    def props(self) -> dict[str, Any]:
        return cast(dict[str, Any], self._props)

    def render(self, w: _flyweb.FlyWeb) -> None:
        w.elem(self._tag, **self._props)


class TextInput(Component):
    def __init__(
        self,
        *,
        value: str | None = None,
        on_enter_key: Callable[[str], None] | None = None,
        **props: Unpack[_flyweb.DomNodeProperties],
    ):
        props = props.copy()
        if "key" not in props:
            # Allow couple different <input> tags in one heirarchy without
            # having to manually specify "key" for them. Without this, maquette
            # blows up with "div had a input child added, but there is now more
            # than one". It would be nice to come up with a better way to do
            # this.
            props["key"] = "text"
        assert "onkeyup" not in props
        props["onkeyup"] = self._on_key_up
        assert "oninput" not in props
        props["oninput"] = self._on_input
        super().__init__("input", **props)

        self.value = value or ""
        self._on_enter_key = on_enter_key

    def render(self, w: _flyweb.FlyWeb) -> None:
        # I don't quite like this. It would be nice if it picked up "value"
        # automatically. Maybe it should grab all instance variables that don't
        # begin with "_" and stuff them in props?
        self.props["value"] = self.value
        super().render(w)

    # TODO: switch this to a client-side fragment that does this, otherwise we
    # might lose keystrokes when typing too fast.
    def _on_key_up(self, event: _flyweb.KeyboardEvent) -> None:
        if event.get("keyCode") == 13 and self._on_enter_key:
            self._on_enter_key(self.value)

    def _on_input(self, event: _flyweb.Event) -> None:
        if "target_value" in event:
            self.value = event["target_value"]


class CheckBox(Component):
    def __init__(
        self,
        *,
        checked: bool = False,
        **props: Unpack[_flyweb.DomNodeProperties],
    ):
        props = props.copy()
        if "key" not in props:
            props["key"] = "checkbox"
        assert "onclick" not in props
        props["onclick"] = self._on_click
        props["type"] = "checkbox"

        super().__init__("input", **props)
        self.checked = checked

    def render(self, w: _flyweb.FlyWeb) -> None:
        self.props["checked"] = self.checked
        super().render(w)

    def _on_click(self, _) -> None:
        self.checked = not self.checked
