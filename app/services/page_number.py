"""Printed page-number parsing and Azure paragraph role assignment."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

PageNumberTier = Literal["high", "medium", "low", "bare_labeled"]
VerticalBand = Literal["header", "footer", "body"]
ParagraphRole = Literal["pageNumber", "pageFooter", "pageHeader"]

# Normalized 0–1000 layout coordinates (matches layout region bboxes).
HEADER_Y_MAX = 120.0
FOOTER_Y_MIN = 880.0

_DIGIT_NORMALIZE = str.maketrans(
    {
        "O": "0",
        "o": "0",
        "l": "1",
        "I": "1",
        "|": "1",
        "S": "5",
        "s": "5",
        "B": "8",
    }
)

_PAGE_LABEL = r"(?:seite|page|bl\.?|s\.?)"
_SEP = r"(?:von|of|/|\\|–|-)"
_NUM = r"([0-9OlI|]{1,3})"

_RE_FULL_LABELED = re.compile(
    rf"^\s*(?:{_PAGE_LABEL}\s*)?{_NUM}\s*{_SEP}\s*{_NUM}\s*$",
    re.IGNORECASE,
)
_RE_FULL_BARE = re.compile(
    rf"^\s*{_NUM}\s*{_SEP}\s*{_NUM}\s*$",
    re.IGNORECASE,
)
_RE_BARE_LABELED = re.compile(
    rf"^\s*{_PAGE_LABEL}\s*{_NUM}\s*$",
    re.IGNORECASE,
)
_RE_MEDIUM = re.compile(
    rf"(?:{_PAGE_LABEL}\s*{_NUM}\s*{_SEP}\s*{_NUM}|{_PAGE_LABEL}\s*{_NUM}\s*"
    rf"(?:von|of)\s*{_NUM})",
    re.IGNORECASE,
)
_RE_LOW = re.compile(rf"\b{_NUM}\s*{_SEP}\s*{_NUM}\b")


@dataclass(frozen=True)
class PageNumberMatch:
    x: int
    y: int | None
    tier: PageNumberTier


def normalize_page_number_digits(text: str) -> str:
    """Normalize OCR confusions inside digit tokens only."""
    return text.translate(_DIGIT_NORMALIZE)


def _parse_int_token(token: str) -> int | None:
    try:
        return int(normalize_page_number_digits(token))
    except ValueError:
        return None


def _parse_pair(text: str) -> tuple[int, int] | None:
    stripped = text.strip()
    for pattern in (_RE_FULL_LABELED, _RE_FULL_BARE):
        match = pattern.match(stripped)
        if not match:
            continue
        x_val = _parse_int_token(match.group(1))
        y_val = _parse_int_token(match.group(2))
        if x_val is None or y_val is None:
            continue
        if 1 <= x_val <= y_val <= 999:
            return x_val, y_val
    return None


def _parse_bare_labeled(text: str) -> int | None:
    match = _RE_BARE_LABELED.match(text.strip())
    if not match:
        return None
    x_val = _parse_int_token(match.group(1))
    if x_val is None:
        return None
    if 1 <= x_val <= 999:
        return x_val
    return None


def _is_date_like_remainder(text: str, end: int) -> bool:
    tail = text[end:].lstrip()
    return tail.startswith("/") and len(tail) > 1 and tail[1].isdigit()


def classify_page_number(text: str) -> PageNumberMatch | None:
    """Classify printed page numbering text (e.g. ``Seite 1 von 5``, ``1/5``)."""
    stripped = text.strip()
    if not stripped:
        return None

    pair = _parse_pair(stripped)
    if pair is not None:
        return PageNumberMatch(x=pair[0], y=pair[1], tier="high")

    bare_x = _parse_bare_labeled(stripped)
    if bare_x is not None:
        return PageNumberMatch(x=bare_x, y=None, tier="bare_labeled")

    medium = _RE_MEDIUM.search(stripped)
    if medium is not None:
        fragment = medium.group(0)
        pair = _parse_pair(fragment)
        if pair is not None:
            return PageNumberMatch(x=pair[0], y=pair[1], tier="medium")
        bare_x = _parse_bare_labeled(fragment)
        if bare_x is not None:
            return PageNumberMatch(x=bare_x, y=None, tier="bare_labeled")

    low = _RE_LOW.search(stripped)
    if low is not None:
        if _is_date_like_remainder(stripped, low.end()):
            return None
        pair = _parse_pair(low.group(0))
        if pair is not None:
            return PageNumberMatch(x=pair[0], y=pair[1], tier="low")

    return None


def vertical_band_from_bbox(
    bbox_2d: object,
    *,
    polygon: object = None,
) -> VerticalBand | None:
    """Map a layout bbox (0–1000 space) to header/footer/body."""
    y_top: float | None = None
    y_bottom: float | None = None

    rect = _bbox_to_rect_internal(bbox_2d)
    if rect is not None:
        y_top, y_bottom = rect[1], rect[3]
    else:
        poly = _coerce_polygon_internal(polygon)
        if poly is not None:
            ys = poly[1::2]
            y_top, y_bottom = min(ys), max(ys)

    if y_top is None or y_bottom is None:
        return None
    if y_bottom > FOOTER_Y_MIN:
        return "footer"
    if y_top < HEADER_Y_MAX:
        return "header"
    return "body"


def assign_paragraph_role(
    *,
    content: str,
    band: VerticalBand | None,
    emit_roles: bool,
) -> ParagraphRole | None:
    if not emit_roles:
        return None

    match = classify_page_number(content)
    if match is not None:
        if match.tier in {"high", "medium", "bare_labeled"}:
            return "pageNumber"
        if match.tier == "low" and band in {"header", "footer"}:
            return "pageNumber"

    if band == "footer":
        return "pageFooter"
    if band == "header":
        return "pageHeader"
    return None


def _polygon_y_range(polygon: object) -> tuple[float, float] | None:
    poly = _coerce_polygon_internal(polygon)
    if poly is None:
        return None
    ys = poly[1::2]
    return min(ys), max(ys)


def find_page_number_in_words(
    words: list[dict[str, object]],
    *,
    footer_y_min: float = FOOTER_Y_MIN,
    coord_max: float = 1000.0,
) -> PageNumberMatch | None:
    """Join footer-band words (normalized coords) and parse page numbering."""
    threshold = footer_y_min if coord_max <= 1000.0 else footer_y_min * coord_max / 1000.0
    footer_words: list[tuple[float, float, str]] = []
    for entry in words:
        if not isinstance(entry, dict):
            continue
        content = str(entry.get("content") or "").strip()
        if not content:
            continue
        y_range = _polygon_y_range(entry.get("polygon"))
        if y_range is None:
            continue
        _y_top, y_bottom = y_range
        if y_bottom <= threshold:
            continue
        poly = _coerce_polygon_internal(entry.get("polygon"))
        if poly is None:
            continue
        xs = poly[0::2]
        x_min = min(xs)
        y_center = sum(y_range) / 2.0
        footer_words.append((y_center, x_min, content))

    if not footer_words:
        return None

    footer_words.sort(key=lambda item: (item[0], item[1]))
    joined = " ".join(word for _, _, word in footer_words)
    return classify_page_number(joined)


def footer_band_words(
    words: list[dict[str, object]],
    *,
    page_height: float,
    footer_ratio: float = 0.12,
) -> list[dict[str, object]]:
    """Return words whose bottom edge lies in the bottom ``footer_ratio`` of the page."""
    if page_height <= 0:
        return []
    threshold = page_height * (1.0 - footer_ratio)
    out: list[dict[str, object]] = []
    for entry in words:
        if not isinstance(entry, dict):
            continue
        y_range = _polygon_y_range(entry.get("polygon"))
        if y_range is None:
            continue
        if y_range[1] >= threshold:
            out.append(entry)
    return out


def _bbox_to_rect_internal(value: object) -> tuple[float, float, float, float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    if not all(isinstance(point, (int, float)) for point in value):
        return None
    x1, y1, x2, y2 = (float(point) for point in value)
    return x1, y1, x2, y2


def _coerce_polygon_internal(value: object) -> list[float] | None:
    if not isinstance(value, (list, tuple)):
        return None
    if value and all(isinstance(point, (int, float)) for point in value):
        if len(value) < 8 or len(value) % 2 != 0:
            return None
        try:
            return [float(point) for point in value]
        except (TypeError, ValueError):
            return None
    return None
