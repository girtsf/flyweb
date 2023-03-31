#!/usr/bin/env python3

from __future__ import annotations

from typing import Any, cast

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
        self._original_onblur = props.get("onblur")
        props["onblur"] = self._on_blur
        props["value"] = value or ""
        super().__init__("input", **props)

        # TODO: implement a client-side <on key> that sends a custom event.

    @property
    def value(self) -> str:
        assert "value" in self._props
        return self._props["value"]

    @value.setter
    def value(self, value: str) -> None:
        self._props["value"] = value

    def _on_blur(self, event: _flyweb.FocusEvent) -> None:
        if "target_value" in event:
            self.value = event["target_value"]
        if self._original_onblur:
            self._original_onblur(event)


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
