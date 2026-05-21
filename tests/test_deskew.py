from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from app.services.deskew import (
    apply_exif_orientation,
    consume_deskew_debug_trace,
    deskew_image,
    exif_orientation_ccw,
    open_rgb_image,
)


def _text_image() -> Image.Image:
    img = Image.new("RGB", (400, 200), "white")
    draw = ImageDraw.Draw(img)
    for index, char in enumerate("HELLO WORLD TEST"):
        draw.text((10 + index * 22, 80), char, fill="black")
    return img


def test_open_rgb_image_ignores_exif_orientation() -> None:
    source = _text_image()
    exif = source.getexif()
    exif[274] = 6
    buf = BytesIO()
    source.save(buf, format="JPEG", exif=exif)
    raw = open_rgb_image(buf.getvalue())
    with Image.open(BytesIO(buf.getvalue())) as opened:
        oriented, ccw = apply_exif_orientation(opened)
    assert ccw == 270.0
    assert raw.size == (400, 200)
    assert oriented.size == (200, 400)


def test_detect_deskew_correction_reports_90_degree_rotation() -> None:
    rotated = _text_image().transpose(Image.Transpose.ROTATE_90)
    correction = deskew_image(rotated)[1]
    assert correction in {90.0, 270.0}


def test_deskew_without_page_cardinal_skips_quarter_turn() -> None:
    base = Image.new("RGB", (600, 400), "white")
    draw = ImageDraw.Draw(base)
    for index, char in enumerate("SCANNED DOCUMENT"):
        draw.text((40 + index * 18, 180), char, fill="black")
    sideways = base.transpose(Image.Transpose.ROTATE_270)
    _, net = deskew_image(sideways, allow_page_cardinal=False)
    assert net == 0.0, net


