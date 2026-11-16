import fitz

import converters
import server
import security_forms_engine


def _pdf(path):
    document = fitz.open()
    document.new_page()
    document.save(path)
    document.close()
    return path


def test_added_edit_and_page_number_text_is_extractable_and_unicode_mapped(tmp_path):
    source = _pdf(tmp_path / "source.pdf")
    edited = tmp_path / "edited.pdf"
    numbered = tmp_path / "numbered.pdf"

    converters.apply_editor_annotations(source, edited, [{
        "type": "text", "page": 1, "docX": 72, "docY": 80,
        "docW": 200, "docH": 30, "text": "Added searchable text",
    }])
    page_overlay = server.overlay(595, 842, "Page 1 of 1", "page_numbers", {})
    with fitz.open(edited) as document:
        assert "Added searchable text" in document[0].get_text().replace("\u00a0", " ")
        fonts = document.get_page_fonts(0, full=True)
        assert any(document.xref_get_key(font[0], "ToUnicode")[0] != "null" for font in fonts)

    with fitz.open(source) as document:
        page = document[0]
        page.show_pdf_page(page.rect, fitz.open(stream=page_overlay, filetype="pdf"), 0)
        document.save(numbered)
    with fitz.open(numbered) as document:
        assert "Page 1 of 1" in document[0].get_text()
        assert any(document.xref_get_key(font[0], "ToUnicode")[0] != "null"
                   for font in document.get_page_fonts(0, full=True))


def test_page_number_default_includes_total_on_six_page_pdf(tmp_path):
    source = tmp_path / "six-pages.pdf"
    document = fitz.open()
    for _ in range(6):
        document.new_page()
    document.save(source)
    document.close()

    output_path = server.process("page_numbers", [source], {"format": "page_of_total"}, tmp_path)

    with fitz.open(output_path) as output:
        assert output.page_count == 6
        assert "Page 1 of 6" in output[0].get_text().replace("\u00a0", " ")


def test_page_number_literal_ui_template_substitutes_both_tokens(tmp_path):
    source = tmp_path / "six-page-ui-template.pdf"
    with fitz.open() as document:
        for _ in range(6):
            document.new_page()
        document.save(source)

    output_path = server.process(
        "page_numbers", [source], {"format": "Page {n} of {total}"}, tmp_path
    )

    with fitz.open(output_path) as output:
        assert "Page 1 of 6" in output[0].get_text().replace("\u00a0", " ")
        assert "Page 6 of 6" in output[5].get_text().replace("\u00a0", " ")


def test_sign_pdf_typed_name_is_visible_and_extractable(tmp_path):
    source = _pdf(tmp_path / "unsigned.pdf")
    output = tmp_path / "signed.pdf"

    security_forms_engine.add_visual_signature(source, output, "Test", signer_name="Test")

    with fitz.open(output) as signed:
        assert "Test" in signed[0].get_text()
        assert signed[0].get_drawings()


def test_compare_diff_headers_use_original_names_not_internal_staging_names(tmp_path):
    left = _pdf(tmp_path / "a1b2c3_ten-pages.pdf")
    right = tmp_path / "d4e5f6_ten-pages-revised.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Different version")
    document.save(right)
    document.close()

    output = server.process("compare", [left, right], {
        "_original_filenames": ["ten-pages.pdf", "ten-pages-revised.pdf"]
    }, tmp_path)

    diff = output.read_text(encoding="utf-8")
    assert "--- ten-pages.pdf" in diff
    assert "+++ ten-pages-revised.pdf" in diff
    assert "a1b2c3" not in diff and "d4e5f6" not in diff
