from __future__ import annotations

import fitz
import pytest

import server


def _make_marked_pdf(path, labels: list[str]) -> None:
    document = fitz.open()
    for label in labels:
        page = document.new_page(width=595, height=842)
        page.insert_text((72, 72), label, fontsize=16)
    document.save(path)
    document.close()


def test_tool_desk_annotation_adds_real_note_and_rejects_empty_request(tmp_path):
    source = tmp_path / "notes.pdf"
    output_dir = tmp_path / "annotated"
    output_dir.mkdir()
    _make_marked_pdf(source, ["Review section marker"])

    with pytest.raises(ValueError, match="comment text"):
        server.process("annotate", [source], {"annot_type": "note", "page": 1}, output_dir)

    output = server.process("annotate", [source], {
        "annot_type": "note",
        "page": 1,
        "content": "Requested review note",
    }, output_dir)
    with fitz.open(output) as result:
        page = result[0]
        annotations = list(page.annots() or [])
        assert result.page_count == 1
        assert page.get_text().strip() == "Review section marker"
        assert len(annotations) == 1
        assert annotations[0].info["content"] == "Requested review note"
        source_pixels = fitz.open(source)[0].get_pixmap().samples
        result_pixels = page.get_pixmap().samples
        assert result_pixels != source_pixels


def test_organize_tool_applies_explicit_order_and_rejects_empty_order(tmp_path):
    source = tmp_path / "pages.pdf"
    output_dir = tmp_path / "organized"
    output_dir.mkdir()
    _make_marked_pdf(source, ["Page 1 marker", "Page 2 marker", "Page 3 marker"])

    with pytest.raises(ValueError, match="page order"):
        server.process("organize", [source], {}, output_dir)

    output = server.process("organize", [source], {"pages": "3,1,2"}, output_dir)
    with fitz.open(output) as result:
        texts = [page.get_text().strip() for page in result]
    assert texts == ["Page 3 marker", "Page 1 marker", "Page 2 marker"]


def test_compare_diff_uses_original_names_without_temporary_prefixes(tmp_path):
    before = tmp_path / "before-input.pdf"
    after = tmp_path / "after-input.pdf"
    output_dir = tmp_path / "compared"
    output_dir.mkdir()
    _make_marked_pdf(before, ["Original text"])
    _make_marked_pdf(after, ["Revised text"])

    output = server.process("compare", [before, after], {
        "_original_filenames": ["before.pdf", "after.pdf"],
    }, output_dir)
    diff = output.read_text(encoding="utf-8")
    assert "--- before.pdf" in diff
    assert "+++ after.pdf" in diff
    assert "before-input.pdf" not in diff
    assert "after-input.pdf" not in diff
    assert "Original text" in diff and "Revised text" in diff
