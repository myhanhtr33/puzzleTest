import cv2
import numpy as np


def multi_scale_template_match(scene_bgr, template_bgr, roi=None, scales=None, threshold=0.70):
    if scales is None:
        scales = np.linspace(0.6, 1.8, 25)

    if roi is None:
        x0, y0, w0, h0 = 0, 0, scene_bgr.shape[1], scene_bgr.shape[0]
    else:
        x0, y0, w0, h0 = roi

    scene_roi = scene_bgr[y0:y0+h0, x0:x0+w0]
    scene_gray = cv2.cvtColor(scene_roi, cv2.COLOR_BGR2GRAY)

    best = None

    for scale in scales:
        tw = int(template_bgr.shape[1] * scale)
        th = int(template_bgr.shape[0] * scale)

        if tw < 30 or th < 20:
            continue
        if tw >= scene_roi.shape[1] or th >= scene_roi.shape[0]:
            continue

        resized = cv2.resize(template_bgr, (tw, th), interpolation=cv2.INTER_AREA)
        tpl_gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

        result = cv2.matchTemplate(scene_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if best is None or max_val > best["score"]:
            best = {
                "score": max_val,
                "x": x0 + max_loc[0],
                "y": y0 + max_loc[1],
                "w": tw,
                "h": th,
                "scale": scale
            }

    if best is None or best["score"] < threshold:
        return None

    return best


def shrink_rect(rect, pad_x, pad_y):
    x, y, w, h = rect
    return (
        x + pad_x,
        y + pad_y,
        max(1, w - 2 * pad_x),
        max(1, h - 2 * pad_y)
    )


def detect_text_mask_in_button(scene_bgr, button_rect):
    x, y, w, h = button_rect
    crop = scene_bgr[y:y+h, x:x+w]

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    # bright text fill
    bright_mask = cv2.inRange(gray, 180, 255)

    # dark outline (likely around text)
    dark_mask = cv2.inRange(gray, 0, 110)

    # expand bright area a bit, then keep nearby dark outline
    kernel = np.ones((3, 3), np.uint8)
    bright_dilated = cv2.dilate(bright_mask, kernel, iterations=1)

    outline_near_text = cv2.bitwise_and(dark_mask, bright_dilated)

    # final text-like mask
    text_mask = cv2.bitwise_or(bright_mask, outline_near_text)

    # cleanup
    text_mask = cv2.morphologyEx(text_mask, cv2.MORPH_OPEN, kernel)
    text_mask = cv2.morphologyEx(text_mask, cv2.MORPH_CLOSE, kernel)

    return text_mask


def largest_text_bbox(text_mask, min_area=80):
    contours, _ = cv2.findContours(text_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        boxes.append((x, y, w, h))

    if not boxes:
        return None, []

    # union all text components
    xs = [b[0] for b in boxes]
    ys = [b[1] for b in boxes]
    x2s = [b[0] + b[2] for b in boxes]
    y2s = [b[1] + b[3] for b in boxes]

    union = (min(xs), min(ys), max(x2s) - min(xs), max(y2s) - min(ys))
    return union, boxes


def rect_inside(inner, outer):
    ix, iy, iw, ih = inner
    ox, oy, ow, oh = outer

    return (
        ix >= ox and
        iy >= oy and
        ix + iw <= ox + ow and
        iy + ih <= oy + oh
    )


def analyze_button_text(scene_path, template_path, roi):
    scene = cv2.imread(scene_path)
    template = cv2.imread(template_path)

    match = multi_scale_template_match(scene, template, roi=roi, threshold=0.65)
    if match is None:
        return {
            "status": "FAIL",
            "reason": "Button sprite not found in ROI"
        }

    button_rect = (match["x"], match["y"], match["w"], match["h"])

    # safe area for valid text
    safe_rect = shrink_rect(button_rect, pad_x=int(match["w"] * 0.10), pad_y=int(match["h"] * 0.16))

    text_mask = detect_text_mask_in_button(scene, button_rect)
    text_bbox_local, parts = largest_text_bbox(text_mask)

    if text_bbox_local is None:
        return {
            "status": "FAIL",
            "reason": "No visible text detected inside detected button",
            "button_rect": button_rect,
            "safe_rect": safe_rect,
            "score": match["score"]
        }

    # convert local text bbox to scene coords
    bx, by, bw, bh = button_rect
    tlx, tly, tlw, tlh = text_bbox_local
    text_bbox_global = (bx + tlx, by + tly, tlw, tlh)

    inside_outer = rect_inside(text_bbox_global, button_rect)
    inside_safe = rect_inside(text_bbox_global, safe_rect)

    if inside_safe:
        status = "PASS"
        reason = "Text is inside button safe area"
    elif inside_outer:
        status = "WARNING"
        reason = "Text is inside button, but overlaps border/safe padding"
    else:
        status = "FAIL"
        reason = "Text spreads outside button boundary"

    return {
        "status": status,
        "reason": reason,
        "score": match["score"],
        "button_rect": button_rect,
        "safe_rect": safe_rect,
        "text_bbox": text_bbox_global
    }