#!/usr/bin/env python3

import sys

import pytest

import flyweb


def _onclick(_: flyweb.Event) -> None:
    pass


def test_basic_rendering():
    w = flyweb.FlyWeb()
    with w.div(class_="a"):
        w.button("b", onclick=_onclick)
        w.button("b2", onclick=_onclick)
        w.text("c")
        with w.span(class_="d", id="d2"):
            w.text("e")
    assert flyweb.serialize(w) == [
        "div",
        {},
        [
            [
                "div",
                {"class": "a"},
                [
                    [
                        "button",
                        {
                            "onclick": ["_flyweb_event_handler", "event"],
                            "id": "flyweb/div/button",
                        },
                        ["b"],
                    ],
                    [
                        "button",
                        {
                            "onclick": ["_flyweb_event_handler", "event"],
                            "id": "flyweb/div/button[1]",
                        },
                        ["b2"],
                    ],
                    "c",
                    ["span", {"id": "d2", "class": "d"}, ["e"]],
                ],
            ]
        ],
    ]


if __name__ == "__main__":
    pytest.main(sys.argv)
