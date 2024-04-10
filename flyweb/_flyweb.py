#!/usr/bin/env python3

from __future__ import annotations

import collections
import contextlib
import dataclasses
import inspect
import logging
import time
import typing
from typing import Any, Callable, Protocol, Type, TypedDict

from typing_extensions import Unpack

logger = logging.getLogger("flyweb")


_EVAL = "_flyweb_eval"
_EVENT_HANDLER = "_flyweb_event_handler"
_FORCE_VALUE = "_flyweb_force_value"


class ForceValue:
    def __init__(self, value: str):
        self.value = value
        self._timestamp = time.time()

    def serialize(self) -> list[str | float]:
        return [_FORCE_VALUE, self._timestamp, self.value]

    def __repr__(self) -> str:
        return f"ForceValue({self.value!r})"


class FrontendFunction:
    """Function that runs in the browser.

    FrontendFunctions don't pass events to the backend.
    """

    def __init__(self, js: str):
        self.js = js


class Event(TypedDict, total=False):
    _flyweb_handler_key: str
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
    key: str
    keyCode: int


EventFunction = Callable[[Event], None]
FocusEventFunction = Callable[[FocusEvent], None]
MouseEventFunction = Callable[[MouseEvent], None]
KeyboardEventFunction = Callable[[KeyboardEvent], None]


class FlyWebProperties(TypedDict, total=False):
    # If present, register onkeydown on the frontend and generate events for
    # specified keys.
    individualKeyDownHandlers: dict[str, KeyboardEventFunction]


class DomNodeProperties(TypedDict, total=False):
    """Property names and types allowed on DOM nodes."""

    _flyweb: FlyWebProperties

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
    value: str | ForceValue
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
    children: list[str | DomNode] = dataclasses.field(default_factory=list)
    props: dict = dataclasses.field(default_factory=dict)

    def serialize(self) -> str | list[str | list | dict]:
        return _serialize(self)


def _serialize(x: str | DomNode) -> str | list[str | list | dict]:
    if isinstance(x, str):
        return x
    assert isinstance(x, DomNode)
    children = [_serialize(x) for x in x.children]
    return [x.tag, x.props, children]


def serialize(f: FlyWeb) -> list[str | list | dict]:
    serialized = f._root.serialize()
    assert isinstance(serialized, list)
    return serialized


@dataclasses.dataclass
class _DomNodeContext:
    path: list[str]
    children_ids: collections.Counter[str] = dataclasses.field(
        default_factory=collections.Counter
    )
    children_keys: set[str | int] = dataclasses.field(default_factory=set)


class _Renderable(Protocol):
    """Protocol for things that implement "render" method."""

    def render(self, w: FlyWeb) -> None:
        ...


