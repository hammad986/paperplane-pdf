import fitz

import converters


def test_already_grayscale_pdf_keeps_its_searchable_content(tmp_path):
    source = tmp_path / "already-gray.pdf"
    output = tmp_path / "preserved-gray.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Searchable black text stays in the PDF.", color=(0, 0, 0))
    doc.save(source)
    doc.close()

    report = converters.convert_pdf_to_grayscale(source, output)

    with fitz.open(source) as original, fitz.open(output) as converted:
        assert converted.page_count == original.page_count == 1
        assert converted[0].get_text().strip() == original[0].get_text().strip()
    assert report["already_grayscale"] is True
    assert output.read_bytes() == source.read_bytes()
    assert report["size_delta_bytes"] == 0


def test_colored_pdf_is_grayscale_and_reports_rasterization_size_delta(tmp_path):
    source = tmp_path / "colored.pdf"
    output = tmp_path / "converted-gray.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Color title", color=(1, 0, 0))
    page.insert_text((72, 110), "Black text", color=(0, 0, 0))
    doc.save(source)
    doc.close()

    report = converters.convert_pdf_to_grayscale(source, output)

    with fitz.open(output) as converted:
        assert converted.page_count == 1
        pix = converted[0].get_pixmap(colorspace=fitz.csRGB, dpi=72, alpha=False)
        pixels = pix.samples
        assert all(
            pixels[index] == pixels[index + 1] == pixels[index + 2]
            for index in range(0, len(pixels), pix.n)
        )
        # Color pages are intentionally rasterized; the UI warns that text may
        # need OCR before it can be searched or copied.
        assert converted[0].get_text().strip() == ""
    assert report["already_grayscale"] is False
    assert report["size_delta_bytes"] == output.stat().st_size - source.stat().st_size
