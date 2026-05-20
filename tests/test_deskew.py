from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw

from app.services.deskew import (
    apply_exif_orientation,
    detect_deskew_correction,
    deskew_image,
    exif_orientation_ccw,
)


def _text_image() -> Image.Image:
    img = Image.new("RGB", (400, 200), "white")
    draw = ImageDraw.Draw(img)
    for index, char in enumerate("HELLO WORLD TEST"):
        draw.text((10 + index * 22, 80), char, fill="black")
    return img


def test_detect_deskew_correction_reports_90_degree_rotation() -> None:
    rotated = _text_image().transpose(Image.Transpose.ROTATE_90)
    correction = detect_deskew_correction(rotated)
    assert correction in {90.0, 270.0, -90.0}


def test_detect_page_angle_near_80_not_snapped_to_opposite_90() -> None:
    from app.services.deskew import detect_page_angle

    skewed = _text_image().rotate(80, expand=True, fillcolor="white")
    angle = detect_page_angle(skewed)
    assert -82.0 <= angle <= -78.0, angle

    _, net = deskew_image(skewed)
    assert -82.0 <= net <= -78.0, net


def test_deskew_image_does_not_flip_after_large_skew_correction() -> None:
    skewed = _text_image().rotate(82, expand=True, fillcolor="white")
    _, net = deskew_image(skewed)
    assert -84.0 <= net <= -80.0, net


def test_detect_deskew_correction_reports_upside_down_page() -> None:
    upside_down = _text_image().transpose(Image.Transpose.ROTATE_180)
    correction = detect_deskew_correction(upside_down)
    assert correction == 180.0


def test_deskew_image_applies_upside_down_correction() -> None:
    upside_down = _text_image().transpose(Image.Transpose.ROTATE_180)
    _, net = deskew_image(upside_down)
    assert net == 180.0


def test_exif_orientation_tag_maps_to_ccw_degrees() -> None:
    img = _text_image()
    exif = img.getexif()
    exif[274] = 6  # orientation: rotate 270 CCW to display
    assert exif_orientation_ccw(img) == 270.0
    oriented, ccw = apply_exif_orientation(img)
    assert ccw == 270.0
    assert oriented.size == (200, 400)


def test_exif_orientation_applied_via_bytes_roundtrip() -> None:
    source = _text_image()
    exif = source.getexif()
    exif[274] = 8
    buf = BytesIO()
    source.save(buf, format="JPEG", exif=exif)
    with Image.open(BytesIO(buf.getvalue())) as loaded:
        oriented, ccw = apply_exif_orientation(loaded)
    assert ccw == 90.0
