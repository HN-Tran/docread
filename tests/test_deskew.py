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


def _wide_text_portrait_page() -> Image.Image:
    """Portrait page whose text lines span most of the width (typical document body)."""
    page = Image.new("RGB", (1654, 2339), "white")
    draw = ImageDraw.Draw(page)
    line = "Description column with item details qty unit price and line total amount EUR"
    for row in range(20):
        draw.text((110, 180 + row * 95), f"{row + 1:02d}  {line}", fill="black")
    return page


def _feeder_skew_page(*, lines: int = 15) -> Image.Image:
    """A4-like page with dense text (realistic ADF feeder skew target)."""
    page = Image.new("RGB", (2480, 3507), "white")
    draw = ImageDraw.Draw(page)
    for row in range(lines):
        label = f"Row {row + 1:02d}  Description line {row}  EUR {100 + row:.2f}"
        for index, char in enumerate(label):
            draw.text((200 + index * 10, 300 + row * 48), char, fill="black")
    return page


def _table_with_diagonal_grid(*, text_skew_deg: float = 5.0) -> Image.Image:
    """Simulate a table: horizontal text with a diagonal grid that confuses projection."""
    doc = Image.new("RGB", (900, 700), "white")
    draw = ImageDraw.Draw(doc)
    for offset in range(-900, 900, 28):
        draw.line((offset, 0, offset + 700, 700), fill=(210, 210, 210), width=1)
        draw.line((offset, 700, offset + 700, 0), fill=(210, 210, 210), width=1)
    for row, label in enumerate(("Pos", "3.1", "3.2", "3.3", "3.4", "3.5", "3.6")):
        y = 80 + row * 42
        for index, char in enumerate(f"{label}  1,000 ST  Grundfos Kondensat"):
            draw.text((40 + index * 14, y), char, fill="black")
    if text_skew_deg:
        doc = doc.rotate(text_skew_deg, expand=True, fillcolor="white")
    return doc


def test_tesseract_fine_skew_runs_on_document_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """Integration: Tesseract PSM 2 deskew on a full page (paperless-ngx / OCRmyPDF path)."""
    import shutil

    if shutil.which("tesseract") is None:
        pytest.skip("tesseract not installed")

    from app.services.deskew import _tesseract_deskew_degrees

    monkeypatch.setenv("DESKEW_TESSERACT_LANG", "osd")
    page = Image.new("RGB", (1200, 1600), "white")
    draw = ImageDraw.Draw(page)
    for row, label in enumerate(("Invoice 2024", "Line item A", "Line item B", "Total due")):
        for index, char in enumerate(label):
            draw.text((80 + index * 14, 200 + row * 48), char, fill="black")
    angle = _tesseract_deskew_degrees(page)
    assert angle is not None


def test_feeder_skew_tesseract_corrects_typical_adf_tilt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Integration: 0.5–4° feeder skew on a full page (Tesseract PSM 2, no projection apply)."""
    import shutil

    if shutil.which("tesseract") is None:
        pytest.skip("tesseract not installed")

    monkeypatch.setenv("DESKEW_TESSERACT_LANG", "osd")

    for applied_deg in (0.5, 1.0, 2.0, 3.0, 4.0):
        skewed = _feeder_skew_page().rotate(applied_deg, expand=True, fillcolor="white")
        _, net = deskew_image(skewed, allow_page_cardinal=False)
        assert abs(net + applied_deg) < 1.2, (applied_deg, net)


def test_upright_portrait_not_rotated_to_landscape_without_osd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: upright portrait pages must stay portrait when OSD is unavailable.

    The projection-variance fallback previously used per-row dark SUMS, which scale
    with row length and biased every portrait page toward a false 'sideways' (90°)
    reading. An upright A4 must not be flipped to landscape.
    """
    monkeypatch.setattr("app.services.deskew._osd_cardinal_ccw", lambda *_a, **_k: None)
    monkeypatch.setattr("app.services.deskew._tesseract_deskew_degrees", lambda *_a: 0.0)

    page = _wide_text_portrait_page()
    corrected, net = deskew_image(page)
    assert corrected.height > corrected.width, (net, corrected.size)
    assert net % 90 == 0, net


