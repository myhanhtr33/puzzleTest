from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from .types import Checker


def check_texture(runner: Any, node: Any, check: dict[str, Any], contract: Any) -> str | None:
    from utils.ui_contracts import _asset_name

    target = runner.resolve_target(node, check.get("target"))
    actual = _asset_name(runner.read_attr(target, "texture"))
    if not actual:
        actual = _asset_name(runner.read_attr(target, "spriteName"))
    expected = _asset_name(check.get("expected"))
    if actual != expected:
        return f"expected texture {expected!r}, got {actual!r}"
    return None


def check_texture_image_match(runner: Any, node: Any, check: dict[str, Any], contract: Any) -> str | None:
    import cv2
    import numpy as np

    texture_checks = [item for item in contract.checks if item.get("type") == "texture"]
    if len(texture_checks) != 1:
        return f"texture_image_match requires exactly one texture check, got {len(texture_checks)}"

    target = runner.resolve_target(node, texture_checks[0].get("target"))
    image_path = Path(str(check.get("image", check.get("image_path")))).expanduser()
    if not image_path.is_file():
        return f"reference image does not exist: {image_path}"

    encoded, _ = runner.poco.snapshot(width=int(check.get("screenshot_width", 720)))
    screen = cv2.imdecode(np.frombuffer(base64.b64decode(encoded), dtype=np.uint8), cv2.IMREAD_COLOR)
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
    from utils.ui_contract_reporting import is_collecting, record_debug_image
    from utils.ui_contracts import _coerce_bool_value

    if _coerce_bool_value(check.get("debug", False)) or is_collecting():
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
        record_debug_image(debug_path)

    if best_confidence < threshold:
        return f"reference image {image_path.name!r} did not match target (confidence={best_confidence:.3f}, threshold={threshold:.3f}, bounds={(x1, y1, x2, y2)})"
    return None


CHECKERS: dict[str, Checker] = {
    "texture": check_texture,
    "texture_image_match": check_texture_image_match,
}
