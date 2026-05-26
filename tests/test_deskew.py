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


def test_pick_fine_skew_prefers_horizontal_tiles_over_diamond_zone() -> None:
    """Table grids can peak at ~45° while text tiles read near 0°."""
    from app.services.deskew import _is_skew_tile_source, _pick_fine_skew_from_candidates

    candidates = [
        (-49.0, "content_bbox"),
        (-45.0, "tile_0_0"),
        (-49.5, "tile_1_1"),
        (-1.0, "probe_tile_1_2"),
        (2.5, "probe_tile_0_1"),
        (2.0, "tile_2_2"),
    ]
    angle, source = _pick_fine_skew_from_candidates(candidates, default_source="content_bbox")
    assert abs(angle - 2.5) <= 1.0, (angle, source)
    assert _is_skew_tile_source(source) or source == "tile_consensus"


def test_region_skew_hint_does_not_override_tile_consensus() -> None:
    from app.services.deskew import _pick_fine_skew_from_candidates

    candidates = [
        (-10.0, "content_bbox"),
        (-51.0, "full_page"),
        (3.0, "tile_0_1"),
        (2.5, "tile_1_2"),
        (1.5, "tile_2_1"),
        (2.0, "probe_tile_1_1"),
    ]
    angle, source = _pick_fine_skew_from_candidates(
        candidates,
        default_source="content_bbox",
        cardinal_skew_hint=-10.0,
        trust_cardinal_skew_hint=False,
    )
    assert angle > 0.0, (angle, source)
    assert abs(angle - 2.5) <= 1.0, (angle, source)


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


def test_slightly_skewed_table_not_overcorrected_to_diamond_zone() -> None:
    """Regression: ~5° scanner tilt must not become ~45° from table grid lines."""
    doc = _table_with_diagonal_grid(text_skew_deg=5.0)
    page = Image.new("RGB", (1500, 2000), "white")
    page.paste(doc, ((page.width - doc.width) // 2, (page.height - doc.height) // 2))
    _, net = deskew_image(page)
    assert abs(net) <= 10.0, net


def test_pick_fine_skew_zero_hint_does_not_block_tile_consensus() -> None:
    from app.services.deskew import _pick_fine_skew_from_candidates

    candidates = [
        (-49.0, "content_bbox"),
        (-1.0, "probe_tile_1_2"),
        (2.0, "probe_tile_2_2"),
    ]
    angle, source = _pick_fine_skew_from_candidates(
        candidates,
        default_source="content_bbox",
        cardinal_skew_hint=0.0,
        min_angle_deg=0.5,
    )
    assert abs(angle) <= 2.0, (angle, source)


def test_small_island_ignores_spurious_content_bbox_diamond_skew() -> None:
    """Regression: curved book with ~43° content_bbox must not beat a lone near-upright tile."""
    from app.services.deskew import _pick_fine_skew_from_candidates

    candidates = [
        (43.0, "content_bbox"),
        (-90.0, "full_page"),
        (-90.0, "tight_text"),
        (-48.5, "tile_0_0"),
        (0.0, "tile_0_1"),
        (-90.0, "tile_0_2"),
        (-90.0, "tile_1_0"),
        (0.0, "tile_1_1"),
        (-90.0, "tile_1_2"),
        (0.0, "tile_2_0"),
        (0.0, "tile_2_1"),
        (-90.0, "tile_2_2"),
        (-38.5, "probe_tile_0_0"),
        (-38.5, "probe_tile_0_1"),
        (-46.5, "probe_tile_0_2"),
        (-43.5, "probe_tile_1_0"),
        (-46.0, "probe_tile_1_1"),
        (-49.0, "probe_tile_1_2"),
        (-45.0, "probe_tile_2_0"),
        (-47.5, "probe_tile_2_1"),
        (-5.0, "probe_tile_2_2"),
    ]
    angle, source = _pick_fine_skew_from_candidates(
        candidates,
        default_source="content_bbox",
        cardinal_skew_hint=0.0,
        min_angle_deg=0.5,
        cardinal_branch="small_island_upright",
    )
    assert abs(angle) < 0.5, (angle, source)


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


def test_full_page_mixed_sign_tiles_skip_fine_skew() -> None:
    from app.services.deskew import _pick_fine_skew_from_candidates

    candidates = [
        (-90.0, "full_page"),
        (-1.5, "tile_0_0"),
        (0.0, "tile_0_1"),
        (0.0, "tile_1_0"),
        (0.0, "tile_1_1"),
        (0.0, "tile_2_0"),
        (1.5, "tile_2_1"),
        (-90.0, "tile_2_2"),
    ]
    angle, source = _pick_fine_skew_from_candidates(
        candidates,
        default_source="full_page",
        min_angle_deg=0.5,
    )
    assert abs(angle) < 0.5, (angle, source)


def test_diamond_zone_upright_hint_needs_two_tiles(monkeypatch: pytest.MonkeyPatch) -> None:
    from PIL import Image

    from app.services.deskew import _diamond_zone_upright_skew_hint

    monkeypatch.setattr(
        "app.services.deskew._skew_tile_candidates",
        lambda _img: [(-5.0, "tile_2_2")],
    )
    assert _diamond_zone_upright_skew_hint(Image.new("RGB", (100, 100), "white")) == 0.0


def test_pick_fine_skew_uses_cardinal_hint_over_diamond_zone() -> None:
    from app.services.deskew import _pick_fine_skew_from_candidates

    candidates = [
        (40.0, "content_bbox"),
        (-50.0, "full_page"),
        (40.0, "tile_2_2"),
    ]
    angle, source = _pick_fine_skew_from_candidates(
        candidates,
        default_source="content_bbox",
        cardinal_skew_hint=-5.0,
        min_angle_deg=0.5,
        trust_cardinal_skew_hint=True,
    )
    assert abs(angle + 5.0) < 0.1, (angle, source)
    assert source == "content_bbox"


def test_diamond_zone_near_horizontal_returns_without_sideways(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: diamond-zone conflict must return upright, not fall through to sideways."""
    from PIL import Image

    from app.services.deskew import _pick_cardinal_on_probe

    monkeypatch.setenv("DESKEW_DEBUG", "1")
    probe = Image.new("RGB", (284, 304), "white")
    monkeypatch.setattr("app.services.deskew.detect_page_angle", lambda _img: -49.0)
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
    monkeypatch.setattr("app.services.deskew.detect_page_angle", lambda _img: -49.0)
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


def test_detect_preview_tilt_upside_down_includes_cardinal_and_fine() -> None:
    from app.services.deskew import detect_preview_tilt

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
