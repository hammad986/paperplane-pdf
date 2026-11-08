from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import ai_engine
import converters
import server


def make_pdf(path: Path, pages: int = 1) -> None:
    doc = fitz.open()
    for number in range(1, pages + 1):
        page = doc.new_page()
        page.insert_text((72, 72), f"Launch audit page {number}: local test document content.")
    doc.save(path)
    doc.close()


def test_false_premise_correction_works_without_a_document(monkeypatch):
    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setattr(ai_engine, "call_llm", lambda *args, **kwargs: pytest.fail("known false premise should be corrected locally"))
    client = TestClient(server.app)
    response = client.post("/api/ai/chat", data={"question": "Shanghai is the capital of China, right?"})
    assert response.status_code == 200
    assert "Beijing is the capital of China, not Shanghai" in response.json()["answer"]
    assert response.json()["citations"] == []


def test_citation_alignment_supports_plain_parenthesized_ranges_and_filters_templates():
    answer, citations = ai_engine.align_answer_citations(
        "Start Page 1, middle (p. 2), span [Pages 3–4], unsupported [Page 99], template [Page X].",
        {1, 2, 3, 4},
    )
    assert citations == [1, 2, 3, 4]
    assert answer.count("[Page 1]") == 1
    assert "[Page 2]" in answer and "[Pages 3, 4]" in answer
    assert "99" not in answer and "[Page X]" not in answer

    already_bracketed, bracketed_pages = ai_engine.align_answer_citations("The extracted answer [Page 1].", {1})
    assert already_bracketed == "The extracted answer [Page 1]."
    assert bracketed_pages == [1]

    already_parenthesized, parenthesized_pages = ai_engine.align_answer_citations("The extracted answer (Page 2).", {2})
    assert already_parenthesized == "The extracted answer [Page 2]."
    assert parenthesized_pages == [2]


def test_ai_status_endpoints_follow_bluesminds_provider_not_legacy_keys(monkeypatch):
    monkeypatch.setattr(server, "OPENAI_API_KEY", "")
    monkeypatch.setattr(server, "GEMINI_API_KEY", "")
    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setattr(ai_engine, "_current_bluesminds_api_key", lambda: "local-test-key")
    client = TestClient(server.app)
    assert client.get("/api/integrations").json()["ai"] is True
    assert client.get("/api/operations").json()["ai_chat"]["status"] == "AVAILABLE"

    monkeypatch.setattr(ai_engine, "_current_bluesminds_api_key", lambda: "")
    assert client.get("/api/integrations").json()["ai"] is False
    assert client.get("/api/operations").json()["ai_chat"]["status"] == "SERVICE_UNAVAILABLE"


def test_zero_success_ocr_fails_instead_of_emitting_a_false_output(tmp_path, monkeypatch):
    image_path = tmp_path / "scan.png"
    Image.new("RGB", (600, 300), "white").save(image_path)
    source = tmp_path / "scan.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(page.rect, filename=str(image_path))
    doc.save(source)
    doc.close()
    output = tmp_path / "ocr.pdf"

    def fail_ocr(*args, **kwargs):
        raise RuntimeError("synthetic OCR failure")

    monkeypatch.setattr(fitz.Page, "get_textpage_ocr", fail_ocr)
    with pytest.raises(RuntimeError, match="could not add searchable text"):
        converters.ocr_pdf(source, output, language="eng", mode="all")
    assert not output.exists()


def test_paid_upload_limit_includes_exact_500_mib_boundary():
    assert server.MAX_FILE_SIZE == 524_288_000
    assert server.upload_limit_bytes_for_tier("pro") == 524_288_000
    assert server.upload_limit_bytes_for_tier("free") == 50 * 1024 * 1024


