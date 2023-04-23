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
    if (typeof v === "object") {
      if (Array.isArray(v)) {
        if (v.length == 2) {
          switch (v[0]) {
            case "__flyweb_event_handler":
              props[k] = getMagicalEventHandler(v[1]);
              break;
            case "__flyweb_eval":
              if (!(v[1] in evalFunctions)) {
                evalFunctions[v[1]] = eval?.(`"use strict";(${v[1]})`);
              }
              props[k] = evalFunctions[v[1]];
              break;
          }
        }
      }
    }
  }
}

function getBasicEventParameters(ev) {
  return {
    type: ev.type,
    target_id: ev.target?.id,
    target_value: ev.target?.value,
  };
}

function eventEventHandler(ev) {
  const msg = getBasicEventParameters(ev);
  sio.emit("event", msg);
}

function mouseEventHandler(ev) {
  const msg = {
    ...getBasicEventParameters(ev),
    detail: ev.detail,
    button: ev.button,
    buttons: ev.buttons,
  };
  sio.emit("event", msg);
}

function keyboardEventHandler(ev) {
  const msg = {
    ...getBasicEventParameters(ev),
    detail: ev.detail,
    code: ev.code,
    keyCode: ev.keyCode,
  };
  sio.emit("event", msg);
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
