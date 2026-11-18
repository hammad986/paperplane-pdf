import fitz
import io
import pytest
from PIL import Image

import ai_engine
import converters


def test_offline_brief_retains_last_page_when_provider_fails(tmp_path, monkeypatch):
    source = tmp_path / "long.pdf"
    with fitz.open() as doc:
        for number in range(1, 70):
            doc.new_page().insert_text((72, 72), f"Distinct finding number {number} in this document.")
        doc.save(source)

    def unavailable(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(ai_engine, "call_llm", unavailable)
    brief = ai_engine.summarize_pdf(source)
    assert "Distinct finding number 1 " in brief
    assert "Distinct finding number 69 " in brief
    assert "[Page 69]" in brief


@pytest.mark.parametrize("preset", ["100kb", "balanced"])
def test_compression_keeps_visible_image_and_searchable_text(tmp_path, preset):
    source, output = tmp_path / "source.pdf", tmp_path / "output.pdf"
    image = Image.new("RGB", (1200, 1200), (230, 35, 25))
    encoded = io.BytesIO()
    image.save(encoded, format="PNG")
    with fitz.open() as doc:
        page = doc.new_page(width=400, height=400)
        page.insert_image(fitz.Rect(50, 50, 350, 300), stream=encoded.getvalue())
        page.insert_text((50, 350), "Readable original text")
        doc.save(source)
    converters.compress_pdf(source, output, preset=preset)
    with fitz.open(output) as doc:
        assert "Readable original text" in doc[0].get_text()
        pix = doc[0].get_pixmap()
        red, green, blue = pix.pixel(200, 150)[:3]
        assert red > 160 and red > green * 2 and red > blue * 2


def test_word_preserves_mixed_page_images_and_tables(tmp_path):
    from docx import Document
    source, output = tmp_path / 'mixed.pdf', tmp_path / 'mixed.docx'
    image = io.BytesIO()
    Image.new('RGB', (120, 100), 'red').save(image, format='PNG')
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 40), 'Editable heading')
        page.insert_image(fitz.Rect(40, 80, 160, 180), stream=image.getvalue())
        for x in (40, 180, 320):
            page.draw_line((x, 220), (x, 300))
        for y in (220, 260, 300):
            page.draw_line((40, y), (320, y))
        for x, y, text in ((50, 245, 'Item'), (190, 245, 'Amount'), (50, 285, 'Printer'), (190, 285, '42')):
            page.insert_text((x, y), text)
        doc.save(source)
    converters.pdf_to_word(source, output)
    document = Document(output)
    assert any('Editable heading' in p.text for p in document.paragraphs)
    assert len(document.inline_shapes) == 1
    assert len(document.tables) == 1
    assert document.tables[0].cell(1, 0).text == 'Printer'
