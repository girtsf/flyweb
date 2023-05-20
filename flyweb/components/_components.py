#!/usr/bin/env python3

from __future__ import annotations

import functools
from typing import Any, cast

from typing_extensions import Unpack

from flyweb import _flyweb


class Component:
    """Base class for components.

    A Component is a reusable class that emits one or more DomNodes when its
    "render" function is called. "render" function can be overridden in base
    classes, but by default, it will render as its html_tag with props from
    _props.
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
    """Stateful <input type="text"> component.

    When the component loses focus ("onblur"), we receive the element's value
    from the frontend and store it in self.value.

    It's not recommended to use onkey* or oninput* events as they can "eat"
    characters, e.g. while the event caused by the first character is going to
    backend and back, a second character might get typed. Then response from
    the first character event comes back and overwrites the value without the
    additional character.

    To support reacting to <enter>, <esc> or other individual keys, you can use
    individual_key_down_handlers that are special-cased in the frontend. See
    https://developer.mozilla.org/en-US/docs/Web/API/UI_Events/Keyboard_event_key_values
    for "key" values.
    """

    def __init__(
        self,
        *,
        value: str | None = None,
        individual_key_down_handlers: dict[str, _flyweb.KeyboardEventFunction]
        | None = None,
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
        props["value"] = value or ""
        props["onblur"] = self._handle_on_blur
        if individual_key_down_handlers:
            self._individual_key_down_handlers = individual_key_down_handlers
            if not "__flyweb" in props:
                props["__flyweb"] = {}
            props["__flyweb"]["individualKeyDownHandlers"] = {
                k: functools.partial(self._handle_individual_key, v)
                for k, v in individual_key_down_handlers.items()
            }
        else:
            self._individual_key_down_handlers = None
        super().__init__("input", **props)

    @property
    def value(self) -> str:
        assert "value" in self._props
        return self._props["value"]

    @value.setter
    def value(self, value: str) -> None:
        self._props["value"] = value

    def _handle_individual_key(
        self, orig_handler: _flyweb.KeyboardEventFunction, event: _flyweb.KeyboardEvent
    ) -> None:
        if "target_value" in event:
            self.value = event["target_value"]
        orig_handler(event)

    def _handle_on_blur(self, event: _flyweb.FocusEvent) -> None:
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
        self._original_onclick = props.pop("onclick", None)
        props["onclick"] = self._handle_on_click
        props["type"] = "checkbox"

        super().__init__("input", **props)
        self.checked = checked

    def render(self, w: _flyweb.FlyWeb) -> None:
        self.props["checked"] = self.checked
        super().render(w)

    def _handle_on_click(self, event: _flyweb.MouseEvent) -> None:
        self.checked = not self.checked
        if self._original_onclick:
            self._original_onclick(event)
