import json
from pathlib import Path

import fitz
import openpyxl
import pytest
from fastapi.testclient import TestClient

import ai_engine
import converters
import security_forms_engine
import server


ROOT = Path(__file__).resolve().parents[1]


def test_id441_ai_chat_stream_429_does_not_leak_unrelated_rag_on_general_question(tmp_path, monkeypatch):
    source = tmp_path / "biology.pdf"
    with fitz.open() as pdf:
        pdf.new_page().insert_text((72, 72), "Quarterly biology lab notes and microscope calibration steps.")
        pdf.save(source)

    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setattr(ai_engine, "_current_bluesminds_api_key", lambda: "test-key")
    monkeypatch.setattr(
        ai_engine,
        "stream_bluesminds",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("upstream HTTP 429 rate limited")),
    )

    client = TestClient(server.app)
    with source.open("rb") as handle:
        resp = client.post(
            "/api/ai/chat/stream",
            data={"question": "What is the capital of Japan?"},
            files={"file": ("biology.pdf", handle, "application/pdf")},
        )
    assert resp.status_code == 200
    body = resp.text.lower()
    assert "rate" in body or "limit" in body or "error" in body
    assert "no relevant information found in the document" not in body
    assert "microscope calibration" not in body

    assert ai_engine.has_substantive_excerpt_match("Explain microscope calibration", "microscope calibration steps") is True
    assert ai_engine.has_substantive_excerpt_match("What does this document say?", "Quarterly biology lab notes") is False


def test_id394_currency_inr_decimal_and_punctuation_preserved():
    source_text = "Budget limit INR: 900,000.00 and reserve Rs. 45,500."
    summary = "Budget limit is 900000 (currency unspecified) and reserve is 45,500.00 (currency unspecified)."
    restored = ai_engine._restore_explicit_summary_currency(summary, source_text)
    assert "currency unspecified" not in restored.lower()
    assert "INR 900000" in restored
    assert "INR 45,500.00" in restored


def test_id1_translation_sequential_recovery_after_parallel_429(tmp_path, monkeypatch):
    source = tmp_path / "multi_batch.pdf"
    output = tmp_path / "translated_multi_batch.pdf"
    with fitz.open() as pdf:
        for i in range(4):
            page = pdf.new_page()
            page.insert_text((72, 72), f"Paragraph block number {i} with meaningful source text.")
        pdf.save(source)

    monkeypatch.setattr(ai_engine, "TRANSLATION_BATCH_SIZE", 1)
    monkeypatch.setattr(ai_engine, "TRANSLATION_MAX_PARALLEL_BATCHES", 2)
    monkeypatch.setattr(ai_engine.time, "sleep", lambda *_args, **_kwargs: None)

    attempts = {"count": 0}

    def flaky_translate_batch(batch, target_language, deadline=None):
        attempts["count"] += 1
        # First 4 parallel calls trip 429; subsequent sequential cooldown recovery succeeds.
        if attempts["count"] <= 4:
            raise RuntimeError("Translation provider failed (upstream HTTP 429).")
        return {block_id: f"Texto traducido {block_id} sobre documento." for block_id, _ in batch}

    monkeypatch.setattr(ai_engine, "_translate_text_batch", flaky_translate_batch)
    report = {}
    res = ai_engine.translate_pdf_layout(source, output, target_lang="es", report=report)
    assert res.exists()
    assert report["blocks_translated"] == 4
    assert report["translation_status"] != "failed"


def test_id423_dashboard_redirect_adds_no_store_cache_headers():
    client = TestClient(server.app)
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["location"] == "/tool-desk"
    cc = resp.headers.get("cache-control", "").lower()
    assert "no-store" in cc and "no-cache" in cc
    assert "paperplane_dashboard_notice=1" in (resp.headers.get("set-cookie", ""))


