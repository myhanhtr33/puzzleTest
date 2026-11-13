from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import zlib
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import unquote, unquote_to_bytes
from xml.etree import ElementTree


SCHEMA_VERSION = 2
PATH_MODES = {"name_chain", "offspring", "same"}
CARDINALITIES = {"unique", "one_or_more", "any"}
TEXT_FORMATS = {"literal", "price", "gold_amount", "life_duration", "booster_amount"}
CONTRACT_TYPES = {"ui", "reward", "button"}
BUTTON_TYPES = {"buy", "ads", "claim"}
AMOUNT_UNITS = {"count", "seconds"}


class ManifestError(ValueError):
    pass


class ResolutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class PathSpec:
    mode: str
    names: tuple[str, ...]

    @classmethod
    def from_raw(cls, mode: Any, raw: Any, field: str = "path") -> "PathSpec":
        mode = str(mode or "").strip().lower()
        if mode not in PATH_MODES:
            raise ManifestError(f"{field}: pathMode must be one of {sorted(PATH_MODES)}")

        names = _path_names(raw, field)
        if mode == "same":
            if names:
                raise ManifestError(f"{field}: pathMode=same cannot contain path segments")
            return cls(mode, ())
        if not names:
            raise ManifestError(f"{field}: path must contain at least one name")
        return cls(mode, tuple(names))

    def to_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "names": list(self.names)}


@dataclass(frozen=True)
class UIContract:
    test_id: str
    base: str | None
    path: PathSpec
    exist: bool
    checks: tuple[dict[str, Any], ...]
    cardinality: str = "unique"
    label: str = ""
    source_id: str = ""
    contract_type: str = "ui"
    reward_id: str | None = None
    amount: int | float | str | None = None
    amount_unit: str | None = None
    amount_text_ref: str | None = None
    button_type: str | None = None
    product_id: str | None = None
    price: str | None = None
    grants: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result = {
            "testId": self.test_id,
            "base": self.base,
            "path": self.path.to_dict(),
            "exist": self.exist,
            "checks": list(self.checks),
            "cardinality": self.cardinality,
        }
        if self.contract_type != "ui":
            result["contractType"] = self.contract_type
        if self.reward_id is not None:
            result["rewardId"] = self.reward_id
        if self.amount is not None:
            result["amount"] = self.amount
        if self.amount_unit is not None:
            result["amountUnit"] = self.amount_unit
        if self.amount_text_ref is not None:
            result["amountTextRef"] = self.amount_text_ref
        if self.button_type is not None:
            result["buttonType"] = self.button_type
        if self.product_id is not None:
            result["productId"] = self.product_id
        if self.price is not None:
            result["price"] = self.price
        if self.contract_type == "button":
            result["grants"] = list(self.grants)
        return result


@dataclass(frozen=True)
class ContractAssertion:
    test_id: str
    assertion: str
    passed: bool
    message: str


@dataclass
class ContractReport:
    assertions: list[ContractAssertion]

    @property
    def passed(self) -> bool:
        return all(assertion.passed for assertion in self.assertions)

    @property
    def failures(self) -> list[ContractAssertion]:
        return [assertion for assertion in self.assertions if not assertion.passed]

    def format(self) -> str:
        if self.passed:
            return f"UI contract passed ({len(self.assertions)} assertions)."
        lines = [
            f"UI contract failed ({len(self.failures)} of {len(self.assertions)} assertions):"
        ]
        lines.extend(
            f"- {failure.test_id} [{failure.assertion}]: {failure.message}"
            for failure in self.failures
        )
        return "\n".join(lines)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ManifestError(f"{field}: expected a boolean, got {value!r}")


def _path_names(raw: Any, field: str) -> list[str]:
    if isinstance(raw, Mapping):
        raw = raw.get("names", raw.get("segments", raw.get("path")))

    if isinstance(raw, (list, tuple)):
        names = [str(item).strip() for item in raw]
    else:
        text = str(raw or "").strip()
        if text in {"", ".", "parent"}:
            return []
        if text.startswith("["):
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ManifestError(f"{field}: invalid JSON path list: {exc.msg}") from exc
            if not isinstance(decoded, list):
                raise ManifestError(f"{field}: JSON path must be an array")
            names = [str(item).strip() for item in decoded]
        else:
            names = [part.strip() for part in text.lstrip("/").split("/")]

    if any(not name for name in names):
        raise ManifestError(f"{field}: path segments cannot be empty")
    return names


def _json_checks(raw: Any, field: str) -> tuple[dict[str, Any], ...]:
    if raw is None or raw == "":
        return ()
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ManifestError(f"{field}: invalid checks JSON: {exc.msg}") from exc
    if not isinstance(raw, list):
        raise ManifestError(f"{field}: checks must be a JSON array")
    checks: list[dict[str, Any]] = []
    for index, check in enumerate(raw):
        if not isinstance(check, dict):
            raise ManifestError(f"{field}[{index}]: each check must be an object")
        checks.append(check)
    return tuple(checks)


def _json_string_list(raw: Any, field: str) -> tuple[str, ...]:
    if raw is None or raw == "":
        return ()
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ManifestError(f"{field}: invalid JSON array: {exc.msg}") from exc
    if not isinstance(raw, (list, tuple)):
        raise ManifestError(f"{field}: expected a JSON array")
    values = tuple(str(value).strip() for value in raw)
    if any(not value for value in values):
        raise ManifestError(f"{field}: values cannot be empty")
    if len(set(values)) != len(values):
        raise ManifestError(f"{field}: values must be unique")
    return values


