from __future__ import annotations

import io
import json
import time
from pathlib import Path

import fitz
import pypdf
from fastapi.testclient import TestClient

import ai_engine
import converters
import persistence
import security_forms_engine
import server


ROOT = Path(__file__).resolve().parents[1]


def _make_sample_pdf(path: Path, text: str = "Paperplane Phase 1 Test Document", title: str = "", author: str = "") -> Path:
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), text)
        if title or author:
            doc.set_metadata({"title": title, "author": author, "subject": "Audit Subject"})
        doc.save(path)
    return path


def _wait_for_job(client: TestClient, status_url: str) -> dict:
    job = {}
    for _ in range(120):
        job = client.get(status_url).json()
        if job.get("status") in {"completed", "failed"}:
            return job
        time.sleep(0.02)
    return job


def test_id412_terms_and_privacy_routes_and_auth_links():
    client = TestClient(server.app)
    for route in ("/terms", "/privacy"):
        resp = client.get(route)
        assert resp.status_code == 200
        assert "<!doctype html>" in resp.text.lower()

    index_html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert 'id="link-auth-terms"' in index_html
    assert 'href="/terms"' in index_html
    assert 'id="link-auth-privacy"' in index_html
    assert 'href="/privacy"' in index_html


def test_id414_compress_100kb_and_200kb_routes_serve_html_and_tool_mapping():
    client = TestClient(server.app)
    for route in ("/compress-pdf-to-100kb", "/compress-pdf-to-200kb"):
        resp = client.get(route)
        assert resp.status_code == 200
        assert "<!doctype html>" in resp.text.lower()

    app_js = (ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    assert "pathSlug === 'compress-pdf-to-100kb' || pathSlug === 'compress-pdf-to-200kb'" in app_js


def test_id415_id333_metadata_cleanup_merge_preservation_and_clearing(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "DATABASE", tmp_path / "phase1-meta.sqlite")
    monkeypatch.setattr(server, "JOBS", tmp_path / "jobs")
    persistence.init_db()

    # 1. pdf_to_markdown & pdf_to_word skip 'untitled' / internal names
    source = _make_sample_pdf(tmp_path / "source.pdf", text="Quarterly financial schedule", title="untitled")
    md_out = converters.pdf_to_markdown(source, tmp_path / "out.md")
    md_text = md_out.read_text(encoding="utf-8")
    assert "untitled" not in md_text.lower()
    assert "Quarterly financial schedule" in md_text

    docx_out = converters.pdf_to_word(source, tmp_path / "out.docx")
    assert docx_out.exists()
    from docx import Document
    docx_doc = Document(docx_out)
    assert docx_doc.core_properties.title != "untitled"

    # 2. Merge preserves first document metadata
    p1 = _make_sample_pdf(tmp_path / "p1.pdf", text="First document page", title="Primary Board Pack", author="Ayesha Khan")
    p2 = _make_sample_pdf(tmp_path / "p2.pdf", text="Second document page", title="Appendix", author="Other")

    client = TestClient(server.app)
    merge_resp = client.post(
        "/api/jobs",
        data={"operation": "merge", "options": "{}"},
        files=[
            ("files", ("p1.pdf", p1.read_bytes(), "application/pdf")),
            ("files", ("p2.pdf", p2.read_bytes(), "application/pdf")),
        ],
    )
    assert merge_resp.status_code == 202
    merge_payload = merge_resp.json()
    job = _wait_for_job(client, merge_payload["status_url"])
    assert job["status"] == "completed", job
    merged_bytes = client.get(merge_payload["download_url"]).content
    reader = pypdf.PdfReader(io.BytesIO(merged_bytes))
    assert reader.metadata.get("/Title") == "Primary Board Pack"
    assert reader.metadata.get("/Author") == "Ayesha Khan"

    # 3. Metadata clearing deletes empty keys instead of leaving stale values
    clear_resp = client.post(
        "/api/jobs",
        data={"operation": "metadata", "options": json.dumps({"title": "", "author": "", "subject": ""})},
        files={"files": ("primary.pdf", p1.read_bytes(), "application/pdf")},
    )
    assert clear_resp.status_code == 202
    clear_payload = clear_resp.json()
    clear_job = _wait_for_job(client, clear_payload["status_url"])
    assert clear_job["status"] == "completed", clear_job
    cleared_bytes = client.get(clear_payload["download_url"]).content
    with fitz.open(stream=cleared_bytes, filetype="pdf") as cleared_doc:
        meta = cleared_doc.metadata or {}
        assert not (meta.get("title") or "").strip()
        assert not (meta.get("author") or "").strip()
        assert not (meta.get("subject") or "").strip()


def test_id150_id117_owner_encrypted_empty_user_password_pdfs_work(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "DATABASE", tmp_path / "phase1-enc.sqlite")
    monkeypatch.setattr(server, "JOBS", tmp_path / "jobs")
    persistence.init_db()

    enc_path = tmp_path / "owner_locked.pdf"
    with fitz.open() as doc:
        p = doc.new_page()
        p.insert_text((72, 72), "Owner-only restricted PDF content.")
        doc.save(
            enc_path,
            encryption=fitz.PDF_ENCRYPT_AES_256,
            owner_pw="owner-secret-pass",
            user_pw="",
        )

    gray_out = tmp_path / "gray.pdf"
    gray_res = converters.convert_pdf_to_grayscale(enc_path, gray_out)
    assert gray_out.exists()
    assert gray_res["page_count"] == 1

    comp_out = tmp_path / "compressed.pdf"
    converters.compress_pdf(enc_path, comp_out, quality="balanced")
    assert comp_out.exists()

    sig_info = security_forms_engine.verify_pdf_signatures(enc_path)
    assert sig_info.get("locked") is not True
    assert "password-protected" not in str(sig_info.get("error", "")).lower()

    client = TestClient(server.app)
    resp_all = client.post(
        "/api/jobs",
        data={"operation": "split", "options": json.dumps({"split_mode": "all_pages"})},
        files={"files": ("owner_locked.pdf", enc_path.read_bytes(), "application/pdf")},
    )
    assert resp_all.status_code == 202
    job_all = _wait_for_job(client, resp_all.json()["status_url"])
    assert job_all["status"] == "completed", job_all

    resp_sel = client.post(
        "/api/jobs",
        data={"operation": "split", "options": json.dumps({"pages": "1"})},
        files={"files": ("owner_locked.pdf", enc_path.read_bytes(), "application/pdf")},
    )
    assert resp_sel.status_code == 202
    job_sel = _wait_for_job(client, resp_sel.json()["status_url"])
    assert job_sel["status"] == "completed", job_sel


def test_id293_flatten_forms_renders_widgets_without_prebaked_ap(tmp_path):
    source = tmp_path / "widget_no_ap.pdf"
    output = tmp_path / "flattened.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        widget = fitz.Widget()
        widget.rect = fitz.Rect(80, 100, 260, 130)
        widget.field_name = "signer_name"
        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        widget.field_value = "Approved By Owner"
        widget.text_color = (0, 0, 0)
        widget.fill_color = (0.95, 0.95, 0.95)
        widget.border_color = (0, 0, 0)
        page.add_widget(widget)
        for w in page.widgets():
            doc.xref_set_key(w.xref, "AP", "null")
        doc.save(source)

    security_forms_engine.flatten_pdf_forms(source, output)
    with fitz.open(output) as out_doc:
        assert list(out_doc[0].widgets() or []) == []
        assert list(out_doc[0].annots() or []) == []
        pix = out_doc[0].get_pixmap(clip=fitz.Rect(80, 100, 260, 130))
        assert any(channel < 235 for channel in pix.samples)


def test_id14_annotate_and_redact_dehyphenated_wrapped_terms(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "DATABASE", tmp_path / "phase1-dehyph.sqlite")
    monkeypatch.setattr(server, "JOBS", tmp_path / "jobs")
    persistence.init_db()

    source = tmp_path / "wrapped.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), "Strict confi-\ndentiality clause applies.")
        doc.save(source)

    hl_out = tmp_path / "highlighted.pdf"
    converters.annotate_pdf(
        source,
        hl_out,
        annotations=[{"type": "highlight", "page": 1, "text": "confidentiality", "content": "Wrapped match"}],
    )
    with fitz.open(hl_out) as hl_doc:
        annots = list(hl_doc[0].annots() or [])
        assert len(annots) >= 1

    client = TestClient(server.app)
    redact_resp = client.post(
        "/api/jobs",
        data={"operation": "redact", "options": json.dumps({"terms": "confidentiality"})},
        files={"files": ("wrapped.pdf", source.read_bytes(), "application/pdf")},
    )
    assert redact_resp.status_code == 202
    redact_payload = redact_resp.json()
    redact_job = _wait_for_job(client, redact_payload["status_url"])
    assert redact_job["status"] == "completed", redact_job
    redacted_bytes = client.get(redact_payload["download_url"]).content
    with fitz.open(stream=redacted_bytes, filetype="pdf") as red_doc:
        text = red_doc[0].get_text("text")
        assert "dentiality" not in text.lower()


def test_id12_id9_id338_false_premise_and_smart_metadata_attribution(tmp_path):
    pdf = tmp_path / "attribution_resume.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text(
            (72, 72),
            "Copyright (c) 1999 Acme Archive Corp.\n"
            "Digitized by FooOCR Engine\n"
            "Priya Sharma\n"
            "Senior Financial Analyst\n"
            "Date: 15 March 2025\n"
            "Quarterly revenue forecast and capital allocation review.\n",
        )
        doc.save(pdf)

    # Unattributed author false-premise returns honest can't-verify guidance when PDF is provided
    fp_msg = ai_engine.correct_false_premise(pdf, "Was this written by Albert Einstein?")
    assert fp_msg and "can't verify" in fp_msg.lower()
    # Grounded capitalized heading words should not trigger false-premise warning
    assert ai_engine.correct_false_premise(pdf, "Explain The Senior Financial Analyst review?") is None

    extracted_resume = ai_engine.extract_metadata_entities(pdf, doc_type="resume")
    resume_dump = json.dumps(extracted_resume).lower()
    assert "acme archive" not in resume_dump
    assert "fooocr" not in resume_dump
    assert "priya sharma" in extracted_resume["resume_data"]["candidate_name"].lower()

    extracted_general = ai_engine.extract_metadata_entities(pdf, doc_type="general")
    general_dump = json.dumps(extracted_general).lower()
    assert "acme archive" not in general_dump
    assert "fooocr" not in general_dump
    doc_date = str(extracted_general["general_data"].get("document_date", ""))
    assert "1999" not in doc_date
    assert "2025" in doc_date


