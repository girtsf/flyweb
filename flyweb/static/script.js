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
  const afterUpdateFunctions = [];

  for (const [k, v] of Object.entries(props)) {
    if (typeof v !== "object") {
      continue;
    }
    if (!Array.isArray(v)) {
      fixMagicalProps(v);
      continue;
    }
    if (v.length == 2 && v[0] == "_flyweb_event_handler") {
      props[k] = getMagicalEventHandler(v[1]);
    } else if (v.length == 3 && v[0] == "_flyweb_event_handler") {
      const fun = getMagicalEventHandler(v[1]);
      const handlerKey = v[2];
      props[k] = (ev) => fun(ev, handlerKey);
    } else if (v.length == 2 && v[0] == "_flyweb_eval") {
      if (!(v[1] in evalFunctions)) {
        evalFunctions[v[1]] = eval?.(`"use strict";(${v[1]})`);
      }
      props[k] = evalFunctions[v[1]];
      continue;
    } else if (v.length == 3 && v[0] == "_flyweb_force_value") {
      // Hack: special case to force value of the prop. This is needed for
      // cases like text input where the previous value might be "", then
      // user enters something, presses <Enter>, backend gets the new value
      // and wants to set the value back to "". MaquetteJS would not touch
      // the value since in its eyes it hadn't changed.
      //
      // So we attach an extra "afterUpdate" function that MaquetteJS will
      // call after the update and it that we set the value again ourselves.
      const forceId = v[1];
      const forceValue = v[2];
      props[k] = forceValue;
      // We create a function that will replace the prop value with the forced value and attach it to "afterUpdate".
      afterUpdateFunctions.push((element) => {
        if (element[k + "-previousForceId"] != forceId) {
          element[k] = forceValue;
          element[k + "-previousForceId"] = forceId;
        }
      });
    }
  }
  if (props._flyweb) {
    Object.assign(props, fixMagicalFlyWebProps(props._flyweb));
  }
  if (afterUpdateFunctions.length) {
    if (props.afterUpdate) {
      // an "afterUpdate" function already exists, make sure we call that one too.
      afterUpdateFunctions.push(props.afterUpdate);
    }
    props.afterUpdate = (...args) => {
      afterUpdateFunctions.forEach((fun) => {
        fun(...args);
      });
    };
  }
}

function fixMagicalFlyWebProps(flywebProps) {
  if (flywebProps.individualKeyDownHandlers) {
    return {
      onkeydown: (ev) =>
        individualKeyHandler(ev, flywebProps.individualKeyDownHandlers),
    };
  }
  return {};
}

function getBasicEventParameters(ev, handlerKey) {
  // "target" is the element that triggered the event
  // "currentTarget" is the event listener element
  const out = {
    type: ev.type,
    target_id: ev.currentTarget?.id,
    target_value: ev.currentTarget?.value,
  };
  if (handlerKey !== undefined) {
    out._flyweb_handler_key = handlerKey;
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
  let init = vdom === null;
  vdom = toMaquetteDom(msg);
  if (init) {
    projector.append(document.getElementById("flyweb-contents"), () => vdom);
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