def _json_object_list(raw: Any, field: str) -> tuple[dict[str, Any], ...]:
    if raw is None or raw == "":
        return ()
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ManifestError(f"{field}: invalid JSON array: {exc.msg}") from exc
    if not isinstance(raw, (list, tuple)):
        raise ManifestError(f"{field}: expected a JSON array")
    if any(not isinstance(item, Mapping) for item in raw):
        raise ManifestError(f"{field}: every item must be an object")
    return tuple(dict(item) for item in raw)


def _normalized_amount(value: Any, field: str) -> int | float:
    _check_number(value, field)
    number = Decimal(str(value))
    if number == number.to_integral_value():
        return int(number)
    return float(number)


def _check_number(value: Any, field: str) -> None:
    if isinstance(value, bool) or value is None:
        raise ManifestError(f"{field}: expected a number")
    try:
        Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ManifestError(f"{field}: expected a number, got {value!r}") from exc


def _validate_target(target: Any, field: str) -> None:
    if target is None:
        return
    if isinstance(target, Mapping):
        mode = target.get("type", target.get("pathMode", target.get("mode", "offspring")))
        raw_path = target.get("names", target.get("path", target.get("segments")))
    else:
        mode = "offspring"
        raw_path = target
    PathSpec.from_raw(mode, raw_path, field)


def _validate_checks(checks: tuple[dict[str, Any], ...], field: str) -> None:
    texture_checks = [check for check in checks if str(check.get("type", "")).strip() == "texture"]
    image_match_checks = [check for check in checks if str(check.get("type", "")).strip() == "texture_image_match"]
    if len(texture_checks) > 1:
        raise ManifestError(f"{field}: an object can have at most one texture check")
    if image_match_checks and len(texture_checks) != 1:
        raise ManifestError(f"{field}: texture_image_match requires exactly one texture check")

    for index, check in enumerate(checks):
        check_type = str(check.get("type", "")).strip()
        check_field = f"{field}[{index}]"
        if not check_type:
            raise ManifestError(f"{check_field}: type is required")

        if check_type == "texture":
            if not str(check.get("expected", "")).strip():
                raise ManifestError(f"{check_field}: texture expected is required")
            _validate_target(check.get("target"), f"{check_field}.target")
        elif check_type == "texture_image_match":
            if not str(check.get("image", check.get("image_path", ""))).strip():
                raise ManifestError(f"{check_field}: image path is required")
            if "threshold" in check:
                _check_number(check["threshold"], f"{check_field}.threshold")
                threshold = float(check["threshold"])
                if not 0 <= threshold <= 1:
                    raise ManifestError(f"{check_field}.threshold: expected a value from 0 to 1")
        elif check_type == "clickable":
            if "expected" in check:
                _parse_bool(check["expected"], f"{check_field}.expected")
        elif check_type == "component_exists":
            if not str(check.get("component", "")).strip():
                raise ManifestError(f"{check_field}: component is required")
            if "expected" in check:
                _parse_bool(check["expected"], f"{check_field}.expected")
        elif check_type == "child_count":
            if "expected" not in check and "childCount" not in check:
                raise ManifestError(f"{check_field}: expected child count is required")
            expected = check.get("expected", check.get("childCount"))
            _check_number(expected, f"{check_field}.expected")
            if Decimal(str(expected)) < 0 or Decimal(str(expected)) % 1 != 0:
                raise ManifestError(f"{check_field}.expected: child count must be a non-negative integer")
            _validate_target(check.get("target"), f"{check_field}.target")
        elif check_type == "text":
            text_format = str(check.get("format", "literal")).strip().lower()
            if text_format not in TEXT_FORMATS:
                raise ManifestError(
                    f"{check_field}.format: expected one of {sorted(TEXT_FORMATS)}"
                )
            _validate_target(check.get("target"), f"{check_field}.target")
            if text_format == "literal" and "expected" not in check:
                raise ManifestError(f"{check_field}: literal text expected is required")
            if text_format == "price":
                if "amount" not in check and "expected" not in check:
                    raise ManifestError(f"{check_field}: price amount is required")
                currencies = check.get("currencies", [])
                if not isinstance(currencies, list) or not currencies or not all(
                    str(currency).strip() for currency in currencies
                ):
                    raise ManifestError(f"{check_field}: price currencies must be non-empty")
                position = str(check.get("currency_position", "any")).lower()
                if position not in {"any", "prefix", "suffix"}:
                    raise ManifestError(
                        f"{check_field}.currency_position: expected any, prefix, or suffix"
                    )
                _check_number(check.get("amount", check.get("expected")), f"{check_field}.amount")
            elif text_format == "life_duration":
                if "seconds" not in check and "expected" not in check:
                    raise ManifestError(f"{check_field}: life_duration seconds is required")
                _check_number(
                    check.get("seconds", check.get("expected")), f"{check_field}.seconds"
                )
                rounding = str(check.get("rounding", "exact")).lower()
                if rounding not in {"exact", "floor", "ceil", "nearest"}:
                    raise ManifestError(
                        f"{check_field}.rounding: expected exact, floor, ceil, or nearest"
                    )
            elif text_format in {"gold_amount", "booster_amount"}:
                if "amount" not in check and "expected" not in check:
                    raise ManifestError(f"{check_field}: {text_format} amount is required")
                _check_number(
                    check.get("amount", check.get("expected")), f"{check_field}.amount"
                )