def test_billable_ai_and_studio_success_count_but_failed_uploads_do_not(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "REQUIRE_AUTH", False)
    monkeypatch.setattr(server, "check_operation_quota", lambda *args: (True, 0, "free"))
    counted: list[str] = []
    monkeypatch.setattr(server, "increment_daily_usage", lambda subject: (counted.append(subject), len(counted))[1])
    monkeypatch.setattr(ai_engine, "summarize_pdf", lambda path: "Test overview [Page 1].")
    monkeypatch.setattr(ai_engine, "extract_chunks_from_pdf", lambda path: [SimpleNamespace(page_number=1, text="Test page")])
    client = TestClient(server.app)
    source = tmp_path / "source.pdf"
    make_pdf(source)

    with source.open("rb") as handle:
        result = client.post("/api/ai/summarize", files={"file": (source.name, handle, "application/pdf")})
    assert result.status_code == 200
    assert result.headers["X-Paperplane-Operations-Today"] == "1"
    assert len(counted) == 1

    with source.open("rb") as handle:
        result = client.post(
            "/api/studio/pages/rotate",
            data={"pages": "[1]", "degrees": "90"},
            files={"file": (source.name, handle, "application/pdf")},
        )
    assert result.status_code == 200
    assert result.headers["X-Paperplane-Operations-Today"] == "2"
    output = fitz.open(stream=result.content, filetype="pdf")
    assert len(output) == 1 and output[0].rotation == 90
    output.close()
    assert len(counted) == 2

    invalid = client.post(
        "/api/studio/pages/rotate",
        data={"pages": "[1]", "degrees": "90"},
        files={"file": ("bad.pdf", b"not a pdf", "application/pdf")},
    )
    assert invalid.status_code >= 400
    assert len(counted) == 2


def test_billable_quota_blocks_ai_and_studio_before_processing(monkeypatch):
    monkeypatch.setattr(server, "REQUIRE_AUTH", False)
    monkeypatch.setattr(server, "check_operation_quota", lambda *args: (False, 100, "free"))
    monkeypatch.setattr(server, "increment_daily_usage", lambda subject: pytest.fail("blocked request must not consume quota"))
    client = TestClient(server.app)
    response = client.post("/api/ai/summarize")
    assert response.status_code == 402
    assert response.json()["detail"]["code"] == "TIER_LIMIT_REACHED"


def test_tool_desk_studio_and_legacy_routes_render_or_redirect_to_real_targets():
    client = TestClient(server.app)
    desk = client.get("/tool-desk", follow_redirects=False)
    assert desk.status_code == 200
    assert '<div id="view-tool-desk-directory" class="tool-desk-directory">' in desk.text
    studio = client.get("/studio", follow_redirects=False)
    assert studio.status_code == 200
    assert '<div id="view-pdf-studio" class="pdf-studio">' in studio.text
    assert client.get("/fill-form", follow_redirects=False).headers["location"] == "/fill-pdf-form"
    assert client.get("/ai-translate", follow_redirects=False).headers["location"] == "/translate-pdf"