def test_id432_tool_pages_replace_merge_description():
    client = TestClient(server.app)
    resp = client.get("/compress-pdf")
    assert resp.status_code == 200
    assert "Combine multiple PDFs into one unified document" not in resp.text
    assert '<h1 id="tool-title">Compress PDF</h1>' in resp.text


def test_id398_uncached_excel_formula_evaluates_and_discloses_source(tmp_path):
    xlsx = tmp_path / "formulas.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Totals"
    ws.append(["Item", "Value"])
    ws.append(["Alpha", 10])
    ws.append(["Beta", 25])
    ws.append(["Direct", "=10+25"])
    ws.append(["Sum", "=SUM(B2:B3)"])
    ws.append(["Avg", "=AVERAGE(B2:B3)"])
    wb.save(xlsx)

    pdf_out = tmp_path / "formulas.pdf"
    converters.excel_to_pdf(xlsx, pdf_out)
    with fitz.open(pdf_out) as doc:
        text = "\n".join(page.get_text("text") for page in doc)
    assert "35" in text and "=10+25" in text
    assert "=SUM(B2:B3)" in text
    assert "17.5" in text and "=AVERAGE(B2:B3)" in text


def test_id308_id336_id256_converters_word_markdown_and_repair(tmp_path):
    # ID 336: bold 12pt label inside body line must not become a fake ## heading
    md_pdf = tmp_path / "bold_inline.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((60, 70), "Main Section Title", fontsize=20)
        page.insert_text((60, 110), "Note:", fontsize=11, fontname="hebo")
        page.insert_text((100, 110), "this is a normal descriptive sentence ending in a comma,", fontsize=11, fontname="helv")
        pdf.save(md_pdf)
    md_out = tmp_path / "bold_inline.md"
    converters.pdf_to_markdown(md_pdf, md_out)
    md_text = md_out.read_text(encoding="utf-8")
    assert "# Main Section Title" in md_text
    assert "## Note:" not in md_text

    # ID 256: corrupt file must not leak raw parser trace / Secondary parser failure
    corrupt = tmp_path / "corrupt.pdf"
    corrupt.write_bytes(b"not a real pdf binary header \x00\xff\xfe")
    with pytest.raises(ValueError) as exc_info:
        converters.repair_pdf(corrupt, tmp_path / "repaired.pdf")
    err_msg = str(exc_info.value)
    assert "pikepdf" not in err_msg.lower()
    assert "secondary parser failure" not in err_msg.lower()


def test_id427_security_forms_redaction_all_pages(tmp_path):
    source = tmp_path / "redact_multi.pdf"
    with fitz.open() as pdf:
        pdf.new_page().insert_text((72, 72), "Page 1 TOP_SECRET_TOKEN here")
        pdf.new_page().insert_text((72, 72), "Page 2 TOP_SECRET_TOKEN here")
        pdf.save(source)

    out = tmp_path / "redacted_multi.pdf"
    security_forms_engine.apply_hardened_redaction(
        source, out, [{"page": "all", "text": "TOP_SECRET_TOKEN"}]
    )
    with fitz.open(out) as doc:
        assert "TOP_SECRET_TOKEN" not in doc[0].get_text("text")
        assert "TOP_SECRET_TOKEN" not in doc[1].get_text("text")