class FlyWeb:
    def __init__(self):
        self._root = DomNode(tag="div")
        self._node: DomNode = self._root
        self._ctx = _DomNodeContext(path=["flyweb"])
        # Page title: if not None, the title will be updated to given value.
        self._title: str | None = None

        self._event_handlers: dict[str, EventFunction] = {}

    @contextlib.contextmanager
    def _dom_node_context(self, node: DomNode, path: list[str]):
        prev_node = self._node
        prev_ctx = self._ctx
        self._node = node
        self._ctx = _DomNodeContext(path)
        try:
            yield
        finally:
            self._node = prev_node
            self._ctx = prev_ctx

    def _fix_up_callables(
        self,
        d: dict[str, Any],
        path: list[str],
        *,
        use_handler_key: bool = False,
        type_class: Type[DomNodeProperties] | dict[str, Any] | None,
    ) -> None:
        if not d:
            return
        if "id" in d:
            id_ = d.get("id")
        else:
            id_ = "/".join(path)
        id_needed = False

        for name, value in d.items():
            if isinstance(value, FrontendFunction):
                d[name] = (_EVAL, value.js)
                continue
            elif isinstance(value, dict):
                d[name] = value.copy()
                if type_class:
                    value_annots = typing.get_type_hints(type_class).get(name)
                    child_type_class = value_annots
                else:
                    child_type_class = None
                self._fix_up_callables(
                    d[name],
                    path + [name],
                    use_handler_key=True,
                    type_class=child_type_class,
                )
                continue
            if not callable(value):
                continue

            # We get callable type by looking at the function, and by looking
            # at the props annotations. If they disagree, raise an error. If
            # function does not have annotations, use type from props.
            #
            # TODO: this could use some comments and unittesting.

            args_annots = inspect.get_annotations(value, eval_str=True)
            # value_annots is a dict with optional "return" key, and keys
            args_annots.pop("return", None)
            if len(args_annots) > 1:
                raise RuntimeError(f'event handler "{value}" has more than 1 arg')
            if args_annots:
                _, arg = args_annots.popitem()
            else:
                arg = None

            annot_arg = None
            if type_class:
                if typing.get_origin(type_class) is dict:
                    args = typing.get_args(type_class)
                    # args is [class 'str', typing.Callable[[...], ...]]
                    assert len(args) == 2
                    assert isinstance(args[1], typing.Callable)

                    args = typing.get_args(args[1])
                    # args is [[<args>], <return value>]
                    assert len(args) == 2
                    input_types, _ = args
                    assert len(input_types) == 1

                    annot_arg = input_types[0]

            if arg and annot_arg:
                if arg is not annot_arg:
                    # TODO: clean this up and make the error messages better.
                    raise RuntimeError(f"Mismatch between {arg=} and {annot_arg=}")

            if not arg:
                arg = annot_arg

            if not arg:
                event_handler_type = "no_args"
            elif arg is Event:
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
            handler_key = f"{id_}/{name}"
            self._event_handlers[handler_key] = value
            if use_handler_key:
                d[name] = [_EVENT_HANDLER, event_handler_type, handler_key]
            else:
                # We'll look up event by target id + "on" + event type.
                d[name] = [_EVENT_HANDLER, event_handler_type]
                id_needed = True
        if id_needed:
            d["id"] = id_

    def _fix_up_props(self, node_props: DomNodeProperties, path: list[str]) -> dict:
        props = typing.cast(dict, node_props)
        if "class_" in props:
            props["class"] = props.pop("class_")
        if "is_" in props:
            props["is"] = props.pop("is_")
        if "value" in props and isinstance(props["value"], ForceValue):
            props["value"] = props["value"].serialize()

        self._fix_up_callables(props, path, type_class=DomNodeProperties)
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

        handler_key = msg.get("_flyweb_handler_key")
        if not handler_key:
            handler_key = msg["target_id"] + "/" + "on" + msg["type"]
        handler = self._event_handlers.get(handler_key)
        if not handler:
            logger.warning(f"handler {handler_key} not found")
            return False

        # TODO: support async event handlers.
        logger.debug(f'handling event for "{handler_key}"')
        # TODO: validate that msg contains the right keys.
        handler(msg)  # type: ignore
        return True

    def set_title(self, title: str) -> None:
        self._title = title

    def text(self, txt: str) -> None:
        if not self._node.children:
            self._node.children = []
        self._node.children.append(txt)

    def _make_child_path(
        self, *, tag: str, id: str | None, key: int | str | None, type_: str | None
    ) -> list[str]:
        # If "id" is given, just use that.
        if id:
            return [id]
        p = tag
        if key is not None:
            if key in self._ctx.children_keys:
                raise RuntimeError(f'repeated key "{key}" under {self._ctx.path}')
            self._ctx.children_keys.add(key)
            p += f"[{key}]"
        else:
            if type_:
                p += f"[{type_}]"
            count = self._ctx.children_ids.get(p)
            self._ctx.children_ids[p] += 1
            if count:
                p += f"[{count}]"
        return self._ctx.path + [p]

    def elem(
        self, tag: str, *children: str | DomNode, **props: Unpack[DomNodeProperties]
    ):
        path = self._make_child_path(
            tag=tag, id=props.get("id"), key=props.get("key"), type_=props.get("type")
        )

        for c in children:
            if not isinstance(c, (str, DomNode)):
                raise TypeError(f"unexpected type for {path}: {c.__class__.__name__}")

        fixed_props = self._fix_up_props(props, path)

        node = DomNode(
            tag=tag,
            children=list(children) if children else [],
            props=fixed_props or {},
        )
        self._node.children.append(node)

        return self._dom_node_context(node, path)

    def add(self, renderable: _Renderable) -> None:
        renderable.render(self)

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