def _contract_from_mapping(mapping: Mapping[str, Any], index: int) -> UIContract:
    if not isinstance(mapping, Mapping):
        raise ManifestError(f"objects[{index}]: expected an object")
    test_id = str(mapping.get("testId", mapping.get("test_id", ""))).strip()
    field = f"objects[{index}]"
    if not test_id:
        raise ManifestError(f"{field}: testId is required")

    raw_path = mapping.get("path")
    path_mapping = raw_path if isinstance(raw_path, Mapping) else None
    mode = mapping.get("pathMode", mapping.get("path_mode"))
    if mode is None and path_mapping:
        mode = path_mapping.get("mode", path_mapping.get("pathMode"))
    if mode is None:
        raise ManifestError(f"{field}: pathMode is required")
    if path_mapping:
        raw_path = path_mapping.get("names", path_mapping.get("segments", path_mapping.get("path")))

    base_raw = mapping.get("base")
    base = str(base_raw).strip() if base_raw is not None and base_raw != "" else None
    path = PathSpec.from_raw(mode, raw_path, f"{field}.path")
    exist = _parse_bool(mapping.get("exist"), f"{field}.exist")
    checks = _json_checks(mapping.get("checks", []), f"{field}.checks")
    if "childCount" in mapping:
        checks += ({"type": "child_count", "expected": mapping["childCount"]},)
    _validate_checks(checks, f"{field}.checks")
    cardinality = str(mapping.get("cardinality", "unique")).strip().lower()
    if cardinality not in CARDINALITIES:
        raise ManifestError(f"{field}.cardinality: expected one of {sorted(CARDINALITIES)}")

    contract_type = str(mapping.get("contractType", mapping.get("contract_type", "ui"))).strip().lower()
    if contract_type not in CONTRACT_TYPES:
        raise ManifestError(f"{field}.contractType: expected one of {sorted(CONTRACT_TYPES)}")

    reward_id_raw = mapping.get("rewardId", mapping.get("reward_id"))
    reward_id = str(reward_id_raw).strip() if reward_id_raw not in (None, "") else None
    amount_raw = mapping.get("amount")
    amount = _normalized_amount(amount_raw, f"{field}.amount") if amount_raw not in (None, "") else None
    amount_unit_raw = mapping.get("amountUnit", mapping.get("amount_unit"))
    amount_unit = str(amount_unit_raw).strip().lower() if amount_unit_raw not in (None, "") else None
    amount_text_ref_raw = mapping.get("amountTextRef", mapping.get("amount_text_ref"))
    amount_text_ref = (
        str(amount_text_ref_raw).strip()
        if amount_text_ref_raw not in (None, "")
        else None
    )
    button_type_raw = mapping.get("buttonType", mapping.get("button_type"))
    button_type = str(button_type_raw).strip().lower() if button_type_raw not in (None, "") else None
    product_id_raw = mapping.get("productId", mapping.get("product_id"))
    product_id = str(product_id_raw).strip() if product_id_raw not in (None, "") else None
    price_raw = mapping.get("price")
    price = str(price_raw).strip() if price_raw not in (None, "") else None
    grants = _json_string_list(mapping.get("grants", []), f"{field}.grants")

    if contract_type == "reward":
        if not reward_id:
            raise ManifestError(f"{field}.rewardId: required for a reward node")
        if amount is None:
            raise ManifestError(f"{field}.amount: required for a reward node")
        amount_unit = amount_unit or "count"
        if amount_unit not in AMOUNT_UNITS:
            raise ManifestError(f"{field}.amountUnit: expected one of {sorted(AMOUNT_UNITS)}")
        if amount is not None and Decimal(str(amount)) % 1 != 0:
            raise ManifestError(f"{field}.amount: {amount_unit} amounts must be integers")
    elif any(value is not None for value in (reward_id, amount, amount_unit, amount_text_ref)):
        raise ManifestError(f"{field}: reward fields require contractType=reward")

    if contract_type == "button":
        if button_type not in BUTTON_TYPES:
            raise ManifestError(f"{field}.buttonType: expected one of {sorted(BUTTON_TYPES)}")
        if button_type == "buy" and not product_id:
            raise ManifestError(f"{field}.productId: required for a buy button")
        if button_type == "buy" and not grants:
            raise ManifestError(f"{field}.grants: a buy button must declare at least one reward")
    elif any(value is not None for value in (button_type, product_id, price)) or grants:
        raise ManifestError(f"{field}: button fields require contractType=button")

    return UIContract(
        test_id=test_id,
        base=base,
        path=path,
        exist=exist,
        checks=checks,
        cardinality=cardinality,
        label=str(mapping.get("label", "")),
        source_id=str(mapping.get("source_id", mapping.get("id", ""))),
        contract_type=contract_type,
        reward_id=reward_id,
        amount=amount,
        amount_unit=amount_unit,
        amount_text_ref=amount_text_ref,
        button_type=button_type,
        product_id=product_id,
        price=price,
        grants=grants,
    )


