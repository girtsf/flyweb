#!/usr/bin/env python3

from __future__ import annotations

import contextlib
import dataclasses
import inspect
import logging
import typing
from typing import Any, Callable, TypedDict

from typing_extensions import Unpack

logger = logging.getLogger("flyweb")


_EVAL = "__flyweb_eval"
_EVENT_HANDLER = "__flyweb_event_handler"


class FrontendFunction:
    """Function that runs in the browser.

    FrontendFunctions don't pass events to the backend.
    """

    def __init__(self, js: str):
        self.js = js


class Event(TypedDict, total=False):
    type: str
    target_id: str
    # Set if "target" element has a "value" property.
    target_value: str


class UIEvent(Event):
    detail: int


class FocusEvent(UIEvent):
    pass


class MouseEvent(UIEvent):
    button: int
    buttons: int


class KeyboardEvent(UIEvent):
    code: str
    keyCode: int


EventFunction = Callable[[Event], None]
FocusEventFunction = Callable[[FocusEvent], None]
MouseEventFunction = Callable[[MouseEvent], None]
KeyboardEventFunction = Callable[[KeyboardEvent], None]


class DomNodeProperties(TypedDict, total=False):
    """Property names and types allowed on DOM nodes."""

    # Callbacks for Maquette interactions with DOM.
    afterCreate: FrontendFunction
    afterUpdate: FrontendFunction
    afterRemoved: FrontendFunction

    # Maquette-related things.
    key: str | int
    styles: dict[str, str]

    # This list is incomplete. I added stuff that was exposed in Maquette and
    # whatever else I needed. It would be good to find a way to autogenerate
    # this and put the properties in specific elements instead of having a
    # union of all of them here.
    # TODO: look at https://github.com/tawesoft/html5spec

    # HTMLFormElement:
    action: str
    encoding: str
    enctype: str
    method: str
    name: str
    target: str

    # HTMLAnchorElement:
    href: str
    rel: str

    # HTMLElement:
    onblur: FocusEventFunction
    onchange: EventFunction
    onclick: MouseEventFunction
    ondblclick: MouseEventFunction
    onfocus: FocusEventFunction
    oninput: EventFunction
    onkeydown: KeyboardEventFunction
    onkeypress: KeyboardEventFunction
    onkeyup: KeyboardEventFunction
    onmousedown: MouseEventFunction
    onmouseenter: MouseEventFunction
    onmouseleave: MouseEventFunction
    onmousemove: MouseEventFunction
    onmouseout: MouseEventFunction
    onmouseover: MouseEventFunction
    onmouseup: MouseEventFunction
    onsubmit: EventFunction

    spellcheck: bool
    tabIndex: int
    disabled: bool
    title: str
    accessKey: str
    class_: str  # emitted as "class", since "class" is reserved in Python
    id: str
    is_: str  # emitted as "is", since "is" is reserved in Python
    draggable: bool

    # HTMLInputElement:
    type: str
    autocomplete: str
    checked: bool
    placeholder: str
    # note: the property has capital "O", while the attribute doesn't.
    readOnly: bool
    src: str
    value: str
    size: int
    minLength: int
    maxLength: int
    pattern: str

    # HTMLImageElement:
    alt: str
    srcset: str

    # HTMLTableCellElement:
    colSpan: int
    rowSpan: int

    # HTMLTextAreaElement:
    rows: int
    cols: int

    innerHTML: str
    style: str

    # TODO: add the rest of event handlers and properties as needed.


@dataclasses.dataclass
class DomNode:
    tag: str
    children: list[str | DomNode] | None = None
    props: dict | None = None

    def serialize(self) -> str | list[str | list | dict]:
        return _serialize(self)


def _serialize(x: str | DomNode) -> str | list[str | list | dict]:
    if isinstance(x, str):
        return x
    assert isinstance(x, DomNode)
    children = [_serialize(x) for x in x.children or []]
    return [x.tag, x.props or {}, children]


