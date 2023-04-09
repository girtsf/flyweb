#!/usr/bin/env python3

import sys

import pytest

import flyweb


def _onclick(_: flyweb.Event) -> None:
    pass


def test_fixme():
    w = flyweb.FlyWeb()
    with w.div(class_="a"):
        w.button("b", onclick=_onclick)
        with w.span(class_="c", id="c2"):
            w.text("d")
    result = w._dom.serialize()
    assert result
    assert result["tag"] == "div"
    assert "props" not in result
    assert result["children"]


if __name__ == "__main__":
    pytest.main(sys.argv)