def _build_manifest(objects: list[UIContract], name: str, declared_root: Any = None) -> dict[str, Any]:
    errors: list[str] = []
    by_id: dict[str, UIContract] = {}
    for obj in objects:
        if obj.test_id in by_id:
            errors.append(f"duplicate testId: {obj.test_id}")
        by_id[obj.test_id] = obj

    roots = [obj for obj in objects if obj.base is None]
    if len(roots) != 1:
        errors.append(f"expected exactly one root object, found {len(roots)}")
    elif declared_root not in (None, "") and str(declared_root).strip() != roots[0].test_id:
        errors.append(
            f"root references {str(declared_root).strip()!r}, expected {roots[0].test_id!r}"
        )

    for obj in objects:
        if obj.base is not None and obj.base not in by_id:
            errors.append(f"{obj.test_id}: base references unknown testId {obj.base!r}")
        if obj.base is None and obj.path.mode == "offspring":
            errors.append(f"{obj.test_id}: root object cannot use pathMode=offspring")
        if obj.base is None and obj.path.mode == "same":
            errors.append(f"{obj.test_id}: root object cannot use pathMode=same")
        if obj.path.mode == "same" and obj.base is None:
            errors.append(f"{obj.test_id}: pathMode=same requires base")
        if obj.amount_text_ref is not None and obj.amount_text_ref not in by_id:
            errors.append(
                f"{obj.test_id}: amountTextRef references unknown testId {obj.amount_text_ref!r}"
            )

    reward_ids = {obj.reward_id for obj in objects if obj.contract_type == "reward"}
    shared_amounts: dict[str, tuple[int | float | str | None, str | None]] = {}
    for obj in objects:
        if obj.amount_text_ref is not None and obj.amount_text_ref in by_id:
            amount_node = by_id[obj.amount_text_ref]
            if not any(check.get("type") == "text" for check in amount_node.checks):
                errors.append(
                    f"{obj.test_id}: amountTextRef {obj.amount_text_ref!r} has no text check"
                )
            expected = (obj.amount, obj.amount_unit)
            previous = shared_amounts.setdefault(obj.amount_text_ref, expected)
            if previous != expected:
                errors.append(
                    f"{obj.test_id}: shared amountTextRef {obj.amount_text_ref!r} is used by rewards with different amounts"
                )
        if obj.contract_type == "button" and obj.button_type == "buy":
            for reward_id in obj.grants:
                if reward_id not in reward_ids:
                    errors.append(
                        f"{obj.test_id}: grants references unknown rewardId {reward_id!r}"
                    )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(test_id: str) -> None:
        if test_id in visiting:
            errors.append(f"cyclic base reference involving {test_id}")
            return
        if test_id in visited or test_id not in by_id:
            return
        visiting.add(test_id)
        base = by_id[test_id].base
        if base is not None:
            visit(base)
        visiting.remove(test_id)
        visited.add(test_id)

    for obj in objects:
        visit(obj.test_id)

    if errors:
        raise ManifestError("Manifest validation failed:\n" + "\n".join(f"- {error}" for error in errors))

    root_id = roots[0].test_id
    return {
        "schemaVersion": SCHEMA_VERSION,
        "name": name,
        "root": root_id,
        "objects": [obj.to_dict() for obj in objects],
    }


def _decode_compressed_diagram(payload: str) -> str:
    encoded = payload.strip()
    if encoded.startswith("<"):
        return encoded

    candidates: list[bytes] = []
    try:
        candidates.append(unquote_to_bytes(encoded))
    except Exception:
        pass

    compact = re.sub(r"\s+", "", encoded)
    if compact and re.fullmatch(r"[A-Za-z0-9+/=_-]+", compact):
        for candidate in (compact, compact.replace("-", "+").replace("_", "/")):
            try:
                candidates.append(base64.b64decode(candidate + "=" * (-len(candidate) % 4)))
            except Exception:
                pass

    for raw in candidates:
        for compressed in (raw,):
            for wbits in (-zlib.MAX_WBITS, zlib.MAX_WBITS, zlib.MAX_WBITS | 16):
                try:
                    decoded = zlib.decompress(compressed, wbits).decode("utf-8")
                except (UnicodeDecodeError, zlib.error):
                    continue
                decoded = unquote(decoded)
                if decoded.lstrip().startswith("<"):
                    return decoded

    raise ManifestError("Could not decode compressed draw.io diagram content")


def _graph_model(root: ElementTree.Element) -> ElementTree.Element:
    if _local_name(root.tag) == "mxGraphModel":
        return root
    if _local_name(root.tag) != "mxfile":
        raise ManifestError(f"Expected mxfile or mxGraphModel, got {_local_name(root.tag)}")

    diagrams = [child for child in root if _local_name(child.tag) == "diagram"]
    if not diagrams:
        raise ManifestError("draw.io file does not contain a diagram page")
    page = diagrams[0]
    nested_model = next(
        (child for child in page if _local_name(child.tag) == "mxGraphModel"), None
    )
    if nested_model is not None:
        return nested_model
    decoded = _decode_compressed_diagram(page.text or "")
    try:
        decoded_root = ElementTree.fromstring(decoded)
    except ElementTree.ParseError as exc:
        raise ManifestError(f"Decoded diagram is not valid XML: {exc}") from exc
    return _graph_model(decoded_root)


def parse_drawio_xml(source: str | bytes, name: str = "draw.io UI contract") -> dict[str, Any]:
    """Parse draw.io XML into a validated UI-contract manifest.

    The source may be a regular or compressed draw.io document. Testable
    ``object`` metadata is converted into contract objects, ignored metadata
    is skipped, and the resulting object graph is validated before returning
    a normalized manifest. Raises ``ManifestError`` for invalid XML, metadata,
    or graph relationships.
    """
    try:
        root = ElementTree.fromstring(source)
    except ElementTree.ParseError as exc:
        raise ManifestError(f"Invalid draw.io XML: {exc}") from exc

    model = _graph_model(root)
    objects: list[UIContract] = []
    for element in model.iter():
        if _local_name(element.tag) != "object":
            continue
        attrs = element.attrib
        role = attrs.get("metadataRole", "")
        ignored = attrs.get("testIgnore", "false")
        if role != "ui_object" and "testId" not in attrs:
            continue
        if _parse_bool(ignored, f"object {attrs.get('id', '<unknown>')}.testIgnore"):
            continue
        try:
            objects.append(
                _contract_from_mapping(
                    {
                        **attrs,
                        "label": attrs.get("label", ""),
                        "id": attrs.get("id", ""),
                    },
                    len(objects),
                )
            )
        except ManifestError as exc:
            raise ManifestError(str(exc)) from exc

    if not objects:
        raise ManifestError("No testable object metadata found in the diagram")
    return _build_manifest(objects, name)


