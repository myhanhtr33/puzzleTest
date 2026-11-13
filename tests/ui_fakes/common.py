from __future__ import annotations


class FakeNode:
    def __init__(self, name: str, attrs=None, text=None, exists: bool = True, on_click=None):
        self.name = name
        self.attrs = dict(attrs or {})
        self.text = text
        self._exists = exists
        self._children = []
        self._on_click = on_click
        self.click_count = 0

    def add(self, child: "FakeNode") -> "FakeNode":
        self._children.append(child)
        return child

    def children(self):
        return self._children

    def exists(self) -> bool:
        return self._exists

    def offspring(self, name: str) -> "FakeNode":
        if not self._exists:
            return FakeNode(name, exists=False)

        queue = list(self._children)
        while queue:
            child = queue.pop(0)
            if child.name == name:
                return child
            queue.extend(child._children)

        return FakeNode(name, exists=False)

    def attr(self, name: str):
        return self.attrs.get(name)

    def get_text(self):
        return self.text

    def click(self, *args, **kwargs):
        if not self._exists:
            raise RuntimeError(f"cannot click absent node {self.name!r}")
        self.click_count += 1
        if self._on_click is not None:
            return self._on_click(self)
        return None

    def __len__(self):
        return 1 if self._exists else 0


class FakePoco:
    def __init__(self, roots, invoke_handler=None):
        self.roots = {root.name: root for root in roots}
        self.invoke_handler = invoke_handler
        self.invocations = []

    def __call__(self, name: str) -> FakeNode:
        return self.roots.get(name, FakeNode(name, exists=False))

    def freeze(self):
        return self

    def invoke(self, listener: str, **kwargs):
        self.invocations.append((listener, kwargs))
        if self.invoke_handler is None:
            raise NotImplementedError(f"no fake Poco handler for {listener!r}")
        return self.invoke_handler(listener, kwargs)