def test_v28_frontend_bugfix_contracts():
    index_html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT / "web" / "assets" / "styles.css").read_text(encoding="utf-8")
    app_js = (ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    sec_js = (ROOT / "web" / "assets" / "security_forms.js").read_text(encoding="utf-8")
    conv_js = (ROOT / "web" / "assets" / "conversion_engine.js").read_text(encoding="utf-8")
    org_js = (ROOT / "web" / "assets" / "page_organizer.js").read_text(encoding="utf-8")
    editor_js = (ROOT / "web" / "assets" / "editor.js").read_text(encoding="utf-8")
    worker_js = (ROOT / "web" / "assets" / "local_pdf_worker.js").read_text(encoding="utf-8")

    # ID 429: no raw bullet dots placeholder
    assert 'placeholder="••••••••"' not in index_html

    # ID 416: #ai-file-input outside hidden #ai-empty-state
    empty_state_start = index_html.index('<div class="ai-empty-state" id="ai-empty-state">')
    assert index_html.index('id="ai-file-input"') < empty_state_start

    # ID 425 & 426: structured error formatting across Studio modules
    assert "window.formatStudioErrorMessage = function formatStudioErrorMessage" in app_js
    assert "async function studioFetchWithTimeout" in sec_js
    assert "throw await studioRequestError(resp, 'Form fill')" in sec_js
    assert "throw await studioRequestError(resp, 'Form flatten')" in sec_js
    assert "throw await studioRequestError(resp, 'Protection')" in sec_js
    assert "throw await studioRequestError(resp, 'Hardened redaction')" in sec_js
    assert "window.readStudioResponseError" in conv_js
    assert "window.readStudioResponseError" in org_js
    assert "window.readStudioResponseError" in editor_js

    # ID 427 & 433: no native blocking confirm() in flatten / reset / hardened redaction
    flatten_fn = sec_js.split("async applyFormFlatten()", 1)[1].split("async applyFormReset()", 1)[0]
    redact_fn = sec_js.split("async applyHardenedRedaction()", 1)[1]
    assert "confirm(" not in flatten_fn
    assert "confirm(" not in redact_fn

    # ID 362: Convert badges accurate
    assert '<span class="format-icon">DOCX</span>' in conv_js
    assert '<span class="format-icon">MD</span>' in conv_js
    assert '<span class="format-icon">TXT</span>' in conv_js

    # ID 431: View in Studio must not auto-bypass password via #password
    view_studio = app_js.split("const studioBtn = $('#result-view-studio-btn');", 1)[1].split("result.hidden = false;", 1)[0]
    assert "handoffPassword" not in view_studio
    assert "promptStudioPdfPassword" in app_js

    # ID 440: editor _markUnsaved syncs Undo/Redo buttons
    mark_unsaved = editor_js.split("_markUnsaved() {", 1)[1].split("_updateUnsavedIndicator() {", 1)[0]
    assert "this._updateHistoryButtons()" in mark_unsaved

    # ID 393: rotated/wide canvas scales proportionally
    assert "height: auto !important;" in styles_css.split(".studio-active .studio-page-sheet .pdf-page-canvas", 1)[1].split("\n", 1)[0]
    assert "aspectRatio = `${viewport.width} / ${viewport.height}`" in app_js

    # ID 333: metadata save preserves existing metadata
    assert "output: await pdf.save({ updateMetadata: false })" in worker_js

    # ID 434, 436, 437, 442: topbar breakpoint >=1460, topbar > studio-toolbar z-index, filters wrap, footer visible
    assert "@media (min-width: 901px) and (max-width: 1460px)" in styles_css
    assert "top: var(--topbar-height, 76px) !important;" in styles_css
    assert ".tool-desk-directory-filters { display: flex; flex-wrap: wrap;" in styles_css
    assert ".app-global-footer { visibility: visible; opacity: 1; pointer-events: auto;" in styles_css

    # ID 439 & 438 & 430 & 369: Ctrl+K Enter, sidebar All reset, preflight quota check, workspace file isolation
    assert "$('#command-input').onkeydown" in app_js
    assert 'data-desk-category="all"' in app_js.split("$$('.nav-category-tab').forEach", 1)[1].split("function renderSidebarTools", 1)[0]
    assert "totalUploadBytes >= 256 * 1024" in app_js
    assert "state.filesOrigin === 'desk'" in app_js
    assert "state.filesOrigin === 'ai'" in app_js.split("function saveToolSession(", 1)[1].split("toolSessionCache.set(", 1)[0]
    assert "!modal || modal.hidden || !document.hasFocus()" in app_js
    assert "if (!message) {" in conv_js
    assert "if (msg) window.showToast(msg, 'error');" in editor_js
    assert "if (detail) window.showToast(detail, 'error', 7000);" in org_js
