from __future__ import annotations

from typing import Any

from .types import Checker


def check_child_count(runner: Any, node: Any, check: dict[str, Any], contract: Any) -> str | None:
    target = runner.resolve_target(node, check.get("target"))
    expected = int(check.get("expected", check.get("childCount")))
    actual = len(target.children())
    if actual != expected:
        return f"expected direct child count={expected}, got {actual}"
    return None


CHECKERS: dict[str, Checker] = {"child_count": check_child_count}