def test_id352_id359_auth_me_billing_status_and_ai_stream_headers(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "DATABASE", tmp_path / "phase1-quota.sqlite")
    monkeypatch.setattr(server, "JOBS", tmp_path / "jobs")
    persistence.init_db()
    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setenv("BLUESMINDS_API_KEY", "test-key")

    client = TestClient(server.app)
    me_resp = client.get("/api/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json() == {"authenticated": False}

    billing_resp = client.get("/api/billing/status")
    assert billing_resp.status_code == 200
    billing = billing_resp.json()
    assert "plan_limits" in billing

    sample = _make_sample_pdf(tmp_path / "ai.pdf", text="Annual operating plan targets 18% growth.")
    monkeypatch.setattr(
        ai_engine,
        "stream_bluesminds",
        lambda *args, **kwargs: iter(["The plan targets 18% growth [Page 1]."]),
    )
    stream_ok = client.post(
        "/api/ai/chat/stream",
        data={"question": "What growth is targeted?"},
        files={"file": ("ai.pdf", sample.read_bytes(), "application/pdf")},
    )
    assert stream_ok.status_code == 200
    assert "X-Paperplane-Operations-Today" in stream_ok.headers

    monkeypatch.setattr(server, "consume_rate_limit", lambda *args, **kwargs: False)
    limited_chat = client.post(
        "/api/ai/chat",
        data={"question": "What growth is targeted?"},
        files={"file": ("ai.pdf", sample.read_bytes(), "application/pdf")},
    )
    assert limited_chat.status_code == 429

    limited_stream = client.post(
        "/api/ai/chat/stream",
        data={"question": "What growth is targeted?"},
        files={"file": ("ai.pdf", sample.read_bytes(), "application/pdf")},
    )
    assert limited_stream.status_code == 429


def test_id13_studio_page_delete_returns_clean_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "DATABASE", tmp_path / "phase1-del.sqlite")
    persistence.init_db()

    source = tmp_path / "three_pages.pdf"
    with fitz.open() as doc:
        for i in range(1, 4):
            p = doc.new_page()
            p.insert_text((72, 72), f"Unique Marker Page {i}")
        doc.save(source)

    client = TestClient(server.app)
    resp = client.post(
        "/api/studio/page/delete",
        data={"pages": json.dumps([2])},
        files={"file": ("three_pages.pdf", source.read_bytes(), "application/pdf")},
    )
    assert resp.status_code == 200
    with fitz.open(stream=resp.content, filetype="pdf") as out_doc:
        assert out_doc.page_count == 2
        assert "Unique Marker Page 1" in out_doc[0].get_text("text")
        assert "Unique Marker Page 3" in out_doc[1].get_text("text")