def test_tesseract_osd_branch_skips_landscape_flip(monkeypatch: pytest.MonkeyPatch) -> None:
    """OSD quarter-turn must not get an extra 180° from low-confidence landscape flip."""
    monkeypatch.setenv("DESKEW_DEBUG", "1")
    monkeypatch.setattr(
        "app.services.deskew._osd_cardinal_ccw",
        lambda _img, **kwargs: 90,
    )

    doc = Image.new("RGB", (700, 1000), "white")
    draw = ImageDraw.Draw(doc)
    for index, char in enumerate("INVOICE DOCUMENT"):
        draw.text((40 + index * 20, 450), char, fill="black")
    doc = doc.transpose(Image.Transpose.ROTATE_270)
    page = Image.new("RGB", (2480, 3507), "white")
    page.paste(doc, ((page.width - doc.width) // 2, (page.height - doc.height) // 2))

    _, net = deskew_image(page)
    trace = consume_deskew_debug_trace()
    assert net == 90.0, net
    assert any("authoritative_cardinal" in line for line in trace)
    assert not any("landscape_flip_apply" in line for line in trace)


def test_detect_original_tilt_on_upright_and_sideways_crop() -> None:
    from app.services.deskew import _apply_ccw_transpose, detect_original_tilt

    doc = Image.new("RGB", (700, 1000), "white")
    draw = ImageDraw.Draw(doc)
    for index, char in enumerate("INVOICE DOCUMENT"):
        draw.text((40 + index * 20, 450), char, fill="black")
    sideways = doc.transpose(Image.Transpose.ROTATE_270)
    upright = _apply_ccw_transpose(sideways, 90)
    assert detect_original_tilt(upright) == 0.0
    assert abs(detect_original_tilt(sideways)) >= 85.0


def test_preview_angle_from_corrections_subtracts_page_ccw() -> None:
    from app.services.deskew import preview_angle_from_corrections

    assert preview_angle_from_corrections(180.0, page_correction_ccw=0.0) == 180.0
    assert preview_angle_from_corrections(0.0, page_correction_ccw=180.0) == 180.0
    assert preview_angle_from_corrections(180.0, page_correction_ccw=180.0) == 0.0


def test_round_deskew_correction_ccw_normalizes() -> None:
    from app.services.deskew import round_deskew_correction_ccw

    assert round_deskew_correction_ccw(0.0) == 0.0
    assert round_deskew_correction_ccw(84.5) == 84.5
    assert round_deskew_correction_ccw(270.0) == -90.0


def test_reconcile_preview_tilt_uses_cardinal_correction() -> None:
    from app.services.deskew import reconcile_preview_tilt

    assert reconcile_preview_tilt(-0.5, correction_ccw=180.0) == 180.0
    assert reconcile_preview_tilt(0.0, correction_ccw=-5.5) == -5.5
    assert reconcile_preview_tilt(4.0, correction_ccw=0.0) == 4.0


def test_detect_preview_tilt_upside_down_includes_cardinal_and_fine() -> None:
    from app.services.deskew import detect_preview_tilt

    doc = Image.new("RGB", (700, 1000), "white")
    draw = ImageDraw.Draw(doc)
    for index, char in enumerate("INVOICE DOCUMENT"):
        draw.text((40 + index * 20, 450), char, fill="black")
    upside_down = doc.transpose(Image.Transpose.ROTATE_180)
    tilt = detect_preview_tilt(upside_down)
    assert abs(tilt) >= 175.0, tilt


def test_region_deskew_skips_landscape_flip_on_fine_skew_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Region crops after page deskew: fine skew must not trigger +180° landscape flip."""
    monkeypatch.setenv("DESKEW_DEBUG", "1")
    monkeypatch.setattr(
        "app.services.deskew._osd_cardinal_ccw",
        lambda _img, **kwargs: 0,
    )
    skewed = _text_image().rotate(-5, expand=True, fillcolor="white")
    _, net = deskew_image(
        skewed,
        allow_page_cardinal=True,
        deskew_context="region",
        debug_label="region 0",
    )
    trace = consume_deskew_debug_trace()
    assert 4.0 <= abs(net) <= 6.0, net
    assert any("region_after_page" in line for line in trace)
    assert not any("landscape_flip_apply" in line for line in trace)


def test_page_deskew_applies_fine_skew_after_osd_quarter_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After OSD 90°, residual scanner tilt (~5°) should appear in net_ccw."""
    monkeypatch.setattr(
        "app.services.deskew._osd_cardinal_ccw",
        lambda _img, **kwargs: 90,
    )
    doc = Image.new("RGB", (700, 1000), "white")
    draw = ImageDraw.Draw(doc)
    for index, char in enumerate("INVOICE DOCUMENT"):
        draw.text((40 + index * 20, 450), char, fill="black")
    doc = doc.rotate(-5, expand=True, fillcolor="white")
    doc = doc.transpose(Image.Transpose.ROTATE_270)

    page = Image.new("RGB", (2480, 3507), "white")
    page.paste(doc, ((page.width - doc.width) // 2, (page.height - doc.height) // 2))

    _, net = deskew_image(page)
    assert abs(net - 90.0) >= 4.0, net
    assert abs(net - 90.0) <= 6.0, net


def test_small_document_island_on_large_page_uses_content_bbox() -> None:
    """A4 scan with a small sideways island: orient from content, not page margins."""
    doc = Image.new("RGB", (700, 1000), "white")
    draw = ImageDraw.Draw(doc)
    for index, char in enumerate("INVOICE DOCUMENT"):
        draw.text((40 + index * 20, 450), char, fill="black")
    doc = doc.transpose(Image.Transpose.ROTATE_270)

    page = Image.new("RGB", (2480, 3507), "white")
    left = (page.width - doc.width) // 2
    top = (page.height - doc.height) // 2
    page.paste(doc, (left, top))

    _, net = deskew_image(page)
    assert net == 90.0, net


def test_sideways_scan_quarter_turn_matches_orientation() -> None:
    """Each 90° storage orientation gets the opposite CCW correction (not projection sign)."""
    base = Image.new("RGB", (600, 400), "white")
    draw = ImageDraw.Draw(base)
    for index, char in enumerate("SCANNED DOCUMENT"):
        draw.text((40 + index * 18, 180), char, fill="black")
    _, net_90 = deskew_image(base.transpose(Image.Transpose.ROTATE_90))
    _, net_270 = deskew_image(base.transpose(Image.Transpose.ROTATE_270))
    assert net_90 == 270.0, net_90
    assert net_270 == 90.0, net_270


def test_large_upside_down_scan_gets_180_flip() -> None:
    """Regression: landscape flip must not depend on a tight vcenter threshold."""
    base = Image.new("RGB", (600, 400), "white")
    draw = ImageDraw.Draw(base)
    for index, char in enumerate("SCANNED DOCUMENT"):
        draw.text((40 + index * 18, 180), char, fill="black")
    _, net = deskew_image(base.transpose(Image.Transpose.ROTATE_180))
    assert net == 180.0, net


def test_upright_scan_not_false_negative_90() -> None:
    """Upright pages must not get a spurious -90° (270° CCW) from projection noise."""
    base = Image.new("RGB", (600, 400), "white")
    draw = ImageDraw.Draw(base)
    for index, char in enumerate("SCANNED DOCUMENT"):
        draw.text((40 + index * 18, 180), char, fill="black")
    _, net = deskew_image(base)
    assert net == 0.0, net


def test_detect_page_angle_near_80_not_snapped_to_opposite_90() -> None:
    from app.services.deskew import detect_page_angle

    skewed = _text_image().rotate(80, expand=True, fillcolor="white")
    angle = detect_page_angle(skewed)
    assert -82.0 <= angle <= -78.0, angle

    _, net = deskew_image(skewed)
    assert -84.0 <= net <= -76.0, net


def test_deskew_image_does_not_add_spurious_180_after_large_skew() -> None:
    skewed = _text_image().rotate(82, expand=True, fillcolor="white")
    _, net = deskew_image(skewed)
    assert -84.0 <= net <= -80.0, net


def test_deskew_corrects_upside_down_after_large_skew() -> None:
    from app.services.deskew import _text_vertical_center, _to_gray

    upside_down = _text_image().transpose(Image.Transpose.ROTATE_180)
    skewed = upside_down.rotate(80, expand=True, fillcolor="white")
    corrected, net = deskew_image(skewed)
    assert abs(net) >= 78.0
    vcenter = _text_vertical_center(_to_gray(corrected))
    assert vcenter is not None and vcenter < 0.5, vcenter


def test_deskew_image_applies_upside_down_correction() -> None:
    upside_down = _text_image().transpose(Image.Transpose.ROTATE_180)
    _, net = deskew_image(upside_down)
    assert net == 180.0


def test_deskew_debug_does_not_change_correction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DESKEW_DEBUG", "1")
    base = _text_image()
    sideways = base.transpose(Image.Transpose.ROTATE_270)
    _, net_off = deskew_image(sideways)
    monkeypatch.delenv("DESKEW_DEBUG", raising=False)
    _, net_on = deskew_image(sideways)
    assert net_off == net_on


def test_deskew_debug_collects_trace_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DESKEW_DEBUG", "1")
    base = _text_image()
    deskew_image(base.transpose(Image.Transpose.ROTATE_270), debug_label="page 1")
    trace = consume_deskew_debug_trace()
    assert trace
    assert any("sideways" in line for line in trace)
    assert any(line.startswith("[page 1]") for line in trace)
    assert consume_deskew_debug_trace() == []


def test_pdf_page_rotation_maps_clockwise_to_ccw_transpose() -> None:
    from app.services.deskew import pdf_page_rotation_ccw

    assert pdf_page_rotation_ccw(0) == 0
    assert pdf_page_rotation_ccw(90) == 270
    assert pdf_page_rotation_ccw(180) == 180
    assert pdf_page_rotation_ccw(270) == 90


def test_exif_orientation_tag_maps_to_ccw_degrees() -> None:
    img = _text_image()
    exif = img.getexif()
    exif[274] = 6
    assert exif_orientation_ccw(img) == 270.0
    oriented, ccw = apply_exif_orientation(img)
    assert ccw == 270.0
    assert oriented.size == (200, 400)
