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

// Recursively replaces a dict from backend with nested Maquette VDOM.
function toMaquetteDom(thing) {
  if (typeof thing == "string") {
    return thing;
  }
  if (typeof thing != "object") {
    console.log("unexpected:", thing);
    return;
  }
  var children = [];
  if (thing.children != null) {
    children = thing.children.map((x) => toMaquetteDom(x));
  }
  var props = {};
  if (thing.props !== null) {
    // Copy props so we don't modify the input.
    props = {...thing.props};
  }
  // Walk through props and eval anything that looks like ["__flyweb_eval__",
  // "..."], then wrap that in a function that sends out the result of that
  // function to the backend.
  for (const [k, v] of Object.entries(props)) {
    if (v[0] === "__flyweb_eval__") {
      const fun = eval?.(`"use strict";(${v[1]})`);
      props[k] = (event) => {
        // Call the evaluated function.
        const maybeMsg = fun(event);
        // If it returned something, send it to the backend.
        if (maybeMsg) {
          sio.emit("event", maybeMsg);
        }
      };
    }
  }

  return maquette.h(thing.tag, props, children);
}

function render() {
  return vdom;
}

sio.on("update", (msg) => {
  let init = (vdom === null);
  vdom = toMaquetteDom(msg);
  if (init) {
    projector.append(document.getElementById('flyweb-contents'), render);
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
