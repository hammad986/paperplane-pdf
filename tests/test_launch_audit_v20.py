from __future__ import annotations

import time

from fastapi.testclient import TestClient

import converters
import fitz
import server
import security_forms_engine


def test_chunked_upload_reassembles_and_content_checks_queued_job(monkeypatch):
    monkeypatch.setattr(server, "UPLOAD_CHUNK_BYTES", 64)
    monkeypatch.setattr(server, "check_operation_quota", lambda *args, **kwargs: (True, 0, "pro"))
    client = TestClient(server.app)
    files = []
    for index in range(2):
        document = fitz.open()
        page = document.new_page()
        page.insert_text((72, 72), f"Chunked source page {index + 1}")
        data = document.tobytes()
        document.close()
        files.append((f"source-{index + 1}.pdf", data))

    started = client.post("/api/uploads/chunked", json={
        "operation": "merge", "files": [{"name": name, "size": len(data)} for name, data in files]
    })
    assert started.status_code == 201, started.text
    upload_id = started.json()["upload_id"]
    assert client.post(f"/api/uploads/chunked/{upload_id}/commit", json={"operation": "merge", "options": {}}).status_code == 409

    replay_part = None
    for file_index, (name, data) in enumerate(files):
        count = started.json()["chunk_counts"][file_index]
        for chunk_index in range(count):
            chunk = data[chunk_index * 64:(chunk_index + 1) * 64]
            uploaded = client.put(f"/api/uploads/chunked/{upload_id}/{file_index}/{chunk_index}", content=chunk)
            assert uploaded.status_code == 204, uploaded.text
            if replay_part is None:
                replay_part = (file_index, chunk_index, chunk)
    assert replay_part is not None
    file_index, chunk_index, chunk = replay_part
    assert client.put(f"/api/uploads/chunked/{upload_id}/{file_index}/{chunk_index}", content=chunk).status_code == 409

    committed = client.post(f"/api/uploads/chunked/{upload_id}/commit", json={"operation": "merge", "options": {}})
    assert committed.status_code == 202, committed.text
    job = committed.json()
    for _ in range(100):
        status = client.get(job["status_url"]).json()
        if status["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)
    assert status["status"] == "completed", status
    downloaded = client.get(job["download_url"])
    assert downloaded.status_code == 200
    with fitz.open(stream=downloaded.content, filetype="pdf") as output:
        assert output.page_count == 2
        assert "Chunked source page 1" in output[0].get_text()
        assert "Chunked source page 2" in output[1].get_text()


def test_chunked_upload_can_be_discarded_and_expired_sessions_are_swept(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "UPLOAD_CHUNK_BYTES", 32)
    monkeypatch.setattr(server, "CHUNKED_UPLOADS_DIR", tmp_path)
    document = fitz.open()
    document.new_page().insert_text((72, 72), "discard this upload")
    data = document.tobytes()
    document.close()
    client = TestClient(server.app)
    created = client.post("/api/uploads/chunked", json={
        "operation": "compress", "files": [{"name": "large.pdf", "size": len(data)}]
    })
    assert created.status_code == 201
    upload_id = created.json()["upload_id"]
    uploaded = client.put(f"/api/uploads/chunked/{upload_id}/0/0", content=data[:32])
    assert uploaded.status_code == 204
    discarded = client.delete(f"/api/uploads/chunked/{upload_id}")
    assert discarded.status_code == 200 and discarded.json() == {"deleted": True}
    assert not (tmp_path / upload_id).exists()
    assert client.post(f"/api/uploads/chunked/{upload_id}/commit", json={"operation": "compress", "options": {}}).status_code == 404

    expired_id = "a" * 32
    expired_dir = tmp_path / expired_id
    expired_dir.mkdir()
    (expired_dir / "manifest.json").write_text('{"created_at": 1, "files": []}', encoding="utf-8")
    server._cleanup_expired_chunked_uploads(now=server.UPLOAD_SESSION_TTL_SECONDS + 2)
    assert not expired_dir.exists()


def test_cloud_import_exposes_safe_upstream_status_without_echoing_signed_url(monkeypatch):
    def fail_fetch(url, **kwargs):
        raise converters.RemoteFetchHTTPError(404, "www.w3.org", "text/html; charset=utf-8")

    monkeypatch.setattr(server.converters, "safe_fetch_url", fail_fetch)
    response = TestClient(server.app).post(
        "/api/cloud/sync",
        data={"file_url": "https://www.w3.org/WAI/ER/tests/xhtml/testsuite/resources/pdf/dummy.pdf?secret=redacted"},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "HTTP 404" in detail
    assert "secret=redacted" not in detail


def test_google_drive_non_pdf_error_identifies_the_returned_content_type(monkeypatch):
    monkeypatch.setattr(
        server.converters,
        "safe_fetch_url",
        lambda *args, **kwargs: (b"\x89PNG\r\n\x1a\nthumbnail", "image/png"),
    )
    response = TestClient(server.app).post(
        "/api/cloud/sync",
        data={"file_url": "https://drive.google.com/file/d/public-file/view"},
    )

    assert response.status_code == 400
    assert "image/png" in response.json()["detail"]
    assert "not a PDF" in response.json()["detail"]


def test_split_ranges_return_the_requested_page_content_and_count(tmp_path):
    source = tmp_path / "numbered.pdf"
    doc = fitz.open()
    for page_number in range(1, 5):
        page = doc.new_page()
        page.insert_text((72, 72), f"Distinct page content {page_number}")
    doc.save(source)
    doc.close()

    outputs = converters.split_pdf_document(source, tmp_path / "split", "ranges", "1-2, 1")
    first = fitz.open(outputs[0])
    second = fitz.open(outputs[1])
    try:
        assert len(first) == 2
        assert "Distinct page content 1" in first[0].get_text()
        assert "Distinct page content 2" in first[1].get_text()
        assert len(second) == 1
        assert "Distinct page content 1" in second[0].get_text()
    finally:
        first.close()
        second.close()


def test_flatten_bakes_highlight_annotation_and_removes_annotation_record(tmp_path):
    source = tmp_path / "annotated.pdf"
    output = tmp_path / "flattened.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 90), "Highlighted content must remain visible")
    highlight = page.add_highlight_annot(fitz.Rect(70, 75, 265, 95))
    highlight.set_info(content="Review note")
    doc.save(source)
    doc.close()

    security_forms_engine.flatten_pdf_forms(source, output)
    result = fitz.open(output)
    try:
        assert list(result[0].annots() or []) == []
        assert "Highlighted content must remain visible" in result[0].get_text()
    finally:
        result.close()


def test_pdf_to_word_keeps_text_editable_without_page_rasterization(tmp_path):
    source = tmp_path / "text.pdf"
    output = tmp_path / "text.docx"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Editable contract clause 42 remains actual text")
    doc.save(source)
    doc.close()

    converters.pdf_to_word(source, output)
    from docx import Document
    converted = Document(output)
    assert any("Editable contract clause 42" in paragraph.text for paragraph in converted.paragraphs)
    assert not converted.inline_shapes


def test_highlight_annotation_comment_is_saved_in_pdf_contents(tmp_path):
    source = tmp_path / "source.pdf"
    output = tmp_path / "annotated.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "comment target text")
    doc.save(source)
    doc.close()

    converters.annotate_pdf(source, output, annotations=[{
        "type": "highlight", "page": 1, "text": "comment target", "content": "Owner review note"
    }])
    result = fitz.open(output)
    try:
        annotation = next(result[0].annots())
        assert annotation.info["content"] == "Owner review note"
    finally:
        result.close()


def test_sparse_pdf_about_question_uses_page_samples_or_low_text_guidance(tmp_path, monkeypatch):
    source = tmp_path / "sparse-24.pdf"
    doc = fitz.open()
    for page_number in range(1, 25):
        page = doc.new_page()
        page.insert_text((72, 72), f"Topic {page_number}")
    doc.save(source)
    doc.close()
    monkeypatch.setattr(server.ai_engine, "AI_KILL_SWITCH", True)

    answer = server.ai_engine.chat_with_pdf(source, "What is this document about?")
    assert "No relevant information found" not in answer["answer"]
    assert answer["answer"]


def test_pdf_to_excel_splits_table_like_columns_by_word_positions(tmp_path):
    source = tmp_path / "columns.pdf"
    output = tmp_path / "columns.xlsx"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Item")
    page.insert_text((240, 72), "Amount")
    page.insert_text((72, 100), "Printer")
    page.insert_text((240, 100), "$42.00")
    doc.save(source)
    doc.close()

    converters.pdf_to_excel(source, output)
    import openpyxl
    sheet = openpyxl.load_workbook(output, data_only=True).active
    assert sheet.cell(1, 1).value == "Item"
    assert sheet.cell(1, 2).value == "Amount"
    assert sheet.cell(2, 1).value == "Printer"
    assert sheet.cell(2, 2).value == "$42.00"


def test_pdfa_icc_resolver_accepts_valid_configured_profile_and_rejects_invalid(tmp_path, monkeypatch):
    profile = tmp_path / "sRGB.icc"
    header = bytearray(128)
    header[36:40] = b"acsp"
    profile.write_bytes(header)
    monkeypatch.setenv("PAPERPLANE_SRGB_ICC", str(profile))
    assert converters._find_srgb_icc_profile() == profile.resolve()

    monkeypatch.setenv("PAPERPLANE_SRGB_ICC", str(tmp_path / "missing.icc"))
    assert converters._find_srgb_icc_profile() is None


def test_translation_keeps_failed_batch_source_and_translates_other_batches(tmp_path, monkeypatch):
    source = tmp_path / "two-blocks.pdf"
    output = tmp_path / "partial-translation.pdf"
    doc = fitz.open()
    for y, text in [(90, "First source block"), (220, "Second source block")]:
        page = doc.new_page()
        page.insert_text((72, y), text)
    doc.save(source)
    doc.close()
    monkeypatch.setattr(server.ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setattr(server.ai_engine, "BLUESMINDS_API_KEY", "controlled-test-key")
    monkeypatch.setattr(server.ai_engine, "TRANSLATION_BATCH_SIZE", 1)
    monkeypatch.setattr(server.ai_engine, "TRANSLATION_MAX_PARALLEL_BATCHES", 1)

    def translate_batch(blocks, language, deadline=None):
        block_id, _ = blocks[0]
        if block_id == 0:
            raise RuntimeError("controlled upstream HTTP 429")
        return {block_id: "Bloque traducido correctamente"}

    monkeypatch.setattr(server.ai_engine, "_translate_text_batch", translate_batch)
    report = {}
    server.ai_engine.translate_pdf_layout(source, output, target_lang="es", report=report)

    assert output.is_file()
    assert report["failed_batches"]
    assert report["blocks_preserved"] >= 1
    with fitz.open(output) as translated:
        assert "First source block" in translated[0].get_text()
        assert translated[1].get_images()
        assert " ".join(translated[1].get_text().split()) == "Bloque traducido correctamente"
