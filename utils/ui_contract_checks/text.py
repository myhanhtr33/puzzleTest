from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any

from .types import Checker


def check_text(runner: Any, node: Any, check: dict[str, Any], contract: Any) -> str | None:
    from utils.ui_contracts import (
        _booster_amount_from_text, _coerce_bool_value, _decimal_from_text,
        _duration_seconds, _integer_from_text, _strip_markup,
    )

    target = runner.resolve_target(node, check.get("target"))
    actual = runner.read_text(target)
    if actual is None:
        return "target has no text attribute"
    text_format = str(check.get("format", "literal")).lower()
    cleaned = _strip_markup(actual)
    expected = check.get("amount", check.get("seconds", check.get("expected")))

    if text_format == "literal":
        expected_text = _strip_markup(check.get("expected"))
        left = cleaned if _coerce_bool_value(check.get("case_sensitive", True)) else cleaned.casefold()
        right = expected_text if _coerce_bool_value(check.get("case_sensitive", True)) else expected_text.casefold()
        if left != right:
            return f"expected text {expected_text!r}, got {cleaned!r} in {target} "
        return None

    if text_format == "price":
        expected_amount = Decimal(str(expected))
        actual_amount = _decimal_from_text(actual)
        if actual_amount != expected_amount:
            return f"expected price {expected_amount}, got {actual_amount} from {actual!r}"
        currencies = [str(currency).strip() for currency in check.get("currencies", [])]
        currency = next((item for item in currencies if item in cleaned), None)
        if currency is None:
            return f"expected one of currencies {currencies!r}, got {actual!r}"
        position = str(check.get("currency_position", "any")).lower()
        if position != "any":
            from utils.ui_contracts import _NUMBER_RE
            number_match = _NUMBER_RE.search(cleaned)
            token_index = cleaned.find(currency)
            if number_match is None:
                return f"could not locate price number in {actual!r}"
            if position == "prefix" and token_index > number_match.start():
                return f"expected currency prefix in {actual!r}"
            if position == "suffix" and number_match.end() > token_index:
                return f"expected currency suffix in {actual!r}"
        return None

    if text_format in {"gold_amount", "booster_amount"}:
        try:
            actual_value = (_integer_from_text(actual) if text_format == "gold_amount"
                            else _booster_amount_from_text(actual))
        except ValueError as exc:
            return str(exc)
        expected_value = int(Decimal(str(expected)))
        if actual_value != expected_value:
            label = "gold amount" if text_format == "gold_amount" else "booster amount"
            return f"expected {label}={expected_value}, got {actual_value} from {actual!r}"
        return None

    if text_format == "life_duration":
        duration = _duration_seconds(actual)
        rounding = str(check.get("rounding", "exact")).lower()
        if rounding == "floor":
            duration = duration.to_integral_value(rounding=ROUND_FLOOR)
        elif rounding == "ceil":
            duration = duration.to_integral_value(rounding=ROUND_CEILING)
        elif rounding == "nearest":
            duration = duration.to_integral_value(rounding=ROUND_HALF_UP)
        tolerance = Decimal(str(check.get("tolerance_seconds", 0)))
        expected_seconds = Decimal(str(expected))
        if abs(duration - expected_seconds) > tolerance:
            return f"expected life duration {expected_seconds}s, got {duration}s from {actual!r}"
        return None
    return f"unsupported text format {text_format!r}"


CHECKERS: dict[str, Checker] = {"text": check_text}
