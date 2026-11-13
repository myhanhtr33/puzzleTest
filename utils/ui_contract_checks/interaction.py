from __future__ import annotations

from typing import Any

from .types import Checker


def check_clickable(runner: Any, node: Any, check: dict[str, Any], contract: Any) -> str | None:
    from utils.ui_contracts import _coerce_bool_value

    expected = _coerce_bool_value(check.get("expected", True))
    actual = _coerce_bool_value(runner.read_attr(node, "clickable"))
    if actual != expected:
        return f"expected clickable={expected}, got {actual}"
    return None


def check_component_exists(runner: Any, node: Any, check: dict[str, Any], contract: Any) -> str | None:
    from utils.ui_contracts import _coerce_bool_value

    expected = _coerce_bool_value(check.get("expected", True))
    component = str(check.get("component", "")).strip()
    components = runner.read_attr(node, "components")
    if isinstance(components, str):
        components = [components]
    actual = isinstance(components, (list, tuple, set)) and component in {
        str(item) for item in components
    }
    if actual != expected:
        return f"expected component {component!r} existence={expected}, got {actual}; components={components!r}"
    return None


CHECKERS: dict[str, Checker] = {
    "clickable": check_clickable,
    "component_exists": check_component_exists,
}