class FlyWeb:
    def __init__(self):
        self._dom = DomNode(tag="div")
        self._last: DomNode = self._dom
        self._path = ["flyweb"]
        self._children_by_tag = {}
        self._event_handlers = {}

    @contextlib.contextmanager
    def _last_child_context(self, path: list[str]):
        prev = self._last
        prev_children_by_tag = self._children_by_tag
        prev_path = self._path
        assert self._last.children
        last_children = self._last.children
        last_child = last_children[-1]
        assert isinstance(last_child, DomNode)
        self._last = last_child
        self._path = path
        self._children_by_tag = {}
        try:
            yield
        finally:
            self._last = prev
            self._path = prev_path
            self._children_by_tag = prev_children_by_tag

    def _fix_up_callables(self, d: dict[str, Any], path: list[str]) -> None:
        id_ = d.get("id")
        for name, value in d.items():
            if isinstance(value, FrontendFunction):
                d[name] = (_EVAL, value.js)
                continue
            elif isinstance(value, dict):
                d[name] = value.copy()
                self._fix_up_callables(d[name], path + [name])
                continue
            if not callable(value):
                continue
            if not id_:
                id_ = "/".join(path)
            annots = inspect.get_annotations(value, eval_str=True)
            # annots is a dict with optional "return" key, and keys
            annots.pop("return", None)
            if len(annots) > 1:
                raise RuntimeError(f'event handler "{value}" has more than 1 arg')
            if not annots:
                event_handler_type = "no_args"
            else:
                _, arg = annots.popitem()
                if arg is Event:
                    event_handler_type = "event"
                elif arg is MouseEvent:
                    event_handler_type = "mouse_event"
                elif arg is FocusEvent:
                    event_handler_type = "focus_event"
                elif arg is KeyboardEvent:
                    event_handler_type = "keyboard_event"
                else:
                    raise RuntimeError(
                        f'event handler "{callable}" has'
                        f' unsupported arg type "{arg.__name__}"'
                    )

            self._event_handlers[id_, name] = value
            d[name] = (_EVENT_HANDLER, event_handler_type)
        if id_:
            d["id"] = id_

    def _fix_up_props(self, node_props: DomNodeProperties, path: list[str]) -> dict:
        props = typing.cast(dict, node_props)
        if "class_" in props:
            props["class"] = props.pop("class_")
        if "is_" in props:
            props["is"] = props.pop("is_")

        self._fix_up_callables(props, path)
        return props

    def _handle_event_from_frontend(self, msg: dict[str, Any]) -> bool:
        """Handles event, returns True iff there was an event handler."""
        logger.debug(f"event: {msg}")
        if "target_id" not in msg:
            logger.warning(f'missing "target_id" in event "{msg}"')
            return False
        if "type" not in msg:
            logger.warning(f'missing "type" in event "{msg}"')
            return False

        handler_key = msg["target_id"], "on" + msg["type"]
        handler = self._event_handlers.get(handler_key)
        if not handler:
            logger.warning(f"handler {handler_key} not found")
            return False

        # TODO: support async event handlers.
        logger.debug(f'handling event for "{handler_key}"')
        handler(msg)
        return True

    def text(self, txt: str) -> None:
        if not self._last.children:
            self._last.children = []
        self._last.children.append(txt)

    def _make_path(
        self, *, tag: str, id: str | None, key: int | str | None
    ) -> list[str]:
        if id:
            return [id]
        last = tag
        if key:
            last += f"[{key}]"
        elif tag in self._children_by_tag:
            self._children_by_tag[tag] += 1
            last += f"[{self._children_by_tag[tag]}]"
        else:
            self._children_by_tag[tag] = 1
        return self._path + [last]

    def elem(
        self, tag: str, *children: str | DomNode, **props: Unpack[DomNodeProperties]
    ):
        path = self._make_path(tag=tag, id=props.get("id"), key=props.get("key"))

        for c in children:
            if not isinstance(c, (str, DomNode)):
                raise TypeError(f"unexpected type for {path}: {c.__class__.__name__}")

        fixed_props = self._fix_up_props(props, path)

        node = DomNode(
            tag=tag,
            children=list(children) if children else None,
            props=fixed_props or None,
        )
        if not self._last.children:
            self._last.children = []
        self._last.children.append(node)

        return self._last_child_context(path)

    # The list of elements was imported from MDN after removing all deprecated
    # elements. Not all of the elements here will be useful.

    def a(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("a", *children, **props)

    def abbr(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("abbr", *children, **props)

    def address(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("address", *children, **props)

    def area(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("area", *children, **props)

    def article(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("article", *children, **props)

    def aside(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("aside", *children, **props)

    def audio(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("audio", *children, **props)

    def b(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("b", *children, **props)

    def base(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("base", *children, **props)

    def bdi(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("bdi", *children, **props)

    def bdo(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("bdo", *children, **props)

    def blockquote(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("blockquote", *children, **props)

    def body(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("body", *children, **props)

    def br(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("br", *children, **props)

    def button(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("button", *children, **props)

    def canvas(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("canvas", *children, **props)

    def caption(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("caption", *children, **props)

    def cite(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("cite", *children, **props)

    def code(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("code", *children, **props)

    def col(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("col", *children, **props)

    def colgroup(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("colgroup", *children, **props)

    def data(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("data", *children, **props)

    def datalist(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("datalist", *children, **props)

    def dd(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("dd", *children, **props)

    def del_(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("del", *children, **props)

    def details(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("details", *children, **props)

    def dfn(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("dfn", *children, **props)

    def dialog(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("dialog", *children, **props)

    def div(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("div", *children, **props)

    def dl(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("dl", *children, **props)

    def dt(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("dt", *children, **props)

    def em(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("em", *children, **props)

    def embed(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("embed", *children, **props)

    def fieldset(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("fieldset", *children, **props)

    def figcaption(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("figcaption", *children, **props)

    def figure(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("figure", *children, **props)

    def footer(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("footer", *children, **props)

    def form(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("form", *children, **props)

    def h1(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("h1", *children, **props)

    def h2(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("h2", *children, **props)

    def h3(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("h3", *children, **props)

    def h4(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("h4", *children, **props)

    def h5(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("h5", *children, **props)

    def h6(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("h6", *children, **props)

    def head(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("head", *children, **props)

    def header(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("header", *children, **props)

    def hgroup(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("hgroup", *children, **props)

    def hr(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("hr", *children, **props)

    def html(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("html", *children, **props)

    def i(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("i", *children, **props)

    def iframe(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("iframe", *children, **props)

    def img(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("img", *children, **props)

    def input(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("input", *children, **props)

    def ins(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("ins", *children, **props)

    def kbd(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("kbd", *children, **props)

    def label(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("label", *children, **props)

    def legend(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("legend", *children, **props)

    def li(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("li", *children, **props)

    def link(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("link", *children, **props)

    def main(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("main", *children, **props)

    def map(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("map", *children, **props)

    def mark(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("mark", *children, **props)

    def menu(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("menu", *children, **props)

    def meta(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("meta", *children, **props)

    def meter(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("meter", *children, **props)

    def nav(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("nav", *children, **props)

    def noscript(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("noscript", *children, **props)

    def object(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("object", *children, **props)

    def ol(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("ol", *children, **props)

    def optgroup(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("optgroup", *children, **props)

    def option(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("option", *children, **props)

    def output(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("output", *children, **props)

    def p(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("p", *children, **props)

    def picture(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("picture", *children, **props)

    def pre(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("pre", *children, **props)

    def progress(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("progress", *children, **props)

    def q(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("q", *children, **props)

    def rp(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("rp", *children, **props)

    def rt(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("rt", *children, **props)

    def ruby(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("ruby", *children, **props)

    def s(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("s", *children, **props)

    def samp(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("samp", *children, **props)

    def script(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("script", *children, **props)

    def section(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("section", *children, **props)

    def select(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("select", *children, **props)

    def slot(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("slot", *children, **props)

    def small(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("small", *children, **props)

    def source(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("source", *children, **props)

    def span(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("span", *children, **props)

    def strong(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("strong", *children, **props)

    def style(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("style", *children, **props)

    def sub(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("sub", *children, **props)

    def summary(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("summary", *children, **props)

    def sup(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("sup", *children, **props)

    def table(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("table", *children, **props)

    def tbody(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("tbody", *children, **props)

    def td(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("td", *children, **props)

    def template(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("template", *children, **props)

    def textarea(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("textarea", *children, **props)

    def tfoot(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("tfoot", *children, **props)

    def th(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("th", *children, **props)

    def thead(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("thead", *children, **props)

    def time(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("time", *children, **props)

    def title(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("title", *children, **props)

    def tr(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("tr", *children, **props)

    def track(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("track", *children, **props)

    def u(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("u", *children, **props)

    def ul(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("ul", *children, **props)

    def var(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("var", *children, **props)

    def video(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("video", *children, **props)

    def wbr(self, *children: str | DomNode, **props: Unpack[DomNodeProperties]):
        return self.elem("wbr", *children, **props)
