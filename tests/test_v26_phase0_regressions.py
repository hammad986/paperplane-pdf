from __future__ import annotations

import io
import json
import time
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

import ai_engine
import persistence
import server


ROOT = Path(__file__).resolve().parents[1]


def _make_pdf_bytes(page_count: int = 2, line_prefix: str = "Paperplane audit line") -> bytes:
    with fitz.open() as doc:
        for index in range(1, page_count + 1):
            page = doc.new_page()
            page.insert_text((72, 72), f"{line_prefix} on page {index}. INR 900,000 budget approved.")
        return doc.tobytes()


def test_id314_executive_brief_pdf_export_preserves_unicode_and_inr():
    client = TestClient(server.app)
    summary_md = (
        "### Executive Summary\n\n"
        "- Budget capped at ₹900,000 / INR 900,000 for ﬁnal phase [Page 1].\n"
        "- Multilingual check: भारत सरकार [Page 2].\n"
    )
    response = client.post(
        "/api/ai/summarize/pdf",
        json={"summary": summary_md, "filename": "audit_executive_brief.pdf", "title": "Audit Brief"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content.startswith(b"%PDF-")

    with fitz.open(stream=response.content, filetype="pdf") as exported:
        assert exported.page_count >= 1
        extracted = "\n".join(page.get_text("text") for page in exported)
        assert "INR 900,000" in extracted
        assert "Audit Brief" in extracted


def test_id314_frontend_brief_pdf_does_not_fall_back_to_txt():
    app_js = (ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    download_section = app_js.split("async function downloadSummaryPdf", 1)[1].split("function showAiChatDeskResult", 1)[0]
    assert "/api/ai/summarize/pdf" in download_section
    assert "sanitizePdfWinAnsi" in download_section
    assert "The summary was downloaded as a text file instead" not in download_section


def test_id1_id2_id410_async_summarize_and_translate_jobs_emit_metadata_and_clean_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "DATABASE", tmp_path / "phase0-jobs.sqlite")
    monkeypatch.setattr(server, "JOBS", tmp_path / "jobs")
    persistence.init_db()
    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setenv("BLUESMINDS_API_KEY", "test-key")

    pdf_69 = _make_pdf_bytes(69, "Quarterly operational findings")

    def fake_chunk_llm(system, prompt, timeout_seconds=None, max_attempts=2, **kwargs):
        if prompt.startswith("Synthesize these page-grounded"):
            return (
                "### Executive Summary\n\n"
                "- Approved INR 900,000 cap across all 69 pages [Page 1] [Page 69]."
            )
        return "Operational milestone verified with INR 900,000 cap [Page 1] [Page 69]."

    monkeypatch.setattr(ai_engine, "call_llm", fake_chunk_llm)

    client = TestClient(server.app)
    submit_sum = client.post(
        "/api/jobs",
        data={"operation": "summarize", "options": "{}"},
        files={"files": ("notes.pdf", pdf_69, "application/pdf")},
    )
    assert submit_sum.status_code == 202
    sum_status_url = submit_sum.json()["status_url"]
    sum_job = {}
    for _ in range(120):
        sum_job = client.get(sum_status_url).json()
        if sum_job["status"] in {"completed", "failed"}:
            break
        time.sleep(0.02)
    assert sum_job["status"] == "completed"
    assert sum_job["summary_mode"] == "provider_synthesized"
    assert "Executive Summary" in sum_job["summary"]
    assert 1 in sum_job["citations"]
    assert 69 in sum_job["citations"]

    # Translate job for Hindi (Devanagari) and Spanish
    pdf_2 = _make_pdf_bytes(2, "Invoice total")
    monkeypatch.setattr(
        ai_engine,
        "_translate_text_batch",
        lambda batch, target_lang, **_kwargs: {
            block_id: (
                "भारत सरकार अनुमोदित"
                if target_lang == "hi"
                else "Factura aprobada por Paperplane"
            )
            for block_id, _ in batch
        },
    )
    for lang, marker in [("es", "Factura aprobada"), ("hi", "भारत सरकार")]:
        sub_tr = client.post(
            "/api/jobs",
            data={"operation": "translate", "options": json.dumps({"target_language": lang})},
            files={"files": ("sample.pdf", pdf_2, "application/pdf")},
        )
        assert sub_tr.status_code == 202
        tr_job = {}
        for _ in range(120):
            tr_job = client.get(sub_tr.json()["status_url"]).json()
            if tr_job["status"] in {"completed", "failed"}:
                break
            time.sleep(0.02)
        assert tr_job["status"] == "completed"
        assert tr_job["translation_status"] == "translated"
        assert tr_job["translated_block_fraction"] >= 0.99
        downloaded = client.get(sub_tr.json()["download_url"])
        assert downloaded.status_code == 200
        assert downloaded.content.startswith(b"%PDF-")
        with fitz.open(stream=downloaded.content, filetype="pdf") as out_pdf:
            text_out = "\n".join(page.get_text("text") for page in out_pdf)
            assert marker in text_out


def test_id1_translation_aborts_repair_amplification_after_429(tmp_path, monkeypatch):
    source = tmp_path / "src.pdf"
    source.write_bytes(_make_pdf_bytes(4, "Independent section paragraph"))
    out = tmp_path / "out.pdf"

    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setenv("BLUESMINDS_API_KEY", "test-key")
    monkeypatch.setattr(time, "sleep", lambda _s: None)

    calls = []

    def rate_limited(batch, *_args, **_kwargs):
        calls.append(len(batch))
        raise RuntimeError("AI translation request failed with upstream HTTP 429.")

    monkeypatch.setattr(ai_engine, "_translate_text_batch", rate_limited)
    report: dict = {}
    with pytest.raises(RuntimeError, match="429"):
        ai_engine.translate_pdf_layout(source, out, target_lang="es", report=report)
    # 1 batch call, zero repair amplification calls after 429
    assert len(calls) == 1
    assert report["blocks_translated"] == 0


def test_id349_id394_offline_69p_summary_has_single_heading_and_preserves_inr(tmp_path, monkeypatch):
    pdf_path = tmp_path / "notes69.pdf"
    pdf_path.write_bytes(_make_pdf_bytes(69, "Detailed audit findings"))
    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", True)

    summary, citations = ai_engine.summarize_pdf(pdf_path, include_citations=True)
    assert len(citations) == 69
    assert summary.count("Executive Summary (Offline Analysis)") == 1
    assert summary.count("Local extractive notes from") == 0
    assert "INR 900,000" in summary


def test_id4_drive_confirm_link_extracts_uc_download_href():
    html = (
        '<html><body><a id="uc-download-link" '
        'href="https://drive.usercontent.google.com/download?id=abc123&export=download&confirm=t&uuid=xyz">'
        "Download anyway</a></body></html>"
    )
    confirm_url = server._confirm_drive_download(
        html.encode("utf-8"),
        "https://drive.google.com/uc?id=abc123",
        "abc123",
        {},
    )
    assert confirm_url is not None
    assert "drive.usercontent.google.com/download" in confirm_url
    assert "confirm=t" in confirm_url
    assert "id=abc123" in confirm_url


def test_id93_backup_service_has_explicit_healthcheck_in_compose():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    backup_block = compose.split("paperplane-backup:", 1)[1].split("nginx:", 1)[0]
    assert "healthcheck:" in backup_block
    assert "os.path.isdir('/backups') and os.path.isdir('/data')" in backup_block


def test_id358_id411_id375_id376_frontend_error_and_signout_contracts():
    security_js = (ROOT / "web" / "assets" / "security_forms.js").read_text(encoding="utf-8")
    opt_js = (ROOT / "web" / "assets" / "optimization_engine.js").read_text(encoding="utf-8")
    app_js = (ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")

    assert "await studioRequestError(resp, 'Digital signing')" in security_js
    assert "new Error(err.detail ||" not in opt_js
    assert "function studioRequestError(response, action)" in opt_js
    assert "switchWorkspaceView('desk')" in app_js.split("signoutBtn.onclick", 1)[1][:1200]
