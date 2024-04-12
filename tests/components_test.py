#!/usr/bin/env python3

import sys

import flyweb
import pytest
from flyweb import components


def _handler1(_: flyweb.Event) -> None:
    pass


def _handler2(_: flyweb.KeyboardEvent) -> None:
    pass


def _on_enter(_: str) -> None:
    pass


def test_textinput():
    w = flyweb.FlyWeb()
    w.add(components.TextInput())
    w.add(components.TextInput(value="foo"))
    w.add(
        components.TextInput(
            individual_key_down_handlers={"a": _handler1, "b": _handler2}
        )
    )
    w.add(components.TextInput(on_enter=_on_enter, clear_on_escape=True))

    out = flyweb.serialize(w)
    assert out == [
        "div",
        {},
        [
            [
                "input",
                {
                    "id": "flyweb/input",
                    "onblur": ["_flyweb_event_handler", "focus_event"],
                    "value": "",
                },
                [],
            ],
            [
                "input",
                {
                    "id": "flyweb/input[1]",
                    "onblur": ["_flyweb_event_handler", "focus_event"],
                    "value": "foo",
                },
                [],
            ],
            [
                "input",
                {
                    "_flyweb": {
                        "individualKeyDownHandlers": {
                            "a": [
                                "_flyweb_event_handler",
                                "keyboard_event",
                                "flyweb/input[2]/_flyweb/individualKeyDownHandlers/a",
                            ],
                            "b": [
                                "_flyweb_event_handler",
                                "keyboard_event",
                                "flyweb/input[2]/_flyweb/individualKeyDownHandlers/b",
                            ],
                        }
                    },
                    "id": "flyweb/input[2]",
                    "onblur": ["_flyweb_event_handler", "focus_event"],
                    "value": "",
                },
                [],
            ],
            [
                "input",
                {
                    "_flyweb": {
                        "individualKeyDownHandlers": {
                            "Enter": [
                                "_flyweb_event_handler",
                                "keyboard_event",
                                "flyweb/input[3]/_flyweb/individualKeyDownHandlers/Enter",  # noqa
                            ],
                            "Escape": [
                                "_flyweb_event_handler",
                                "keyboard_event",
                                "flyweb/input[3]/_flyweb/individualKeyDownHandlers/Escape",  # noqa
                            ],
                        }
                    },
                    "id": "flyweb/input[3]",
                    "onblur": ["_flyweb_event_handler", "focus_event"],
                    "value": "",
                },
                [],
            ],
        ],
    ]


def test_checkbox():
    w = flyweb.FlyWeb()
    w.add(components.CheckBox())
    w.add(components.CheckBox(checked=True, onclick=_handler1))

    out = flyweb.serialize(w)
    assert out == [
        "div",
        {},
        [
            [
                "input",
                {
                    "type": "checkbox",
                    "checked": False,
                    "id": "flyweb/input[checkbox]",
                    "onclick": ["_flyweb_event_handler", "mouse_event"],
                },
                [],
            ],
            [
                "input",
                {
                    "type": "checkbox",
                    "checked": True,
                    "id": "flyweb/input[checkbox][1]",
                    "onclick": ["_flyweb_event_handler", "mouse_event"],
                },
                [],
            ],
        ],
    ]


if __name__ == "__main__":
    pytest.main(sys.argv)