def load_manifest(path: str | Path) -> dict[str, Any]:
    source_path = Path(path)
    source = source_path.read_bytes()
    if source_path.suffix.lower() == ".json":
        try:
            payload = json.loads(source.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ManifestError(f"Invalid manifest JSON: {exc}") from exc
        if not isinstance(payload, Mapping) or not isinstance(payload.get("objects"), list):
            raise ManifestError("Manifest JSON must contain an objects array")
        objects = [_contract_from_mapping(item, index) for index, item in enumerate(payload["objects"])]
        name = str(payload.get("name", source_path.stem))
        manifest = _build_manifest(objects, name, payload.get("root"))
    else:
        manifest = parse_drawio_xml(source, name=source_path.stem)
    for item in manifest["objects"]:
        for check in item.get("checks", []):
            if check.get("type") != "texture_image_match":
                continue
            image_key = "image" if "image" in check else "image_path"
            image_path = Path(str(check[image_key])).expanduser()
            if not image_path.is_absolute():
                check[image_key] = str((source_path.parent / image_path).resolve())
    return manifest


def save_manifest(manifest: Mapping[str, Any], output: str | Path) -> None:
    output_path = Path(output)
    output_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _coerce_bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value or "").strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off", "", "none", "null"}:
        return False
    return bool(value)


