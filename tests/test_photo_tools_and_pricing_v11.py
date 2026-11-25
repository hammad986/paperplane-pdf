from __future__ import annotations

import io
from pathlib import Path
from PIL import Image
import pytest
from fastapi.testclient import TestClient

import config
import converters
import server


def _make_sample_image(path: Path, width: int = 400, height: int = 400, color: tuple = (200, 50, 50)) -> Path:
    im = Image.new("RGB", (width, height), color)
    im.save(str(path), format="JPEG", quality=95)
    return path


def test_compress_photo_target_kb(tmp_path):
    src = _make_sample_image(tmp_path / "large.jpg", width=800, height=800)
    out = tmp_path / "out_compressed.jpg"
    res = converters.compress_photo(src, out, target_kb=50)
    assert res.exists()
    assert res.stat().st_size <= 65 * 1024  # within target range


def test_compress_photo_reduces_dimensions_when_quality_alone_misses_target(tmp_path):
    import random

    source = tmp_path / "high-detail-429kb.jpg"
    pixels = random.Random(20261117).randbytes(1200 * 900 * 3)
    Image.frombytes("RGB", (1200, 900), pixels).save(source, format="JPEG", quality=52, optimize=True)
    assert 400 * 1024 <= source.stat().st_size <= 450 * 1024

    output = converters.compress_photo(source, tmp_path / "target-50kb.jpg", target_kb=50)
    with Image.open(output) as image:
        assert image.format == "JPEG"
        assert image.size[0] < 1200 and image.size[1] < 900
    assert output.stat().st_size <= 50 * 1024


def test_compress_photo_quality(tmp_path):
    src = _make_sample_image(tmp_path / "orig.jpg", width=400, height=400)
    out = tmp_path / "out_q.jpg"
    res = converters.compress_photo(src, out, quality=30)
    assert res.exists()
    assert res.stat().st_size > 0


def test_resize_photo_dimensions(tmp_path):
    src = _make_sample_image(tmp_path / "orig_dim.jpg", width=600, height=400)
    out = tmp_path / "out_dim.jpg"
    res = converters.resize_photo(src, out, width=300, height=200)
    with Image.open(str(res)) as im:
        assert im.size == (300, 200)


def test_resize_photo_scale_percent(tmp_path):
    src = _make_sample_image(tmp_path / "orig_scale.jpg", width=400, height=400)
    out = tmp_path / "out_scale.jpg"
    res = converters.resize_photo(src, out, scale_percent=50)
    with Image.open(str(res)) as im:
        assert im.size == (200, 200)


@pytest.mark.parametrize("as_pdf", [False, True])
def test_exam_resizer_obeys_strict_decimal_max_byte_cap(tmp_path, as_pdf):
    import random

    source = tmp_path / "detailed-429kb.jpg"
    pixels = random.Random(20261117).randbytes(1200 * 900 * 3)
    Image.frombytes("RGB", (1200, 900), pixels).save(source, format="JPEG", quality=52, optimize=True)
    output = converters.resize_exam_image(source, tmp_path / ("strict-cap.pdf" if as_pdf else "strict-cap.jpg"),
                                          preset="ssc_photo", as_pdf=as_pdf)
    assert output.stat().st_size <= 50_000


def test_merge_photos_vertical_horizontal_grid(tmp_path):
    img1 = _make_sample_image(tmp_path / "img1.jpg", 100, 100, (255, 0, 0))
    img2 = _make_sample_image(tmp_path / "img2.jpg", 100, 100, (0, 255, 0))
    img3 = _make_sample_image(tmp_path / "img3.jpg", 100, 100, (0, 0, 255))
    img4 = _make_sample_image(tmp_path / "img4.jpg", 100, 100, (255, 255, 0))

    # Vertical
    v_out = converters.merge_photos([img1, img2], tmp_path / "v_merged.jpg", layout="vertical")
    with Image.open(str(v_out)) as im:
        assert im.size == (100, 200)

    # Horizontal
    h_out = converters.merge_photos([img1, img2], tmp_path / "h_merged.jpg", layout="horizontal")
    with Image.open(str(h_out)) as im:
        assert im.size == (200, 100)

    # Grid (4 images)
    g_out = converters.merge_photos([img1, img2, img3, img4], tmp_path / "g_merged.jpg", layout="grid")
    with Image.open(str(g_out)) as im:
        assert im.size == (200, 200)


def test_merge_photos_grid_uses_distinct_row_and_column_extents(tmp_path):
    sources = [
        _make_sample_image(tmp_path / "tall-left.jpg", 100, 200, (255, 0, 0)),
        _make_sample_image(tmp_path / "wide-right-top.jpg", 200, 100, (0, 255, 0)),
        _make_sample_image(tmp_path / "short-left-bottom.jpg", 80, 120, (0, 0, 255)),
        _make_sample_image(tmp_path / "wide-right-bottom.jpg", 200, 150, (255, 255, 0)),
    ]

    output = converters.merge_photos(sources, tmp_path / "uneven_grid.jpg", layout="grid")
    with Image.open(output) as merged:
        assert merged.size == (300, 350)
        assert merged.getpixel((50, 50))[0] > 200
        assert merged.getpixel((150, 50))[1] > 200
        assert merged.getpixel((50, 250))[2] > 200
        assert merged.getpixel((150, 250))[0] > 200


def test_photo_tools_server_routes_and_seo():
    client = TestClient(server.app)

    # Check SEO routes return 200
    for slug in ("compress-image-online", "resize-image-dimensions", "merge-photos-online"):
        resp = client.get(f"/{slug}")
        assert resp.status_code == 200, f"Route /{slug} failed"
        assert "Paperplane" in resp.text


def test_new_pricing_constants():
    assert config.EXAM_PASS_PRICE_INR == 19
    assert config.STUDENT_PRO_PRICE_INR == 49
    assert config.DEV_TIER_PRICE_INR == 299
    assert config.CYBER_CAFE_PRICE_INR == 299
