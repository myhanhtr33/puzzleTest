from __future__ import annotations

from typing import Any, Callable, Protocol


class CheckerRunner(Protocol):
    poco: Any

    def resolve_target(self, node: Any, raw_target: Any) -> Any: ...
    def read_attr(self, node: Any, name: str) -> Any: ...
    def read_text(self, node: Any) -> str | None: ...


Checker = Callable[[CheckerRunner, Any, dict[str, Any], Any], str | None]
