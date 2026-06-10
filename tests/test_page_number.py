from __future__ import annotations

from typing import cast

import pytest

from app.services.page_number import (
    assign_paragraph_role,
    canonicalize_page_counter_text,
    classify_page_number,
    find_page_number_in_words,
    footer_band_words,
    normalize_glued_counter_words,
    split_glued_counter_token,
    vertical_band_from_bbox,
)


@pytest.mark.parametrize(
    ("text", "x", "y", "tier"),
    [
        ("Seite 1 von 5", 1, 5, "high"),
        ("Seite 1/5", 1, 5, "high"),
        ("1/5", 1, 5, "high"),
        ("1 von 5", 1, 5, "high"),
        ("Page 1 of 5", 1, 5, "high"),
        ("S. 1/5", 1, 5, "high"),
        ("Seite 5", 5, None, "bare_labeled"),
        ("2von2", 2, 2, "high"),
        ("Seite 2von2", 2, 2, "high"),
    ],
)
def test_classify_page_number_variants(text: str, x: int, y: int | None, tier: str) -> None:
    match = classify_page_number(text)
    assert match is not None
    assert match.x == x
    assert match.y == y
    assert match.tier == tier


@pytest.mark.parametrize(
    "text",
    [
        "Summe 10,00",
        "1/5/2024",
        "5",
    ],
)
def test_classify_page_number_rejects_non_page_numbers(text: str) -> None:
    assert classify_page_number(text) is None


def test_classify_page_number_ocr_digit_normalization() -> None:
    match = classify_page_number("Seite l von 5")
    assert match is not None
    assert match.x == 1
    assert match.y == 5


def test_vertical_band_from_bbox() -> None:
    assert vertical_band_from_bbox([10, 10, 90, 80]) == "header"
    assert vertical_band_from_bbox([10, 900, 90, 980]) == "footer"
    assert vertical_band_from_bbox([10, 400, 90, 600]) == "body"


def test_assign_paragraph_role_page_number_in_footer() -> None:
    role = assign_paragraph_role(
        content="Seite 1 von 5",
        band="footer",
        emit_roles=True,
    )
    assert role == "pageNumber"


def test_assign_paragraph_role_low_tier_requires_band() -> None:
    assert assign_paragraph_role(content="see 1/5 items", band="body", emit_roles=True) is None
    assert (
        assign_paragraph_role(content="see 1/5 items", band="footer", emit_roles=True)
        == "pageNumber"
    )


def test_assign_paragraph_role_disabled() -> None:
    assert assign_paragraph_role(content="Seite 1 von 5", band="footer", emit_roles=False) is None


def test_find_page_number_in_words_joins_footer_tokens() -> None:
    words: list[dict[str, object]] = [
        {
            "content": "Seite",
            "polygon": [100.0, 910.0, 150.0, 910.0, 150.0, 930.0, 100.0, 930.0],
        },
        {
            "content": "1",
            "polygon": [160.0, 910.0, 180.0, 910.0, 180.0, 930.0, 160.0, 930.0],
        },
        {
            "content": "von",
            "polygon": [190.0, 910.0, 230.0, 910.0, 230.0, 930.0, 190.0, 930.0],
        },
        {
            "content": "5",
            "polygon": [240.0, 910.0, 260.0, 910.0, 260.0, 930.0, 240.0, 930.0],
        },
        {
            "content": "Summe",
            "polygon": [100.0, 400.0, 150.0, 400.0, 150.0, 420.0, 100.0, 420.0],
        },
    ]
    match = find_page_number_in_words(words)
    assert match is not None
    assert match.x == 1
    assert match.y == 5


def test_canonicalize_page_counter_text_glued() -> None:
    assert canonicalize_page_counter_text("Seite 2von2") == "Seite 2 von 2"
    assert canonicalize_page_counter_text("Footer 2von2 end") == "Footer 2 von 2 end"
    assert canonicalize_page_counter_text("1/5/2024") == "1/5/2024"


def test_split_glued_counter_token() -> None:
    assert split_glued_counter_token("2von2") == ["2", "von", "2"]
    assert split_glued_counter_token("2 von 2") is None


def test_normalize_glued_counter_words_splits_footer_token() -> None:
    words: list[dict[str, object]] = [
        {
            "content": "Seite",
            "polygon": [100.0, 910.0, 150.0, 910.0, 150.0, 930.0, 100.0, 930.0],
        },
        {
            "content": "2von2",
            "polygon": [160.0, 910.0, 260.0, 910.0, 260.0, 930.0, 160.0, 930.0],
            "confidence": 0.9,
        },
    ]
    normalized = normalize_glued_counter_words(words)
    contents = [str(w["content"]) for w in normalized]
    assert contents == ["Seite", "2", "von", "2"]
    polygon = cast(list[float], normalized[1]["polygon"])
    assert len(polygon) == 8


def test_normalize_glued_counter_words_splits_body_text_label() -> None:
    words: list[dict[str, object]] = [
        {
            "content": "Seite",
            "polygon": [100.0, 400.0, 150.0, 400.0, 150.0, 420.0, 100.0, 420.0],
        },
        {
            "content": "2von2",
            "polygon": [160.0, 400.0, 260.0, 400.0, 260.0, 420.0, 160.0, 420.0],
            "confidence": 0.9,
        },
    ]
    normalized = normalize_glued_counter_words(words)
    assert [str(w["content"]) for w in normalized] == ["Seite", "2", "von", "2"]


def test_footer_band_words_pixel_coordinates() -> None:
    words: list[dict[str, object]] = [
        {"content": "footer", "polygon": [0.0, 3400.0, 10.0, 3400.0, 10.0, 3450.0, 0.0, 3450.0]},
        {"content": "body", "polygon": [0.0, 100.0, 10.0, 100.0, 10.0, 150.0, 0.0, 150.0]},
    ]
    footer = footer_band_words(words, page_height=3508.0)
    assert len(footer) == 1
    assert footer[0]["content"] == "footer"