def test_studio_mutation_keeps_visible_page_as_reload_target():
    root = Path(__file__).resolve().parents[1]
    app_js = (root / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    organizer_js = (root / "web" / "assets" / "page_organizer.js").read_text(encoding="utf-8")
    assert "initialPage: targetPage" in organizer_js
    assert "Number(document.getElementById('page-jump-input')?.value) || this.state.activePage" in organizer_js
    assert "const renderDeadline = Date.now() + 10000" in app_js
    assert "const preservePageThroughModeChange = () =>" in app_js
    assert "jumpToStudioPage(pageToKeep, 'auto')" in app_js
    assert "document.documentElement.classList.toggle('studio-active', view === 'studio')" in app_js


def test_pdfjs_uses_csp_safe_dynamic_code_mode_and_controls_get_native_labels():
    root = Path(__file__).resolve().parents[1]
    app_js = (root / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    organizer_js = (root / "web" / "assets" / "page_organizer.js").read_text(encoding="utf-8")
    assert "isEvalSupported: false" in app_js
    assert "isEvalSupported: false" in organizer_js
    assert "addMissingControlLabels" in app_js
    assert "new MutationObserver" in app_js


def test_async_initial_route_preserves_an_explicitly_open_cloud_import_modal():
    root = Path(__file__).resolve().parents[1]
    app_js = (root / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    styles = (root / "web" / "assets" / "styles.css").read_text(encoding="utf-8")
    assert "preserveOpenCloudModal = false" in app_js
    assert "if (!preserveOpenCloudModal && view !== 'cloud'" in app_js
    assert "const setInitialView = (view, extra = null) => switchWorkspaceView(view, extra, false, true)" in app_js
    assert "selectOperation(OPERATION_BY_SLUG[pathSlug], true, true)" in app_js
    assert ".organizer-grid.strip-mode {\n    display: grid !important;" in styles
    assert "overflow-y: auto !important;" in styles
    assert "padding-bottom: 64px !important;" in styles
    assert "html.studio-active body .studio-canvas-area" in styles


def test_translation_ui_never_offers_source_preserved_fallback_as_a_successful_pdf():
    root = Path(__file__).resolve().parents[1]
    app_js = (root / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    translate_branch = app_js.split("if (operation === 'translate')", 1)[1].split("// Client-Side WASM", 1)[0]
    failure_branch = translate_branch.split("if (mode === 'failed' || mode === 'source_preserved')", 1)[1].split("const url = URL.createObjectURL(blob)", 1)[0]
    assert "Translation failed" in failure_branch
    assert "No translated download was created" in failure_branch
    assert "Download translated PDF" not in failure_branch
    assert "Partial translation ready" in translate_branch
    assert "Download partial translation" in translate_branch


def test_fill_form_json_map_wraps_long_values_and_is_submitted_with_job_options():
    root = Path(__file__).resolve().parents[1]
    app_js = (root / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    styles = (root / "web" / "assets" / "styles.css").read_text(encoding="utf-8")
    assert '<textarea id="fields" rows="3" wrap="soft"' in app_js
    assert "#options input, #options select, #options textarea" in app_js
    assert "const resizeFormMap = () =>" in app_js
    assert "Math.min(720, Math.round(window.innerHeight * 0.85))" in app_js
    assert ".option-field select,\n.option-field textarea {" in styles
    assert ".option-field textarea {\n  min-height: 4.5em;" in styles


def test_auth_restore_keeps_a_cached_header_identity_without_caching_entitlements():
    root = Path(__file__).resolve().parents[1]
    app_js = (root / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    styles = (root / "web" / "assets" / "styles.css").read_text(encoding="utf-8")
    assert "paperplane-last-auth-shell-email" in app_js
    assert "function restoreCachedAuthShell()" in app_js
    assert "document.body.classList.add('auth-restoring')" in app_js
    assert "const startupNavigationVersion = workspaceNavigationVersion;\n  restoreCachedAuthShell();" in app_js
    assert "cacheAuthShellEmail(data.email);" in app_js
    assert "clearAuthShellEmail();" in app_js
    assert ".auth-pending.auth-restoring #topbar-auth-user { visibility: visible; }" in styles
    assert "state.user = data.authenticated ? data : null;" in app_js
    assert "min-width: 0;" in styles and "box-sizing: border-box;" in styles


def test_excel_to_pdf_wraps_and_preserves_full_cell_values_for_xlsx_and_csv(tmp_path):
    workbook = converters.openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Item", "Amount", "Status"])
    sheet.append(["Application", "19.00", "Paid"])
    sheet.append(["Audit marker", "AUDIT_OFFICE_EXCEL_OUTPUT", "Synthetic"])
    xlsx_source = tmp_path / "audit.xlsx"
    workbook.save(xlsx_source)

    xlsx_output = tmp_path / "audit-xlsx.pdf"
    converters.excel_to_pdf(xlsx_source, xlsx_output)
    with fitz.open(xlsx_output) as pdf:
        xlsx_text = "\n".join(page.get_text() for page in pdf)
    assert "Application" in xlsx_text
    assert "AUDIT_OFFICE_EXCEL_OUTPUT" in xlsx_text

    csv_source = tmp_path / "audit.csv"
    csv_source.write_text('Name,Value\n"Application",19\n"Audit marker",AUDIT_CSV_OUTPUT\n', encoding="utf-8")
    csv_output = tmp_path / "audit-csv.pdf"
    converters.excel_to_pdf(csv_source, csv_output)
    with fitz.open(csv_output) as pdf:
        csv_text = "\n".join(page.get_text() for page in pdf)
    assert "Application" in csv_text
    assert "AUDIT_CSV_OUTPUT" in csv_text
