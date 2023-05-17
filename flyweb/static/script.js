var vdom = null;
var sio = io();
var projector = maquette.createProjector();

window.addEventListener("error", (event) => {
  console.log("Caught top-level error", event.error);
  let err = event.error.stack;
  if (event.error.error) {
    err = event.error.error.stack;
  }
  document.getElementById("flyweb-error-messages").innerText = err;
  document.getElementById("flyweb-error").showModal();
});

// Recursively replaces a [tag, props, children] from backend with nested
// Maquette VDOM.
function toMaquetteDom(thing) {
  if (typeof thing === "string") {
    return thing;
  }
  if (!Array.isArray(thing) || thing.length != 3) {
    throw new Error("expected an array of size 3, got: " + thing);
  }
  let [tag, props, children] = thing;
  fixMagicalProps(props || {});
  children = (children || []).map((x) => toMaquetteDom(x));
  return maquette.h(tag, props, children);
}

// Cache of functions we've already evaluated.
var evalFunctions = {};

function fixMagicalProps(props) {
  for (const [k, v] of Object.entries(props)) {
    if (typeof v !== "object") {
      continue;
    }
    if (!Array.isArray(v)) {
      fixMagicalProps(v);
      continue;
    }
    if (v.length == 2 && v[0] == "__flyweb_event_handler") {
      props[k] = getMagicalEventHandler(v[1]);
    } else if (v.length == 3 && v[0] == "__flyweb_event_handler") {
      const fun = getMagicalEventHandler(v[1]);
      const handlerKey = v[2];
      props[k] = (ev) => fun(ev, handlerKey);
    } else if (v.length == 2 && v[0] == "__flyweb_eval") {
      if (!(v[1] in evalFunctions)) {
        evalFunctions[v[1]] = eval?.(`"use strict";(${v[1]})`);
      }
      props[k] = evalFunctions[v[1]];
      break;
    }
  }
  if (props.__flyweb) {
    Object.assign(props, fixMagicalFlyWebProps(props.__flyweb));
  }
}

function fixMagicalFlyWebProps(flywebProps) {
  if (flywebProps.individualKeyDownHandlers) {
    return {
      onkeydown: (ev) => individualKeyHandler(ev, flywebProps.individualKeyDownHandlers),
    };
  }
  return {};
}

function getBasicEventParameters(ev, handlerKey) {
  const out = {
    type: ev.type,
    target_id: ev.target?.id,
    target_value: ev.target?.value,
  };
  if (handlerKey !== undefined) {
    out.__flyweb_handler_key = handlerKey;
  }
  return out;
}

function eventEventHandler(ev, handlerKey) {
  const msg = getBasicEventParameters(ev, handlerKey);
  sio.emit("event", msg);
}

function mouseEventHandler(ev, handlerKey) {
  const msg = {
    ...getBasicEventParameters(ev, handlerKey),
    detail: ev.detail,
    button: ev.button,
    buttons: ev.buttons,
  };
  sio.emit("event", msg);
}

function keyboardEventHandler(ev, handlerKey) {
  const msg = {
    ...getBasicEventParameters(ev, handlerKey),
    detail: ev.detail,
    code: ev.code,
    key: ev.key,
    keyCode: ev.keyCode,
  };
  sio.emit("event", msg);
}

function individualKeyHandler(ev, handlers) {
  const handler = handlers[ev.key];
  if (handler) {
    handler(ev);
  }
}

function getMagicalEventHandler(name) {
  switch (name) {
    case "no_args":
    case "event":
    case "focus_event":
      return eventEventHandler;
    case "mouse_event":
      return mouseEventHandler;
    case "keyboard_event":
      return keyboardEventHandler;
    default:
      throw new Error(`unsupported event handler: "${name}"`);
  }
}

sio.on("update", (msg) => {
  let init = (vdom === null);
  vdom = toMaquetteDom(msg);
  if (init) {
    projector.append(
      document.getElementById('flyweb-contents'),
      () => vdom,
    );
  } else {
    projector.scheduleRender();
  }
});

sio.on("connect", () => {
  document.getElementById("flyweb-disconnected").close();
});

sio.on("disconnect", () => {
  document.getElementById("flyweb-disconnected").showModal();
});
