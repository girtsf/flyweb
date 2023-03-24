#!/usr/bin/env python3

from __future__ import annotations

import contextlib
import dataclasses
import typing
from typing import Any, Callable, TypedDict

from loguru import logger
from typing_extensions import Unpack

_EVENT_HANDLER_KEY = "__flyweb_event_handler_key__"
_EVAL = "__flyweb_eval__"


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
    tabindex: int
    disabled: bool
    title: str
    accesskey: str
    class_: str  # emitted as "class", since "class" is reserved in Python
    id: str
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
    minlength: int
    maxlength: int
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


@dataclasses.dataclass(kw_only=True, slots=True)
class DomNode:
    tag: str
    children: list[str | DomNode] = dataclasses.field(default_factory=list)
    props: dict = dataclasses.field(default_factory=lambda: {})

    def serialize(self) -> dict:
        return _serialize_dict(self)


def _make_js_function(event_var_mapping: dict[str, str], event_handler_key: str) -> str:
    # Function takes in event, returns a message to send to the backend.
    fn = [
        "function(e) {",
        "  e.preventDefault();",
        "  let msg = {};",
        f'  msg.{_EVENT_HANDLER_KEY} = "{event_handler_key}";',
    ]
    for msg_key, value_getter in event_var_mapping.items():
        fn += [
            f"  {{ let v = {value_getter};"
            f" if (v !== undefined) {{ msg.{msg_key} = v; }} }}"
        ]
    fn += [
        "  return msg;",
        "}",
    ]
    return "\n".join(fn)


def _serialize(x: DomNode | str) -> str | dict[str, str | list | dict]:
    if isinstance(x, str):
        return x
    elif not isinstance(x, DomNode):
        raise TypeError(f"unexpected node type: {x.__class__.__name__}")
    return _serialize_dict(x)


def _serialize_dict(x: DomNode) -> dict[str, str | list | dict]:
    out: dict[str, str | list | dict] = {
        "tag": x.tag,
    }
    if x.children:
        out["children"] = [_serialize(c) for c in x.children]
    if x.props:
        out["props"] = x.props
    return out


class FlyWeb:
    def __init__(self):
        self._dom = DomNode(tag="div")
        self._last = self._dom
        self._path = "flyweb"
        self._children_by_tag = {}
        self._event_handlers = {}

    @contextlib.contextmanager
    def _last_child_context(self, path: str):
        prev = self._last
        prev_children_by_tag = self._children_by_tag
        prev_path = self._path
        last_children = self._last.children
        assert last_children
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

    def _fix_up_props(self, node_props: DomNodeProperties, path: str) -> dict:
        props = typing.cast(dict, node_props.copy())
        if "class_" in props:
            props["class"] = props.pop("class_")

        property_types = typing.get_type_hints(DomNodeProperties)

        for name, value in props.items():
            if isinstance(value, FrontendFunction):
                props[name] = [_EVAL, value.js]
                continue
            if not callable(value):
                continue
            if name not in property_types:
                raise RuntimeError(f'unsupported event handler "{name}" ({path})')
            args = typing.get_args(property_types[name])
            # args is now something like:
            # ([<class 'flyweb._flyweb.FocusEvent'>], <class 'NoneType'>)
            assert len(args[0]) == 1
            handler_arg_type = args[0][0]

            # If "id" was given, use that to specify the event handler id.
            # Otherwise, use the generated path.
            if "id" in props:
                event_handler_key = props["id"] + "-" + name
            else:
                event_handler_key = path + "-" + name

            event_var_mapping = {
                "type": "e.type",
                "target_id": "e.target.id",
                "target_value": "e.target.value",
            }

            if handler_arg_type is FocusEvent:
                pass
            elif handler_arg_type is MouseEvent:
                event_var_mapping["detail"] = "e.detail"
                event_var_mapping["button"] = "e.button"
                event_var_mapping["buttons"] = "e.buttons"
            elif handler_arg_type is KeyboardEvent:
                event_var_mapping["detail"] = "e.detail"
                event_var_mapping["code"] = "e.code"
                event_var_mapping["keyCode"] = "e.keyCode"
                pass
            elif handler_arg_type is Event:
                pass
            else:
                raise RuntimeError(f"BUG: unexpected {handler_arg_type=}")

            # TODO: we might want to define the mappings in script.js to reduce
            # the amount of JS code we have to fling across and eval.
            fn = _make_js_function(event_var_mapping, event_handler_key)

            if event_handler_key in self._event_handlers:
                raise RuntimeError(
                    f'repeated event handler key "{event_handler_key}" in the dom tree'
                )
            self._event_handlers[event_handler_key] = props[name]
            props[name] = [_EVAL, fn]
        return props

    def _handle_event_from_frontend(self, msg: dict[str, Any]) -> bool:
        """Handles event, returns True iff there was an event handler."""
        handler_key = msg.get(_EVENT_HANDLER_KEY)
        if not handler_key:
            logger.error(f'missing "{_EVENT_HANDLER_KEY}" in event message')
            return False
        handler = self._event_handlers.get(handler_key)
        if not handler:
            logger.warning(f'missing "{_EVENT_HANDLER_KEY}" in event message')
            return False

        msg = msg.copy()
        del msg[_EVENT_HANDLER_KEY]

        # TODO: support async event handlers.
        logger.debug(f'handling event for "{handler_key}"')
        handler(msg)
        return True

    def text(self, txt: str) -> None:
        self._last.children.append(txt)

    def elem(
        self, tag: str, *children: str | DomNode, **props: Unpack[DomNodeProperties]
    ):
        path = self._path + "--" + tag
        if key := props.get("key"):
            path += f"_{key}"
        elif tag in self._children_by_tag:
            self._children_by_tag[tag] += 1
            path += str(self._children_by_tag[tag])
        else:
            self._children_by_tag[tag] = 1

        for c in children:
            if not isinstance(c, (str, DomNode)):
                raise TypeError(f"unexpected type for {path}: {c.__class__.__name__}")

        fixed_props = self._fix_up_props(props, path)

        vdom_node = DomNode(tag=tag, children=list(children), props=fixed_props)
        self._last.children.append(vdom_node)

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
