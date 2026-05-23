"""Detect and correct document skew and cardinal misorientation.

Orientation is inferred from page content (projection variance, text position),
not EXIF metadata. Scanned PDFs and TIFFs rarely have trustworthy EXIF tags.

PDF pages may carry a ``/Rotate`` entry (clockwise degrees); ``pypdfium2`` does not
apply it during ``page.render()`` — callers must bake that rotation into pixels
before running :func:`deskew_image` (see :func:`pdf_page_rotation_ccw`).

Set ``DESKEW_DEBUG=1`` to log orientation decisions (variance scores, trial ranks,
PDF/OSD overrides, fine skew, landscape flip) at INFO on logger ``docread.deskew``,
and to append the same lines to OCR ``warnings`` (UI Notes) via
:func:`consume_deskew_debug_trace`.
"""

from __future__ import annotations

import contextvars
import io
import logging
import os
import re

import cv2
import numpy as np
from PIL import Image, ImageOps

logger = logging.getLogger("docread.deskew")

_deskew_debug_label: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "deskew_debug_label", default=None
)
_deskew_debug_trace: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "deskew_debug_trace", default=None
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def deskew_debug_enabled() -> bool:
    """True when ``DESKEW_DEBUG`` requests verbose deskew tracing."""
    return os.getenv("DESKEW_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


def _deskew_debug_enabled() -> bool:
    return deskew_debug_enabled()


def _format_deskew_debug_line(msg: str, **fields: object) -> str:
    label = _deskew_debug_label.get()
    prefix = f"[{label}]" if label else ""
    if fields:
        detail = " ".join(f"{key}={value!r}" for key, value in fields.items())
        return f"{prefix}{msg} | {detail}".strip()
    return f"{prefix}{msg}".strip()


def _deskew_debug(msg: str, **fields: object) -> None:
    if not _deskew_debug_enabled():
        return
    line = _format_deskew_debug_line(msg, **fields)
    logger.info("deskew %s", line)
    trace = _deskew_debug_trace.get()
    if trace is not None:
        trace.append(line)


def _begin_deskew_debug_trace() -> None:
    if _deskew_debug_enabled() and _deskew_debug_trace.get() is None:
        _deskew_debug_trace.set([])


def consume_deskew_debug_trace() -> list[str]:
    """Return and clear debug lines collected for the current deskew call."""
    trace = _deskew_debug_trace.get()
    if trace is None:
        return []
    _deskew_debug_trace.set(None)
    return list(trace)


def _variance_summary(gray: np.ndarray) -> dict[str, float]:
    variances = _cardinal_variances(gray)
    return {
        "var_k0": round(variances[0], 1),
        "var_k1": round(variances[1], 1),
        "var_k2": round(variances[2], 1),
        "var_k3": round(variances[3], 1),
        "score_0_180": round(max(variances[0], variances[2]), 1),
        "score_90_270": round(max(variances[1], variances[3]), 1),
    }


def _to_gray(img: Image.Image) -> np.ndarray:
    return np.array(img.convert("L"), dtype=np.uint8)


def _proj_variance(gray: np.ndarray) -> float:
    """Variance of row-wise dark-pixel sums. High when text lines are horizontal."""
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return float(np.var(binary.sum(axis=1).astype(np.float64)))


def _boundary_asymmetry(gray: np.ndarray) -> float:
    """Return a score > 0 when the image is correctly oriented (0°).

    Measures whether text band ENTRIES (top edge) are sharper than EXITS
    (bottom edge) using only cross-zero transitions in the projection profile.
    """
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    proj = binary.sum(axis=1).astype(np.float64)

    threshold = proj.max() * 0.05
    if threshold == 0:
        return 0.0

    entry_sq: list[float] = []
    exit_sq: list[float] = []
    in_band = False
    prev_val = 0.0

    for _i, val in enumerate(proj):
        if not in_band and val > threshold:
            entry_sq.append(val**2)
            in_band = True
        elif in_band and val <= threshold:
            exit_sq.append(prev_val**2)
            in_band = False
        prev_val = val

    if in_band and prev_val > threshold:
        exit_sq.append(prev_val**2)

    if not entry_sq or not exit_sq:
        return 0.0
    return float(np.mean(entry_sq) - np.mean(exit_sq))


def _text_vertical_center(gray: np.ndarray) -> float | None:
    """Normalised vertical centre of dark pixels (0=top, 1=bottom)."""
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    row_dark = binary.sum(axis=1).astype(np.float64)
    total_dark = row_dark.sum()
    if total_dark <= 0:
        return None
    rows_idx = np.arange(len(row_dark), dtype=np.float64)
    return float((rows_idx * row_dark).sum() / total_dark) / len(row_dark)


def _apply_ccw_transpose(img: Image.Image, degrees: int) -> Image.Image:
    rotation = int(degrees) % 360
    if rotation == 0:
        return img
    return img.transpose(
        {
            90: Image.Transpose.ROTATE_90,
            180: Image.Transpose.ROTATE_180,
            270: Image.Transpose.ROTATE_270,
        }[rotation]
    )


def _cardinal_variances(gray: np.ndarray) -> list[float]:
    return [_proj_variance(np.rot90(gray, k=k)) for k in range(4)]


def _ink_binary_for_content(gray: np.ndarray) -> np.ndarray:
    """Binarize for content bounds; tighten threshold when the sheet is mostly 'ink'."""
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink_frac = float(np.count_nonzero(binary)) / max(binary.size, 1)
    if ink_frac > 0.08:
        thresh = int(np.percentile(gray, 90))
        binary = ((gray < thresh).astype(np.uint8)) * 255
    return binary


def _bbox_from_projection(
    binary: np.ndarray, *, peak_fraction: float = 0.02
) -> tuple[int, int, int, int] | None:
    """BBox around rows/columns that contain dense text (ignores sparse margin noise)."""
    row_proj = binary.sum(axis=1).astype(np.float64)
    col_proj = binary.sum(axis=0).astype(np.float64)
    if row_proj.max() <= 0 or col_proj.max() <= 0:
        return None
    row_thresh = max(row_proj.max() * peak_fraction, 1.0)
    col_thresh = max(col_proj.max() * peak_fraction, 1.0)
    rows = np.flatnonzero(row_proj > row_thresh)
    cols = np.flatnonzero(col_proj > col_thresh)
    if rows.size == 0 or cols.size == 0:
        return None
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


def _content_ink_bbox(
    img: Image.Image, *, padding_ratio: float = 0.012
) -> tuple[int, int, int, int] | None:
    """Estimate the document island inside the scan (projection first, then blob union)."""
    gray = _to_gray(img)
    binary = _ink_binary_for_content(gray)
    bbox = _bbox_from_projection(binary)
    if bbox is None:
        return None
    x0, y0, x1, y1 = bbox
    fill = max(0, x1 - x0) * max(0, y1 - y0) / max(img.width * img.height, 1)
    if fill < 0.98:
        pad_x = max(1, int(img.width * padding_ratio))
        pad_y = max(1, int(img.height * padding_ratio))
        return (
            max(0, x0 - pad_x),
            max(0, y0 - pad_y),
            min(img.width, x1 + pad_x),
            min(img.height, y1 + pad_y),
        )

    page_area = img.width * img.height
    max_blob_area = page_area * 0.65
    min_area = max(20, int(page_area * 0.00002))
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    rects: list[tuple[int, int, int, int]] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if area < min_area or area > max_blob_area:
            continue
        rects.append((x, y, w, h))
    if not rects:
        return bbox
    x0 = min(r[0] for r in rects)
    y0 = min(r[1] for r in rects)
    x1 = max(r[0] + r[2] for r in rects)
    y1 = max(r[1] + r[3] for r in rects)
    pad_x = max(1, int(img.width * padding_ratio))
    pad_y = max(1, int(img.height * padding_ratio))
    return (
        max(0, x0 - pad_x),
        max(0, y0 - pad_y),
        min(img.width, x1 + pad_x),
        min(img.height, y1 + pad_y),
    )


def _content_fill_ratio(img: Image.Image, bbox: tuple[int, int, int, int]) -> float:
    x0, y0, x1, y1 = bbox
    ink_area = max(0, x1 - x0) * max(0, y1 - y0)
    return ink_area / max(img.width * img.height, 1)


def _fine_skew_max_scan_dim() -> int:
    raw = os.getenv("DESKEW_FINE_SCAN_DIM", "2400").strip()
    try:
        return max(600, int(raw))
    except ValueError:
        return 2400


def _fine_skew_scan_dim_for(img: Image.Image) -> int:
    """Use native resolution for skew search when the probe is already moderate size."""
    return min(_fine_skew_max_scan_dim(), max(img.size))


def _content_bbox_max_fill() -> float:
    """Use ink-bbox orientation when content covers less than this fraction of the page."""
    raw = os.getenv("DESKEW_CONTENT_BBOX_MAX_FILL", "0.72").strip()
    try:
        value = float(raw)
    except ValueError:
        return 0.72
    return min(0.98, max(0.05, value))


def _orientation_probe_image(img: Image.Image) -> tuple[Image.Image, str, float]:
    """Return the image to use for cardinal/sideways detection (full page or content crop)."""
    bbox = _content_ink_bbox(img)
    if bbox is None:
        return img, "full_page", 1.0
    fill = _content_fill_ratio(img, bbox)
    if fill >= _content_bbox_max_fill():
        return img, "full_page", fill
    x0, y0, x1, y1 = bbox
    probe_w = x1 - x0
    probe_h = y1 - y0
    min_dim = max(32, int(min(img.width, img.height) * 0.08))
    if min(probe_w, probe_h) < min_dim:
        _deskew_debug(
            "orientation_probe_skip",
            reason="ink_bbox_too_thin",
            probe_w=probe_w,
            probe_h=probe_h,
            min_dim=min_dim,
        )
        return img, "full_page", fill
    crop = img.crop((x0, y0, x1, y1))
    return crop, "content_bbox", fill


def _sideways_ccw_from_skew_hint(skew_hint: float) -> int | None:
    """Map a ±90° fine-skew hint to the opposite quarter-turn transpose.

    ``detect_page_angle`` searches small ``rotate()`` angles; for sideways pages
    the winning ±90° sign picks the *other* horizontal orientation than the
    CCW transpose that actually uprights the page (paperless-style scans).
    """
    abs_hint = abs(skew_hint)
    if abs(abs_hint - 90.0) > _SKEW_HINT_CARDINAL_TOL:
        return None
    return 90 if skew_hint < 0 else 270


def _pick_sideways_ccw(
    img: Image.Image,
    *,
    skew_hint: float,
    allow_skew_hint_tie: bool = False,
    full_page_ambiguous_skew_hint: bool = False,
) -> int:
    """Choose 90° or 270° CCW for a sideways page."""
    trials: list[dict[str, float | int]] = []
    for rot in (90, 270):
        rotated_img = _apply_ccw_transpose(img, rot)
        card, conf = detect_cardinal_rotation(rotated_img)
        if card == 0:
            card_rank = 0
        elif card == 180:
            card_rank = 1
        else:
            card_rank = 2
        trials.append(
            {
                "rot": rot,
                "card": card,
                "conf": conf,
                "card_rank": card_rank,
                "residual": abs(detect_page_angle(rotated_img)),
            }
        )

    cards = {int(t["card"]) for t in trials}
    max_conf = max(float(t["conf"]) for t in trials)
    ambiguous = cards == {0, 180} and max_conf < _SIDEWAYS_LOW_CONF
    hint_ccw = _sideways_ccw_from_skew_hint(skew_hint)

    best = min(
        trials,
        key=lambda t: (
            int(t["card_rank"]),
            float(t["residual"]),
            -float(t["conf"]),
        ),
    )
    chosen = int(best["rot"])
    if int(best["card_rank"]) >= 2:
        chosen = 270
        reason = "fallback"
    else:
        reason = "ranked"

    if (
        ambiguous
        and hint_ccw is not None
        and chosen != hint_ccw
        and (allow_skew_hint_tie or full_page_ambiguous_skew_hint)
    ):
        chosen = hint_ccw
        reason = "skew_hint_ambiguous" if allow_skew_hint_tie else "skew_hint_full_page_ambiguous"
    elif ambiguous and allow_skew_hint_tie and hint_ccw is not None:
        chosen = hint_ccw
        reason = "skew_hint_ambiguous"

    if _deskew_debug_enabled():
        for entry in trials:
            _deskew_debug(
                "sideways_trial",
                trial_ccw=int(entry["rot"]),
                detect_card=int(entry["card"]),
                detect_conf=round(float(entry["conf"]), 4),
                residual_skew=round(float(entry["residual"]), 2),
                card_rank=int(entry["card_rank"]),
            )
        _deskew_debug(
            "sideways_pick",
            chosen_ccw=chosen,
            reason=reason,
            ambiguous=ambiguous,
            skew_hint_ccw=hint_ccw,
        )
    return chosen


def _bbox_ink_fraction(img: Image.Image) -> float:
    gray = _to_gray(img)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return float(np.count_nonzero(binary)) / max(binary.size, 1)


def _tight_text_bbox_for_skew(img: Image.Image) -> tuple[int, int, int, int] | None:
    """Dense text band only (higher peak threshold than loose content bbox)."""
    gray = _to_gray(img)
    binary = _ink_binary_for_content(gray)
    return _bbox_from_projection(binary, peak_fraction=0.06)


def _skew_probe_tiles(
    probe: Image.Image, *, rows: int = 3, cols: int = 3, min_side: int = 80
) -> list[tuple[Image.Image, str]]:
    tiles: list[tuple[Image.Image, str]] = []
    width, height = probe.size
    for row in range(rows):
        for col in range(cols):
            x0 = col * width // cols
            x1 = (col + 1) * width // cols
            y0 = row * height // rows
            y1 = (row + 1) * height // rows
            if (x1 - x0) < min_side or (y1 - y0) < min_side:
                continue
            tile = probe.crop((x0, y0, x1, y1))
            if _bbox_ink_fraction(tile) < 0.015:
                continue
            tiles.append((tile, f"tile_{row}_{col}"))
    return tiles


def _pick_fine_skew_from_candidates(
    candidates: list[tuple[float, str]], *, default_source: str
) -> tuple[float, str]:
    """Tiles are capped at ±20° to drop margin noise; page-wide views keep full range."""
    usable: list[tuple[float, str]] = []
    for angle, source in candidates:
        if abs(angle) < 0.5 or abs(angle) >= _NEAR_CARDINAL_SKEW_DEG:
            continue
        if source.startswith("tile_") and abs(angle) > 20.0:
            continue
        usable.append((angle, source))
    if not usable:
        return 0.0, default_source
    return max(usable, key=lambda item: abs(item[0]))


def _measure_fine_skew_angle(img: Image.Image) -> tuple[float, str]:
    """Pick sub-quarter-turn tilt from full page, tight text, and tiled probes."""
    candidates: list[tuple[float, str]] = []

    probe, probe_source, _ = _orientation_probe_image(img)
    for view, source in (
        (probe, probe_source),
        (img, "full_page"),
    ):
        scan_dim = _fine_skew_scan_dim_for(view)
        candidates.append((detect_page_angle(view, max_scan_dim=scan_dim), source))

    tight = _tight_text_bbox_for_skew(img)
    if tight is not None:
        x0, y0, x1, y1 = tight
        if (x1 - x0) >= 80 and (y1 - y0) >= 80:
            tight_img = img.crop(tight)
            scan_dim = _fine_skew_scan_dim_for(tight_img)
            candidates.append((detect_page_angle(tight_img, max_scan_dim=scan_dim), "tight_text"))

    for tile, tile_source in _skew_probe_tiles(probe):
        scan_dim = _fine_skew_scan_dim_for(tile)
        candidates.append((detect_page_angle(tile, max_scan_dim=scan_dim), tile_source))

    if _deskew_debug_enabled():
        for angle, source in candidates:
            _deskew_debug("fine_skew_sample", source=source, degrees=round(angle, 2))

    return _pick_fine_skew_from_candidates(candidates, default_source=probe_source)


def _apply_fine_skew(img: Image.Image, *, min_angle_deg: float) -> tuple[Image.Image, float]:
    """Apply small skew correction when the page is not near a quarter-turn."""
    angle, probe_source = _measure_fine_skew_angle(img)
    net_ccw = 0.0

    if abs(angle) >= _NEAR_CARDINAL_SKEW_DEG:
        _deskew_debug(
            "fine_skew_skip",
            reason="near_cardinal",
            angle=round(angle, 2),
            probe_source=probe_source,
        )
        return img, net_ccw

    if abs(angle) < min_angle_deg:
        _deskew_debug(
            "fine_skew_skip",
            reason="below_min",
            angle=round(angle, 2),
            min_angle_deg=min_angle_deg,
            probe_source=probe_source,
        )
        return img, net_ccw

    _deskew_debug(
        "fine_skew_apply",
        angle=round(angle, 2),
        probe_source=probe_source,
    )
    img = img.rotate(
        angle,
        expand=True,
        resample=Image.Resampling.BICUBIC,
        fillcolor=(255, 255, 255),
    )
    return img, net_ccw + angle


def _apply_landscape_flip_if_needed(img: Image.Image) -> tuple[Image.Image, float]:
    """Flip 180° CCW when landscape content reads upside-down."""
    gray = _to_gray(img)
    variances = _cardinal_variances(gray)
    if max(variances[1], variances[3]) > max(variances[0], variances[2]) * 1.05:
        _deskew_debug("landscape_flip_skip", reason="portrait_variance")
        return img, 0.0

    rot, conf = detect_cardinal_rotation(img)
    if rot == 180 and conf >= 0.08:
        _deskew_debug("landscape_flip_apply", detect_card=rot, detect_conf=round(conf, 4))
        return _apply_ccw_transpose(img, 180), 180.0
    _deskew_debug(
        "landscape_flip_skip",
        reason="not_upside_down",
        detect_card=rot,
        detect_conf=round(conf, 4),
    )
    return img, 0.0


def _skip_landscape_flip_after_cardinal(
    cardinal_ccw: int, *, cardinal_branch: str, deskew_context: str = "page"
) -> bool:
    """OSD and quarter-turn picks already encode upright; extra 180° flips mis-rotate."""
    if deskew_context == "region":
        return True
    if cardinal_branch in {"tesseract_osd", "page_cardinal_disabled"}:
        return True
    if cardinal_ccw in (90, 270):
        return True
    return False


def _deskew_from_cardinal(
    img: Image.Image,
    cardinal_ccw: int,
    *,
    min_angle_deg: float,
    cardinal_branch: str = "",
    deskew_context: str = "page",
) -> tuple[Image.Image, float]:
    """Apply one cardinal rotation, then fine skew and optional 180° flip."""
    _deskew_debug("cardinal_apply", cardinal_ccw=cardinal_ccw, branch=cardinal_branch)
    trial = img if cardinal_ccw == 0 else _apply_ccw_transpose(img, cardinal_ccw)
    net_ccw = float(cardinal_ccw)

    trial, skew_ccw = _apply_fine_skew(trial, min_angle_deg=min_angle_deg)
    net_ccw += skew_ccw

    if cardinal_ccw == 180:
        _deskew_debug("landscape_flip_skip", reason="cardinal_already_180")
    elif _skip_landscape_flip_after_cardinal(
        cardinal_ccw, cardinal_branch=cardinal_branch, deskew_context=deskew_context
    ):
        reason = "region_after_page" if deskew_context == "region" else "authoritative_cardinal"
        _deskew_debug(
            "landscape_flip_skip",
            reason=reason,
            branch=cardinal_branch,
            cardinal_ccw=cardinal_ccw,
        )
    else:
        trial, flip_ccw = _apply_landscape_flip_if_needed(trial)
        net_ccw += flip_ccw

    return trial, net_ccw


def _osd_enabled() -> bool:
    return os.getenv("DESKEW_OSD", "1").strip().lower() not in {"0", "false", "no", "off"}


def _osd_min_confidence() -> float:
    raw = os.getenv("DESKEW_OSD_MIN_CONFIDENCE", "1.0").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 1.0


def _prepare_osd_image(img: Image.Image, *, min_side: int = 300) -> Image.Image:
    """Upscale small crops so Tesseract OSD (paperless/OCRmyPDF-style) is reliable."""
    if min(img.size) >= min_side:
        return img
    scale = min_side / min(img.size)
    return img.resize(
        (max(1, int(img.width * scale)), max(1, int(img.height * scale))),
        Image.Resampling.LANCZOS,
    )


def _tesseract_osd_clockwise(img: Image.Image) -> tuple[int, float] | None:
    """Return (clockwise degrees, confidence) from Tesseract OSD when available."""
    try:
        import pytesseract
    except ImportError:
        return None

    try:
        osd = pytesseract.image_to_osd(
            np.array(_prepare_osd_image(img).convert("RGB")),
            config="--psm 0",
        )
    except Exception:  # noqa: BLE001
        return None

    rotate_match = re.search(r"Rotate:\s*(\d+)", osd)
    conf_match = re.search(r"Orientation confidence:\s*([\d.]+)", osd)
    if rotate_match is None:
        return None
    confidence = float(conf_match.group(1)) if conf_match else 0.0
    return int(rotate_match.group(1)), confidence


def _osd_cardinal_ccw(img: Image.Image, *, min_confidence: float | None = None) -> int | None:
    """Map Tesseract OSD clockwise rotation to CCW transpose degrees."""
    if not _osd_enabled():
        return None
    osd = _tesseract_osd_clockwise(img)
    if osd is None:
        return None
    rotate_cw, confidence = osd
    threshold = _osd_min_confidence() if min_confidence is None else min_confidence
    if confidence < threshold:
        return None
    return pdf_page_rotation_ccw(rotate_cw)


def _quarter_turn_env_override() -> int | None:
    """Optional ``DESKEW_QUARTER_TURN`` env: ``90``, ``270``, or ``-90``."""
    raw = os.getenv("DESKEW_QUARTER_TURN", "auto").strip().lower()
    if raw in {"90", "+90"}:
        return 90
    if raw in {"270", "-90"}:
        return 270
    return None


def _pick_cardinal_orientation(
    img: Image.Image, *, min_angle_deg: float = 0.5, deskew_context: str = "page"
) -> tuple[int, str]:
    """Choose the best 0/90/180/270° CCW correction for this page."""
    probe, probe_source, content_fill = _orientation_probe_image(img)
    _deskew_debug(
        "pick_start",
        size=f"{img.width}x{img.height}",
        probe_size=f"{probe.width}x{probe.height}",
        probe_source=probe_source,
        content_fill=round(content_fill, 3),
        min_angle_deg=min_angle_deg,
        quarter_turn_env=os.getenv("DESKEW_QUARTER_TURN", "auto"),
    )
    return _pick_cardinal_on_probe(
        probe,
        min_angle_deg=min_angle_deg,
        probe_source=probe_source,
        content_fill=content_fill,
        deskew_context=deskew_context,
    )


def _pick_cardinal_on_probe(
    probe: Image.Image,
    *,
    min_angle_deg: float,
    probe_source: str,
    content_fill: float,
    deskew_context: str = "page",
) -> tuple[int, str]:
    """Cardinal orientation on a probe image (full page or content crop)."""
    skew_hint = detect_page_angle(probe)
    _deskew_debug("skew_hint", degrees=round(skew_hint, 2))
    skew_only_min = (
        _SKEW_ONLY_CARDINAL_MIN_DEG
        if deskew_context == "region"
        else max(min_angle_deg, _SKEW_ONLY_CARDINAL_MIN_DEG)
    )
    if skew_only_min <= abs(skew_hint) < _NEAR_CARDINAL_SKEW_DEG:
        _deskew_debug("pick_result", branch="skew_only_no_cardinal", cardinal_ccw=0)
        return 0, "skew_only_no_cardinal"

    gray = _to_gray(probe)
    variances = _cardinal_variances(gray)
    score_0_180 = max(variances[0], variances[2])
    score_90_270 = max(variances[1], variances[3])
    _deskew_debug("variance_scores", **_variance_summary(gray))

    override = _quarter_turn_env_override()
    if override is not None:
        _deskew_debug("pick_result", branch="env_DESKEW_QUARTER_TURN", cardinal_ccw=override)
        return override, "env_DESKEW_QUARTER_TURN"

    osd_ccw = _osd_cardinal_ccw(probe)
    osd = _tesseract_osd_clockwise(_prepare_osd_image(probe)) if _osd_enabled() else None
    if osd is not None:
        _deskew_debug(
            "tesseract_osd",
            rotate_cw=osd[0],
            confidence=osd[1],
            mapped_ccw=osd_ccw,
            min_confidence=_osd_min_confidence(),
            used=osd_ccw is not None,
        )
    if osd_ccw is not None:
        _deskew_debug("pick_result", branch="tesseract_osd", cardinal_ccw=osd_ccw)
        return osd_ccw, "tesseract_osd"

    if score_90_270 > score_0_180 * 1.08:
        _deskew_debug(
            "branch",
            name="sideways",
            ratio=round(score_90_270 / (score_0_180 + 1e-6), 3),
        )
        picked = _pick_sideways_ccw(
            probe,
            skew_hint=skew_hint,
            allow_skew_hint_tie=probe_source == "content_bbox",
            full_page_ambiguous_skew_hint=(probe_source == "full_page" and content_fill >= 0.95),
        )
        _deskew_debug("pick_result", branch="sideways", cardinal_ccw=picked)
        return picked, "sideways"

    candidates: tuple[int, ...] = (0, 180)
    best_rot = 0
    best_rank = (2, 0.0)
    for rot in candidates:
        trial = probe if rot == 0 else _apply_ccw_transpose(probe, rot)
        card, conf = detect_cardinal_rotation(trial)
        if card == 0:
            rank = (0, -conf)
        elif card == 180:
            rank = (1, -conf)
        else:
            rank = (2, -conf)
        _deskew_debug(
            "upright_trial",
            trial_ccw=rot,
            detect_card=card,
            detect_conf=round(conf, 4),
            rank=rank,
        )
        if rank < best_rank:
            best_rank = rank
            best_rot = rot
    _deskew_debug("pick_result", branch="upright_0_or_180", cardinal_ccw=best_rot)
    return best_rot, "upright_0_or_180"


def open_rgb_image(image: Image.Image | bytes) -> Image.Image:
    """Load pixels as RGB without applying EXIF orientation metadata."""
    if isinstance(image, bytes):
        with Image.open(io.BytesIO(image)) as opened:
            return opened.convert("RGB")
    return image.convert("RGB")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_CARDINAL_SNAP_DEG = 1.0
_VARIANCE_TIE_ABS = 1.0
_VCENTER_MIN_CONFIDENCE = 0.13
_VERTICAL_AXIS_MARGIN = 0.5
_NEAR_CARDINAL_SKEW_DEG = 85.0
_SIDEWAYS_LOW_CONF = 0.25
_SKEW_HINT_CARDINAL_TOL = 15.0
# Only treat skew_hint as "no cardinal" in this band; tiny hints still run OSD/180 checks.
_SKEW_ONLY_CARDINAL_MIN_DEG = 15.0

_EXIF_ORIENTATION_CCW: dict[int, float] = {3: 180.0, 6: 270.0, 8: 90.0}

# PDF ``/Rotate`` is clockwise; map to CCW transpose (same convention as EXIF tag 6).
_PDF_ROTATION_CW_TO_CCW: dict[int, int] = {0: 0, 90: 270, 180: 180, 270: 90}


def pdf_page_rotation_ccw(rotation_clockwise: int) -> int:
    """Map PDF page ``/Rotate`` (clockwise degrees) to a CCW PIL transpose."""
    return _PDF_ROTATION_CW_TO_CCW.get(int(rotation_clockwise) % 360, 0)


def apply_pdf_page_rotation(
    img: Image.Image, rotation_clockwise: int, *, debug_label: str | None = None
) -> tuple[Image.Image, float]:
    """Apply PDF ``/Rotate`` to rendered page pixels (clockwise degrees)."""
    ccw = pdf_page_rotation_ccw(rotation_clockwise)
    if ccw == 0:
        return img, 0.0
    _begin_deskew_debug_trace()
    label_token = _deskew_debug_label.set(debug_label)
    try:
        _deskew_debug(
            "pdf_rotate",
            rotate_cw=rotation_clockwise,
            transpose_ccw=ccw,
            size_before=f"{img.width}x{img.height}",
        )
    finally:
        _deskew_debug_label.reset(label_token)
    return _apply_ccw_transpose(img, ccw), float(ccw)


def exif_orientation_ccw(img: Image.Image) -> float:
    """Return CCW degrees ``ImageOps.exif_transpose`` would apply (metadata only)."""
    try:
        exif = img.getexif()
        orientation = exif.get(274)
    except Exception:  # noqa: BLE001
        return 0.0
    if orientation is None:
        return 0.0
    try:
        tag = int(orientation)
    except (TypeError, ValueError):
        return 0.0
    return _EXIF_ORIENTATION_CCW.get(tag, 0.0)


def apply_exif_orientation(img: Image.Image) -> tuple[Image.Image, float]:
    """Apply EXIF orientation (camera JPEGs only — not used for scans)."""
    ccw = exif_orientation_ccw(img)
    return ImageOps.exif_transpose(img), ccw


def _variance_beats(current: float, best: float) -> bool:
    return current > best + _VARIANCE_TIE_ABS


def _prefer_skew_angle(
    candidate: float, best: float, *, candidate_var: float, best_var: float
) -> bool:
    if _variance_beats(candidate_var, best_var):
        return True
    if abs(candidate_var - best_var) > _VARIANCE_TIE_ABS:
        return False
    if abs(candidate) < abs(best):
        return True
    return abs(candidate) == abs(best) and candidate < best


def normalize_ccw_angle(degrees: float) -> float:
    """Map a net CCW correction into ``(-180, 180]`` for UI messages."""
    normalized = float(degrees) % 360.0
    if normalized > 180.0:
        normalized -= 360.0
    return normalized


def round_deskew_correction_ccw(net_ccw: float) -> float:
    """Normalized CCW correction for API fields (0 when none applied)."""
    if net_ccw == 0.0:
        return 0.0
    return round(normalize_ccw_angle(net_ccw), 1)


def detect_deskew_correction(
    img: Image.Image,
    *,
    min_angle_deg: float = 0.5,
    cardinal_confidence_threshold: float = 0.70,
) -> float:
    """Return the CCW correction ``deskew_image`` would apply, without mutating ``img``."""
    _, net_ccw = deskew_image(
        img.copy(),
        min_angle_deg=min_angle_deg,
        cardinal_confidence_threshold=cardinal_confidence_threshold,
    )
    return net_ccw


def _preview_cardinal_tilt(img: Image.Image) -> int:
    """Quarter-turn wrong in the preview (0, 90, 180, or 270)."""
    osd_ccw = _osd_cardinal_ccw(img)
    if osd_ccw is not None:
        return osd_ccw

    card, conf = detect_cardinal_rotation(img)
    if card != 0 and conf >= 0.05:
        return card

    gray = _to_gray(img)
    vc0 = _text_vertical_center(gray)
    vc2 = _text_vertical_center(np.rot90(gray, k=2))
    if vc0 is not None and vc2 is not None and abs(vc0 - vc2) > 0.08:
        return 180 if vc2 < vc0 else 0
    return 0


def detect_original_tilt(img: Image.Image, *, min_angle_deg: float = 0.5) -> float:
    """Tilt of content on the original scan (0° = upright); cardinal + fine skew."""
    cardinal = _preview_cardinal_tilt(img)
    fine, _source = _measure_fine_skew_angle(img)
    if abs(fine) >= _NEAR_CARDINAL_SKEW_DEG or abs(fine) > 20.0:
        fine = 0.0

    if cardinal != 0:
        tilt = float(cardinal) + fine
        if abs(tilt) >= min_angle_deg:
            return round(tilt, 1)
        return 0.0

    if min_angle_deg <= abs(fine) < _NEAR_CARDINAL_SKEW_DEG:
        return round(float(fine), 1)

    coarse = detect_page_angle(img, max_scan_dim=_fine_skew_scan_dim_for(img))
    if abs(coarse) >= min_angle_deg and abs(coarse) < _NEAR_CARDINAL_SKEW_DEG:
        return round(float(coarse), 1)
    return 0.0


def detect_preview_tilt(img: Image.Image, *, min_angle_deg: float = 0.5) -> float:
    """Alias for :func:`detect_original_tilt` (legacy name)."""
    return detect_original_tilt(img, min_angle_deg=min_angle_deg)


def preview_angle_from_corrections(
    original_angle: float,
    *,
    page_correction_ccw: float = 0.0,
) -> float:
    """Tilt on the deskewed page preview: ``original_angle - page_correction_ccw``."""
    if original_angle == 0.0 and page_correction_ccw == 0.0:
        return 0.0
    return round(
        normalize_ccw_angle(float(original_angle) - float(page_correction_ccw)),
        1,
    )


def reconcile_preview_tilt(
    measured: float,
    *,
    correction_ccw: float = 0.0,
    min_angle_deg: float = 0.5,
) -> float:
    """Merge measured preview tilt with a region deskew correction when cardinal detect fails."""
    if correction_ccw != 0.0:
        net = normalize_ccw_angle(correction_ccw)
        if abs(net) >= 45.0:
            return round(abs(net), 1)
        if abs(measured) < min_angle_deg and abs(net) >= min_angle_deg:
            return round(net, 1)
    if abs(measured) < min_angle_deg:
        return 0.0
    return round(float(measured), 1)


def detect_page_angle(img: Image.Image, *, max_scan_dim: int = 600) -> float:
    """Detect CCW rotation (degrees) that makes text lines horizontal (-90°..+90°)."""
    scan_img = img
    if max(img.size) > max_scan_dim:
        ratio = max_scan_dim / max(img.size)
        scan_img = img.resize(
            (max(1, int(img.width * ratio)), max(1, int(img.height * ratio))),
            Image.Resampling.LANCZOS,
        )

    gray = _to_gray(scan_img)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    base = Image.fromarray(binary)

    def _var(angle: float) -> float:
        arr = np.array(
            base.rotate(angle, expand=True, fillcolor=0, resample=Image.Resampling.NEAREST)
        )
        return float(np.var(arr.sum(axis=1).astype(np.float64)))

    best_angle = 0.0
    best_var = _var(0.0)

    def _update_best(candidate: float, candidate_var: float) -> None:
        nonlocal best_angle, best_var
        if _prefer_skew_angle(
            candidate, best_angle, candidate_var=candidate_var, best_var=best_var
        ):
            best_var = candidate_var
            best_angle = candidate

    for coarse_deg in range(-90, 91, 5):
        if coarse_deg == 0:
            continue
        _update_best(float(coarse_deg), _var(float(coarse_deg)))

    for da in range(-4, 5):
        if da == 0:
            continue
        fine_angle = best_angle + float(da)
        if -90.0 <= fine_angle <= 90.0:
            _update_best(fine_angle, _var(fine_angle))

    for step in range(-30, 31):
        if step == 0:
            continue
        fine_angle = best_angle + step * 0.5
        if -90.0 <= fine_angle <= 90.0:
            _update_best(fine_angle, _var(fine_angle))

    return best_angle


def pick_cardinal_ccw(img: Image.Image, *, min_angle_deg: float = 0.5) -> int:
    """Choose 0/90/180/270° CCW correction (content-bbox probe when the page has margins)."""
    cardinal_ccw, _branch = _pick_cardinal_orientation(img, min_angle_deg=min_angle_deg)
    return cardinal_ccw


def detect_cardinal_rotation(img: Image.Image) -> tuple[int, float]:
    """Fast cardinal detector for per-region crops (0/90/180/270 CCW)."""
    gray = _to_gray(img)
    variances = _cardinal_variances(gray)
    score_0_180 = max(variances[0], variances[2])
    score_90_270 = max(variances[1], variances[3])

    if score_0_180 >= score_90_270:
        vc0 = _text_vertical_center(gray)
        vc2 = _text_vertical_center(np.rot90(gray, k=2))
        if vc0 is not None and vc2 is not None:
            if vc2 < vc0:
                winner_k = 2
            else:
                winner_k = 0
            confidence = float(np.clip(abs(vc0 - vc2) * 2.0, 0.0, 1.0))
        else:
            sym_0 = _boundary_asymmetry(gray)
            sym_180 = _boundary_asymmetry(np.rot90(gray, k=2))
            if sym_180 > sym_0:
                winner_k = 2
                margin = abs(sym_180 - sym_0)
            else:
                winner_k = 0
                margin = abs(sym_0 - sym_180)
            total = abs(sym_0) + abs(sym_180) + 1e-6
            confidence = float(np.clip(margin / total, 0.0, 1.0))
    else:
        if variances[1] >= variances[3]:
            winner_k = 1
        else:
            winner_k = 3
        confidence_raw = (score_90_270 - score_0_180) / (score_90_270 + score_0_180 + 1e-6)
        confidence = float(np.clip(confidence_raw * 2.0, 0.0, 1.0))

    return winner_k * 90, confidence


def deskew_image(
    img: Image.Image,
    *,
    min_angle_deg: float = 0.5,
    cardinal_confidence_threshold: float = 0.70,
    debug_label: str | None = None,
    allow_page_cardinal: bool = True,
    deskew_context: str = "page",
) -> tuple[Image.Image, float]:
    """Straighten a page: quarter-turn (0/90/180/270), then fine skew in degrees.

    Cardinal picks sideways/upside-down (like paperless Tesseract OSD). Fine skew
    then corrects small scanner tilt (e.g. -5°) on the content probe.

    Returns ``(corrected_image, net_ccw_correction)`` for ``page_info["angle"]``.
    Does not read or apply EXIF tags.

    ``deskew_context="region"`` is for layout crops after page deskew: cardinal OSD
    still runs, but landscape 180° flip is skipped so crops are not double-rotated.

    When ``DESKEW_DEBUG=1``, pass ``debug_label`` (e.g. ``"page 1"``) to tag log lines.
    """
    del cardinal_confidence_threshold  # retained for API compatibility
    _begin_deskew_debug_trace()
    label_token = _deskew_debug_label.set(debug_label)
    try:
        if allow_page_cardinal:
            cardinal_ccw, cardinal_branch = _pick_cardinal_orientation(
                img, min_angle_deg=min_angle_deg, deskew_context=deskew_context
            )
        else:
            cardinal_ccw = 0
            cardinal_branch = "page_cardinal_disabled"
            _deskew_debug("pick_result", branch=cardinal_branch, cardinal_ccw=0)
        corrected, net_ccw = _deskew_from_cardinal(
            img,
            cardinal_ccw,
            min_angle_deg=min_angle_deg,
            cardinal_branch=cardinal_branch,
            deskew_context=deskew_context,
        )
        _deskew_debug(
            "done",
            net_ccw=round(net_ccw, 2),
            shown_ccw=round(normalize_ccw_angle(net_ccw), 2),
            size_after=f"{corrected.width}x{corrected.height}",
        )
        return corrected, net_ccw
    finally:
        _deskew_debug_label.reset(label_token)
