# FlyWeb

FlyWeb is a smol live immediate-mode web framework for Python:

* *smol*: minimal dependencies (no frontend build required).
* *live*: updates are pushed to the browser in real time.
* *immediate-mode*: you write a function that emits HTML elements for the whole
  page, [immediate mode GUI](https://en.wikipedia.org/wiki/Immediate_mode_GUI)-style.
* *web framework*: FlyWeb takes care of sending the web page contents
  to the browser, and calling your Python event handlers magically.
* *Python*: 3.10+ and an ASGI server required.

## Examples

Here's a minimal program that renders a counter and an [INCREMENT] button:

```python
import asyncio
import flyweb

class Counter:
    def __init__(self):
        self._count = 0

    def render(self, w: flyweb.FlyWeb) -> None:
        with w.div():
            w.text(f"count is {self._count}")
        with w.div():
            w.button("INCREMENT", onclick=self._increment)

    def _increment(self, _) -> None:
        self._count += 1

async def main():
    counter = Counter()
    await flyweb.Server(counter.render, port=8000).run()

if __name__ == "__main__":
    asyncio.run(main())
```

There are a couple more examples under
[flyweb/examples](https://github.com/girtsf/flyweb/tree/main/flyweb/examples).

## Try it out

```
$ pip install 'flyweb[examples] @ git+https://github.com/girtsf/flyweb'
$ python -m flyweb.examples.todo
```

Then go to http://localhost:8000/.

## Design

Behind the scenes, FlyWeb works like this:
* Your `render` function builds up a virtual DOM.
* This virtual DOM gets serialized to JSON and sent to the frontend over
  socket.io. Any event handlers get converted to magic strings that say "hey
  frontend, please send me a message if this event happens".
* Frontend turns the JSON structure into a VDOM that
  [Maquette](https://maquettejs.org/) then turns into a real DOM.
* As you interact with the web page, events are sent to the backend,
  decoded, and matching event handlers are called. Your `render` function
  is called again, and the results are sent to the frontend. Maquette diffs the
  VDOMs and updates the real DOM with any changes that happened.

FlyWeb uses [anyio](https://github.com/agronholm/anyio) library (thus should
work with either built-in `asyncio` or
[trio](https://github.com/python-trio/trio) libraries).

## Limitations

FlyWeb is mostly intended as a quick way of adding simple web interfaces to
internal tools without having to do a bunch of scaffolding or frontend builds.
It probably won't be suitable for handling complex pages or many users.

Currently it assumes that you want to share the state between all the webpage
users. Implementing per-user state would not be too difficult.

Security: currently there is none, and it's probably pretty easy to crash the
backend if you try.

## Status

It works, at least for simple pages. The API is definitely not stable and will
likely change as it evolves.