def test_cardinal_variance_is_dimension_independent() -> None:
    """_proj_variance must compare orientations by text structure, not row length.

    A wide-line upright portrait page must not score higher in the 90/270 axis
    (which would happen with the old dimension-scaled per-row sum).
    """
    from app.services.deskew import _cardinal_variances, _to_gray

    variances = _cardinal_variances(_to_gray(_wide_text_portrait_page()))
    score_0_180 = max(variances[0], variances[2])
    score_90_270 = max(variances[1], variances[3])
    assert score_90_270 <= score_0_180 * 1.08, (score_0_180, score_90_270)


def test_feeder_skew_upright_page_stays_near_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """Upright full page must not pick up spurious fine skew from orientation hints."""
    import shutil

    if shutil.which("tesseract") is None:
        pytest.skip("tesseract not installed")

    monkeypatch.setenv("DESKEW_TESSERACT_LANG", "osd")
    monkeypatch.setattr("app.services.deskew._osd_cardinal_ccw", lambda *_a, **_k: None)

    def _orientation_hint_77(img: Image.Image, **kwargs: object) -> float:
        if max(img.size) >= 500:
            return 77.0
        return 0.0

    monkeypatch.setattr("app.services.deskew.detect_page_angle", _orientation_hint_77)
    _, net = deskew_image(_feeder_skew_page())
    assert abs(net) < 1.0, net


