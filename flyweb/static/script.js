var vdom = null;
var sio = io();
var projector = maquette.createProjector();

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
    projector.append(document.body, render);
  } else {
    projector.scheduleRender();
  }
});

sio.on("disconnect", () => {
  vdom = maquette.h("div", {key: "__webfly_disconnected__"}, ["--disconnected--"]);
  projector.scheduleRender();
});