def _asset_name(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\\", "/").strip()
    text = text.rsplit("/", 1)[-1]
    if "." in text:
        text = text.rsplit(".", 1)[0]
    return text


def _strip_markup(value: Any) -> str:
    return re.sub(r"<[^>]*>", "", str(value or "")).replace("\u00a0", " ").replace("\u202f", " ").strip()


_NUMBER_RE = re.compile(r"(?<![A-Za-z])\d[\d, \t]*(?:\.\d+)?")


def _number_text(value: Any) -> str | None:
    text = _strip_markup(value)
    match = _NUMBER_RE.search(text)
    if match is None:
        match = re.search(r"\d[\d, \t]*(?:\.\d+)?", text)
    return match.group(0) if match else None


def _decimal_from_text(value: Any) -> Decimal:
    text = _number_text(value)
    if text is None:
        raise ValueError(f"no number found in {value!r}")
    return Decimal(text.replace(",", "").replace(" ", "").replace("\t", ""))


def _integer_from_text(value: Any) -> int:
    cleaned = _strip_markup(value).upper().replace(",", "").replace(" ", "")
    suffix_match = re.fullmatch(r"(\d+(?:\.\d+)?)([KMB])", cleaned)
    if suffix_match:
        number = Decimal(suffix_match.group(1))
        multiplier = {"K": Decimal(1000), "M": Decimal(1000000), "B": Decimal(1000000000)}[
            suffix_match.group(2)
        ]
        result = number * multiplier
    else:
        result = _decimal_from_text(cleaned)
    if result != result.to_integral_value():
        raise ValueError(f"expected an integer, got {value!r}")
    return int(result)


_BOOSTER_AMOUNT_RE = re.compile(
    r"x\s*((?:\d{1,3}(?:[,\s]\d{3})+|\d+))",
    re.IGNORECASE,
)


def _booster_amount_from_text(value: Any) -> int:
    text = _strip_markup(value)
    match = _BOOSTER_AMOUNT_RE.fullmatch(text)
    if match is None:
        raise ValueError(f"expected booster amount in xNumber format, got {value!r}")
    return int(re.sub(r"[,\s]", "", match.group(1)))


_DURATION_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(days?|d|hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b",
    re.IGNORECASE,
)


def _duration_seconds(value: Any) -> Decimal:
    text = _strip_markup(value)
    colon_match = re.search(r"(?<!\d)(\d{1,3}):(\d{1,2}):(\d{1,2})(?!\d)", text)
    if colon_match:
        hours, minutes, seconds = (Decimal(part) for part in colon_match.groups())
        return hours * 3600 + minutes * 60 + seconds

    units = {"d": 86400, "day": 86400, "days": 86400, "h": 3600, "hr": 3600, "hrs": 3600,
             "hour": 3600, "hours": 3600, "m": 60, "min": 60, "mins": 60, "minute": 60,
             "minutes": 60, "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1}
    matches = _DURATION_RE.findall(text)
    if matches:
        return sum((Decimal(amount) * units[unit.lower()] for amount, unit in matches), Decimal(0))
    return _decimal_from_text(text)


class UIContractRunner:
    def __init__(
        self,
        poco: Any,
        manifest: Mapping[str, Any],
        checkers: Mapping[str, Callable[["UIContractRunner", Any, dict[str, Any], UIContract], str | None]] | None = None,
        strict_cardinality: bool = True,
        logger: Any = None,
    ) -> None:
        self.poco = poco
        raw_objects = manifest.get("objects")
        if not isinstance(raw_objects, list):
            raise ManifestError("Manifest must contain an objects array")
        contracts = [
            _contract_from_mapping(item, index)
            for index, item in enumerate(raw_objects)
        ]
        self.manifest = _build_manifest(
            contracts,
            str(manifest.get("name", "UI contract")),
            manifest.get("root"),
        )
        self.objects = {obj.test_id: obj for obj in contracts}
        self.strict_cardinality = strict_cardinality
        self.logger = logger
        self.checkers = dict(DEFAULT_CHECKERS)
        if checkers:
            self.checkers.update(checkers)
        self._nodes: dict[str, Any] = {}
        self._resolving: set[str] = set()

    def resolve(self, test_id: str) -> Any:
        if test_id in self._nodes:
            return self._nodes[test_id]
        if test_id not in self.objects:
            raise ResolutionError(f"unknown contract object {test_id!r}")
        if test_id in self._resolving:
            raise ResolutionError(f"cyclic base resolution involving {test_id!r}")

        self._resolving.add(test_id)
        try:
            contract = self.objects[test_id]
            scope = self.resolve(contract.base) if contract.base else None
            node = self._resolve_path(scope, contract.path)
            self._nodes[test_id] = node
            return node
        finally:
            self._resolving.remove(test_id)

    def run(self) -> ContractReport:
        assertions: list[ContractAssertion] = []
        for contract in self.objects.values():
            try:
                node = self.resolve(contract.test_id)
                resolution_error = None
            except Exception as exc:
                node = None
                resolution_error = exc

            if resolution_error is not None:
                if not contract.exist:
                    assertions.append(
                        ContractAssertion(
                            contract.test_id,
                            "exist",
                            True,
                            f"node is absent ({resolution_error})",
                        )
                    )
                    continue
                assertions.append(
                    ContractAssertion(
                        contract.test_id,
                        "exist",
                        False,
                        f"could not resolve node: {resolution_error}",
                    )
                )
                continue

            actual_exists = self._exists(node)
            existence_passed = actual_exists == contract.exist
            assertions.append(
                ContractAssertion(
                    contract.test_id,
                    "exist",
                    existence_passed,
                    f"expected {contract.exist}, got {actual_exists}",
                )
            )

            if not actual_exists:
                continue

            cardinality_message = self._check_cardinality(node, contract)
            if cardinality_message is not None:
                assertions.append(
                    ContractAssertion(contract.test_id, "cardinality", False, cardinality_message)
                )

            for index, check in enumerate(contract.checks):
                check_type = str(check.get("type", "")).strip()
                checker = self.checkers.get(check_type)
                if checker is None:
                    assertions.append(
                        ContractAssertion(
                            contract.test_id,
                            f"checks[{index}]/{check_type or 'unknown'}",
                            False,
                            f"no checker registered for {check_type!r}",
                        )
                    )
                    continue
                try:
                    message = checker(self, node, check, contract)
                except Exception as exc:
                    message = f"checker raised {type(exc).__name__}: {exc}"
                assertions.append(
                    ContractAssertion(
                        contract.test_id,
                        f"checks[{index}]/{check_type}",
                        message is None,
                        message or "passed",
                    )
                )

        report = ContractReport(assertions)
        if self.logger:
            self.logger.info(report.format())
        return report

    def _resolve_path(self, scope: Any, path: PathSpec) -> Any:
        if path.mode == "same":
            if scope is None:
                raise ResolutionError("pathMode=same requires a base scope")
            return scope

        names = list(path.names)
        if scope is None:
            if path.mode == "offspring":
                raise ResolutionError("pathMode=offspring requires a base scope")
            try:
                current = self.poco(names.pop(0))
            except Exception as exc:
                raise ResolutionError(f"could not select root {path.names[0]!r}: {exc}") from exc
        else:
            current = scope

        for name in names:
            try:
                current = current.offspring(name)
            except Exception as exc:
                raise ResolutionError(f"could not resolve offspring {name!r}: {exc}") from exc
        return current

    def resolve_target(self, node: Any, raw_target: Any) -> Any:
        if raw_target is None:
            return node
        if isinstance(raw_target, Mapping):
            mode = raw_target.get("type", raw_target.get("pathMode", raw_target.get("mode", "offspring")))
            raw_path = raw_target.get("names", raw_target.get("path", raw_target.get("segments")))
        else:
            mode = "offspring"
            raw_path = raw_target
        return self._resolve_path(node, PathSpec.from_raw(mode, raw_path, "check.target"))

    def read_attr(self, node: Any, name: str) -> Any:
        attr = getattr(node, "attr", None)
        if callable(attr):
            value = attr(name)
            if value is not None:
                return value
        return getattr(node, name, None)

    def read_text(self, node: Any) -> str | None:
        get_text = getattr(node, "get_text", None)
        if callable(get_text):
            value = get_text()
            if value is not None:
                return str(value)
        value = self.read_attr(node, "text")
        return None if value is None else str(value)

    def _exists(self, node: Any) -> bool:
        exists = getattr(node, "exists", None)
        if callable(exists):
            return bool(exists())
        return bool(node)

    def _count(self, node: Any) -> int | None:
        for method_name in ("get_count", "count"):
            method = getattr(node, method_name, None)
            if callable(method):
                try:
                    value = method()
                except Exception:
                    continue
                if isinstance(value, int):
                    return value
            elif isinstance(method, int):
                return method
        try:
            return len(node)
        except Exception:
            return None

    def _check_cardinality(self, node: Any, contract: UIContract) -> str | None:
        if contract.cardinality == "any":
            return None
        count = self._count(node)
        if count is None:
            if self.strict_cardinality:
                return "cardinality could not be measured"
            return None
        if contract.cardinality == "unique" and count != 1:
            return f"expected exactly one node, got {count}"
        if contract.cardinality == "one_or_more" and count < 1:
            return f"expected at least one node, got {count}"
        return None


def _check_texture(runner: UIContractRunner, node: Any, check: dict[str, Any], _: UIContract) -> str | None:
    target = runner.resolve_target(node, check.get("target"))
    actual = _asset_name(runner.read_attr(target, "texture"))
    if not actual:
        actual = _asset_name(runner.read_attr(target, "spriteName"))
    expected = _asset_name(check.get("expected"))
    if actual != expected:
        return f"expected texture {expected!r}, got {actual!r}"
    return None


def _check_texture_image_match(
    runner: UIContractRunner, node: Any, check: dict[str, Any], _: UIContract
) -> str | None:
    import cv2
    import numpy as np

    texture_checks = [item for item in _.checks if item.get("type") == "texture"]
    if len(texture_checks) != 1:
        return f"texture_image_match requires exactly one texture check, got {len(texture_checks)}"

    target = runner.resolve_target(node, texture_checks[0].get("target"))
    image_path = Path(str(check.get("image", check.get("image_path")))).expanduser()
    if not image_path.is_file():
        return f"reference image does not exist: {image_path}"

    encoded, _ = runner.poco.snapshot(width=int(check.get("screenshot_width", 720)))
    screen = cv2.imdecode(
        np.frombuffer(base64.b64decode(encoded), dtype=np.uint8), cv2.IMREAD_COLOR
    )
    if screen is None:
        return "Poco returned an invalid screenshot"

    bounds = runner.read_attr(target, "bounds")
    get_bounds = getattr(target, "get_bounds", None)
    if callable(get_bounds):
        bounds = get_bounds()
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
        return f"target has invalid Poco bounds: {bounds!r}"

    height, width = screen.shape[:2]
    top, right, bottom, left = (float(value) for value in bounds)
    x1 = max(0, min(width - 1, int(round(left * width))))
    y1 = max(0, min(height - 1, int(round(top * height))))
    x2 = max(x1 + 1, min(width, int(round(right * width))))
    y2 = max(y1 + 1, min(height, int(round(bottom * height))))
    region = screen[y1:y2, x1:x2]

    template = cv2.imdecode(np.fromfile(str(image_path), dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if template is None:
        return f"could not decode reference image: {image_path}"
    alpha = None
    if template.ndim == 2:
        template = cv2.cvtColor(template, cv2.COLOR_GRAY2BGR)
    elif template.shape[2] == 4:
        alpha = template[:, :, 3]
        visible = cv2.findNonZero(alpha)
        if visible is None:
            return f"reference image is fully transparent: {image_path}"
        crop_x, crop_y, crop_width, crop_height = cv2.boundingRect(visible)
        template = template[crop_y:crop_y + crop_height, crop_x:crop_x + crop_width, :3]
        alpha = alpha[crop_y:crop_y + crop_height, crop_x:crop_x + crop_width]
    else:
        template = template[:, :, :3]

    template_height, template_width = template.shape[:2]
    region_height, region_width = region.shape[:2]
    max_scale = min((region_width - 1) / template_width, (region_height - 1) / template_height)
    if max_scale <= 0:
        return f"image region is too small to match reference ({region_width}x{region_height})"

    min_scale = max_scale * float(check.get("min_scale_ratio", 0.95))
    best_confidence = 0.0
    best_rect = None
    for scale in np.linspace(min_scale, max_scale, int(check.get("scale_steps", 48))):
        match_width = max(8, int(round(template_width * scale)))
        match_height = max(8, int(round(template_height * scale)))
        if match_width > region_width or match_height > region_height:
            continue
        resized = cv2.resize(template, (match_width, match_height), interpolation=cv2.INTER_AREA)
        if alpha is None:
            result = cv2.matchTemplate(region, resized, cv2.TM_CCOEFF_NORMED)
        else:
            resized_alpha = cv2.resize(alpha, (match_width, match_height), interpolation=cv2.INTER_AREA)
            result = cv2.matchTemplate(region, resized, cv2.TM_CCORR_NORMED, mask=resized_alpha)
        _, confidence, _, location = cv2.minMaxLoc(result)
        if confidence > best_confidence:
            best_confidence = float(confidence)
            best_rect = (x1 + location[0], y1 + location[1], match_width, match_height)

    threshold = float(check.get("threshold", 0.83))
    if _coerce_bool_value(check.get("debug", False)):
        from datetime import datetime

        output_dir = Path(check.get("debug_dir", r"F:\SnakeTest\logs\ui_contract_debug")).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        marked = screen.copy()
        cv2.rectangle(marked, (x1, y1), (x2, y2), (0, 255, 255), 2)
        if best_rect is not None:
            match_x, match_y, match_width, match_height = best_rect
            cv2.rectangle(marked, (match_x, match_y), (match_x + match_width, match_y + match_height), (0, 255, 0), 2)
        debug_path = output_dir / f"texture_match_{datetime.now():%Y%m%d_%H%M%S_%f}.png"
        if not cv2.imwrite(str(debug_path), marked):
            raise OSError(f"could not write debug screenshot: {debug_path}")

    if best_confidence < threshold:
        return f"reference image {image_path.name!r} did not match target (confidence={best_confidence:.3f}, threshold={threshold:.3f}, bounds={(x1, y1, x2, y2)})"
    return None


def _check_clickable(runner: UIContractRunner, node: Any, check: dict[str, Any], _: UIContract) -> str | None:
    expected = _coerce_bool_value(check.get("expected", True))
    actual = _coerce_bool_value(runner.read_attr(node, "clickable"))
    if actual != expected:
        return f"expected clickable={expected}, got {actual}"
    return None


def _check_component_exists(
    runner: UIContractRunner, node: Any, check: dict[str, Any], _: UIContract
) -> str | None:
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


def _check_literal(actual: str, expected: Any, case_sensitive: bool) -> str | None:
    actual = _strip_markup(actual)
    expected_text = _strip_markup(expected)
    left = actual if case_sensitive else actual.casefold()
    right = expected_text if case_sensitive else expected_text.casefold()
    if left != right:
        return f"expected text {expected_text!r}, got {actual!r}"
    return None


def _check_price(actual: str, check: dict[str, Any]) -> str | None:
    expected = Decimal(str(check.get("amount", check.get("expected"))))
    actual_amount = _decimal_from_text(actual)
    if actual_amount != expected:
        return f"expected price {expected}, got {actual_amount} from {actual!r}"

    text = _strip_markup(actual)
    currencies = [str(currency).strip() for currency in check.get("currencies", [])]
    currency_match = next((currency for currency in currencies if currency in text), None)
    if currency_match is None:
        return f"expected one of currencies {currencies!r}, got {actual!r}"
    currency_position = str(check.get("currency_position", "any")).lower()
    if currency_position != "any":
        number_match = _NUMBER_RE.search(text)
        token_index = text.find(currency_match)
        if number_match is None:
            return f"could not locate price number in {actual!r}"
        if currency_position == "prefix" and token_index > number_match.start():
            return f"expected currency prefix in {actual!r}"
        if currency_position == "suffix" and number_match.end() > token_index:
            return f"expected currency suffix in {actual!r}"
    return None


def _check_integer(actual: str, expected: Any, label: str) -> str | None:
    expected_value = int(Decimal(str(expected)))
    actual_value = _integer_from_text(actual)
    if actual_value != expected_value:
        return f"expected {label}={expected_value}, got {actual_value} from {actual!r}"
    return None


def _check_booster_amount(actual: str, expected: Any) -> str | None:
    try:
        actual_value = _booster_amount_from_text(actual)
    except ValueError as exc:
        return str(exc)

    expected_value = int(Decimal(str(expected)))
    if actual_value != expected_value:
        return f"expected booster amount={expected_value}, got {actual_value} from {actual!r}"
    return None


def _check_life_duration(actual: str, check: dict[str, Any]) -> str | None:
    expected = Decimal(str(check.get("seconds", check.get("expected"))))
    duration = _duration_seconds(actual)
    rounding = str(check.get("rounding", "exact")).lower()
    if rounding == "floor":
        duration = duration.to_integral_value(rounding=ROUND_FLOOR)
    elif rounding == "ceil":
        duration = duration.to_integral_value(rounding=ROUND_CEILING)
    elif rounding == "nearest":
        duration = duration.to_integral_value(rounding=ROUND_HALF_UP)
    tolerance = Decimal(str(check.get("tolerance_seconds", 0)))
    if abs(duration - expected) > tolerance:
        return f"expected life duration {expected}s, got {duration}s from {actual!r}"
    return None


def _check_text(runner: UIContractRunner, node: Any, check: dict[str, Any], _: UIContract) -> str | None:
    target = runner.resolve_target(node, check.get("target")) #poco node contains text
    actual = runner.read_text(target)
    if actual is None:
        return "target has no text attribute"
    text_format = str(check.get("format", "literal")).lower()
    if text_format == "literal":
        return _check_literal(actual, check.get("expected"), _coerce_bool_value(check.get("case_sensitive", True)))
    if text_format == "price":
        return _check_price(actual, check)
    if text_format == "gold_amount":
        return _check_integer(actual, check.get("amount", check.get("expected")), "gold amount")
    if text_format == "booster_amount":
        return _check_booster_amount(actual, check.get("amount", check.get("expected")))
    if text_format == "life_duration":
        return _check_life_duration(actual, check)
    return f"unsupported text format {text_format!r}"


from utils.ui_contract_checks import DEFAULT_CHECKERS


def run_contract(
    poco: Any,
    manifest: Mapping[str, Any],
    checkers: Mapping[str, Callable[[UIContractRunner, Any, dict[str, Any], UIContract], str | None]] | None = None,
    strict_cardinality: bool = True,
    logger: Any = None,
) -> ContractReport:
    report = UIContractRunner(
        poco,
        manifest,
        checkers=checkers,
        strict_cardinality=strict_cardinality,
        logger=logger,
    ).run()
    from utils.ui_contract_reporting import record_contract_report

    record_contract_report(report, str(manifest.get("name", "UI contract")))
    return report


def assert_contract(
    poco: Any,
    manifest: Mapping[str, Any],
    checkers: Mapping[str, Callable[[UIContractRunner, Any, dict[str, Any], UIContract], str | None]] | None = None,
    strict_cardinality: bool = True,
    logger: Any = None,
) -> ContractReport:
    report = run_contract(
        poco,
        manifest,
        checkers=checkers,
        strict_cardinality=strict_cardinality,
        logger=logger,
    )
    if not report.passed:
        raise AssertionError(report.format())
    return report


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert a draw.io UI contract into JSON.")
    parser.add_argument("source", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(args.source)
        if args.output:
            save_manifest(manifest, args.output)
            print(args.output)
        else:
            print(json.dumps(manifest, indent=2, ensure_ascii=True))
    except (OSError, ManifestError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