def test_region_near_perpendicular_orientation_hint_not_applied_as_fine_skew(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Layout crops: spurious orientation hint must not apply when Tesseract reads upright."""
    monkeypatch.setattr("app.services.deskew._tesseract_deskew_degrees", lambda *_a: 0.0)
    monkeypatch.setattr("app.services.deskew.detect_page_angle", lambda *_a, **_k: -77.0)
    monkeypatch.setattr("app.services.deskew._osd_cardinal_ccw", lambda *_a, **_k: None)

    strip = _text_image()
    _, net = deskew_image(strip, deskew_context="region", debug_label="region strip")
    assert abs(net) < 1.0, net


def test_slightly_skewed_table_not_overcorrected_to_diamond_zone() -> None:
    """Regression: ~5° scanner tilt must not become ~45° from table grid lines."""
    doc = _table_with_diagonal_grid(text_skew_deg=5.0)
    page = Image.new("RGB", (1500, 2000), "white")
    page.paste(doc, ((page.width - doc.width) // 2, (page.height - doc.height) // 2))
    _, net = deskew_image(page)
    assert abs(net) <= 10.0, net


def test_small_island_upright_skips_page_fine_skew_without_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Curved book on large page: leave page upright; regions correct locally."""
    monkeypatch.setenv("DESKEW_DEBUG", "1")
    page = Image.new("RGB", (1500, 2000), "white")

    monkeypatch.setattr(
        "app.services.deskew._pick_cardinal_orientation",
        lambda _img, **kwargs: (0, "small_island_upright", 0.0),
    )

    _, net = deskew_image(page)
    trace = consume_deskew_debug_trace()
    assert net == 0.0, net
    assert any("small_island_no_upright_hint" in line for line in trace)


def test_diamond_zone_upright_hint_needs_two_tiles(monkeypatch: pytest.MonkeyPatch) -> None:
    from PIL import Image

    from app.services.deskew import _diamond_zone_upright_skew_hint

    monkeypatch.setattr(
        "app.services.deskew._skew_tile_candidates",
        lambda _img: [(-5.0, "tile_2_2")],
    )
    assert _diamond_zone_upright_skew_hint(Image.new("RGB", (100, 100), "white")) == 0.0


def test_diamond_zone_near_horizontal_returns_without_sideways(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: diamond-zone conflict must return upright, not fall through to sideways."""
    from PIL import Image

    from app.services.deskew import _pick_cardinal_on_probe

    monkeypatch.setenv("DESKEW_DEBUG", "1")
    probe = Image.new("RGB", (284, 304), "white")
    monkeypatch.setattr("app.services.deskew._tesseract_deskew_degrees", lambda _img: None)
    monkeypatch.setattr("app.services.deskew.detect_page_angle", lambda _img, **kwargs: -49.0)
    monkeypatch.setattr(
        "app.services.deskew._diamond_zone_skew_conflicts_with_tiles",
        lambda _probe, _hint, **kwargs: True,
    )
    monkeypatch.setattr(
        "app.services.deskew._diamond_zone_upright_skew_hint",
        lambda _probe, **kwargs: 1.5,
    )

    cardinal, branch, hint = _pick_cardinal_on_probe(
        probe,
        min_angle_deg=0.5,
        probe_source="content_bbox",
        content_fill=0.029,
        full_img=Image.new("RGB", (1500, 2000), "white"),
    )
    assert cardinal == 0
    assert branch == "diamond_zone_near_horizontal"
    assert hint == 1.5


def test_small_island_upright_skips_sideways_on_tiny_content_bbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PIL import Image

    from app.services.deskew import _pick_cardinal_on_probe

    monkeypatch.setenv("DESKEW_DEBUG", "1")
    probe = Image.new("RGB", (284, 304), "white")
    monkeypatch.setattr("app.services.deskew._tesseract_deskew_degrees", lambda _img: None)
    monkeypatch.setattr("app.services.deskew.detect_page_angle", lambda _img, **kwargs: -49.0)
    monkeypatch.setattr(
        "app.services.deskew._diamond_zone_skew_conflicts_with_tiles",
        lambda _probe, _hint, **kwargs: False,
    )
    monkeypatch.setattr(
        "app.services.deskew._diamond_zone_upright_skew_hint",
        lambda _probe, **kwargs: 2.0,
    )

    cardinal, branch, hint = _pick_cardinal_on_probe(
        probe,
        min_angle_deg=0.5,
        probe_source="content_bbox",
        content_fill=0.029,
        full_img=Image.new("RGB", (1500, 2000), "white"),
    )
    assert cardinal == 0
    assert branch == "small_island_upright"
    assert hint == 2.0


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


def test_detect_preview_tilt_upside_down_includes_cardinal_and_fine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.deskew import detect_preview_tilt

    monkeypatch.setattr("app.services.deskew._osd_cardinal_ccw", lambda *_a, **_k: 180)
    monkeypatch.setattr("app.services.deskew._tesseract_deskew_degrees", lambda *_a: 0.0)

    doc = Image.new("RGB", (700, 1000), "white")
    draw = ImageDraw.Draw(doc)
    for index, char in enumerate("INVOICE DOCUMENT"):
        draw.text((40 + index * 20, 450), char, fill="black")
    upside_down = doc.transpose(Image.Transpose.ROTATE_180)
    tilt = detect_preview_tilt(upside_down)
    assert abs(tilt) >= 175.0, tilt


def test_region_narrow_strip_skips_upside_down_flip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: wide table-row crops must not get a spurious 180° + fine skew."""
    monkeypatch.setenv("DESKEW_DEBUG", "1")
    monkeypatch.setattr("app.services.deskew._osd_cardinal_ccw", lambda _img, **kwargs: None)

    strip = Image.new("RGB", (1100, 160), "white")
    draw = ImageDraw.Draw(strip)
    for index, char in enumerate("Einh. Text    Einzelpreis    Gesamt"):
        draw.text((40 + index * 16, 70), char, fill="black")
    strip = strip.rotate(5, expand=True, fillcolor="white")

    _, net = deskew_image(strip, deskew_context="region", debug_label="region 2")
    trace = consume_deskew_debug_trace()
    assert abs(net) <= 10.0, net
    assert any("region_fine_skew_only" in line for line in trace)
    assert not any("cardinal_ccw=180" in line for line in trace)


def test_region_deskew_skips_landscape_flip_on_fine_skew_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Region crops after page deskew: fine skew must not trigger +180° landscape flip."""
    import shutil

    if shutil.which("tesseract") is None:
        pytest.skip("tesseract not installed")

    monkeypatch.setenv("DESKEW_DEBUG", "1")
    monkeypatch.setenv("DESKEW_TESSERACT_LANG", "osd")
    monkeypatch.setattr(
        "app.services.deskew._osd_cardinal_ccw",
        lambda _img, **kwargs: 0,
    )
    page = _feeder_skew_page(lines=8)
    crop = page.crop((200, 300, 2200, 700)).rotate(-3, expand=True, fillcolor="white")
    _, net = deskew_image(
        crop,
        allow_page_cardinal=True,
        deskew_context="region",
        debug_label="region 0",
    )
    trace = consume_deskew_debug_trace()
    assert 1.5 <= abs(net) <= 4.5, net
    assert any("region_after_page" in line for line in trace)
    assert not any("landscape_flip_apply" in line for line in trace)


def test_page_deskew_applies_fine_skew_after_osd_quarter_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After OSD 90°, residual scanner tilt from Tesseract PSM 2 is added to net_ccw."""
    monkeypatch.setattr(
        "app.services.deskew._osd_cardinal_ccw",
        lambda _img, **kwargs: 90,
    )
    monkeypatch.setattr(
        "app.services.deskew._tesseract_deskew_degrees",
        lambda _img: -5.0,
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
    assert abs(net - 85.0) <= 1.0, net


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


def test_heuristic_180_can_be_enabled_for_upside_down_without_osd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy non-OSD 180° correction is opt-in because it can false-positive."""
    monkeypatch.setenv("DESKEW_HEURISTIC_180", "1")
    monkeypatch.setattr("app.services.deskew._osd_cardinal_ccw", lambda *_a, **_k: None)
    monkeypatch.setattr("app.services.deskew._tesseract_deskew_degrees", lambda *_a: 0.0)

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


def test_bottom_weighted_upright_scan_stays_zero_without_osd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: text position on a valid upright page is not 180° evidence."""
    monkeypatch.setenv("DESKEW_DEBUG", "1")
    monkeypatch.delenv("DESKEW_HEURISTIC_180", raising=False)
    monkeypatch.setattr("app.services.deskew._osd_cardinal_ccw", lambda *_a, **_k: None)
    monkeypatch.setattr("app.services.deskew._tesseract_deskew_degrees", lambda *_a: 0.0)

    base = Image.new("RGB", (600, 400), "white")
    draw = ImageDraw.Draw(base)
    for index, char in enumerate("SCANNED DOCUMENT"):
        draw.text((40 + index * 18, 240), char, fill="black")

    _, net = deskew_image(base, debug_label="bottom weighted")
    trace = consume_deskew_debug_trace()
    assert net == 0.0, net
    assert any("upright_no_heuristic_180" in line for line in trace)
    assert not any("landscape_flip_apply" in line for line in trace)


def test_bottom_weighted_layout_crop_tilt_stays_zero_without_osd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: layout angle reporting must not mark upright crops as 180°."""
    from app.services.deskew import detect_original_tilt

    monkeypatch.delenv("DESKEW_HEURISTIC_180", raising=False)
    monkeypatch.setattr("app.services.deskew._osd_cardinal_ccw", lambda *_a, **_k: None)
    monkeypatch.setattr("app.services.deskew._tesseract_deskew_degrees", lambda *_a: 0.0)

    crop = Image.new("RGB", (800, 300), "white")
    draw = ImageDraw.Draw(crop)
    for index, char in enumerate("Einh. Text    Einzelpreis    Gesamt"):
        draw.text((40 + index * 12, 220), char, fill="black")

    assert detect_original_tilt(crop) == 0.0


def test_detect_page_angle_near_80_not_snapped_to_opposite_90() -> None:
    """Projection hint may read ~80° on heavy tilt; it must resolve to a cardinal
    orientation (0/180), never get applied as a spurious ~80° fine skew."""
    from app.services.deskew import detect_page_angle

    skewed = _text_image().rotate(80, expand=True, fillcolor="white")
    angle = detect_page_angle(skewed)
    assert -82.0 <= angle <= -78.0, angle

    _, net = deskew_image(skewed)
    assert abs(net) < 15.0 or net == 180.0, net


def test_deskew_image_does_not_add_spurious_180_after_large_skew() -> None:
    """~82° tilt is not fine deskew; Tesseract must not stack a spurious 180° on top."""
    skewed = _text_image().rotate(82, expand=True, fillcolor="white")
    _, net = deskew_image(skewed)
    assert abs(net) < 15.0 or net == 180.0, net


def test_deskew_corrects_upside_down_after_large_skew() -> None:
    """Upside-down + heavy tilt: cardinal 180° flip, not projection fine skew."""
    from app.services.deskew import _text_vertical_center, _to_gray

    upside_down = _text_image().transpose(Image.Transpose.ROTATE_180)
    skewed = upside_down.rotate(80, expand=True, fillcolor="white")
    corrected, net = deskew_image(skewed)
    assert net in (0.0, 180.0), net
    vcenter = _text_vertical_center(_to_gray(corrected))
    assert vcenter is not None and vcenter < 0.5, vcenter


def test_deskew_image_applies_upside_down_correction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.deskew._osd_cardinal_ccw", lambda *_a, **_k: 180)
    monkeypatch.setattr("app.services.deskew._tesseract_deskew_degrees", lambda *_a: 0.0)

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
