from __future__ import annotations

import json
import re
import time
from pathlib import Path

import fitz
import openpyxl
from fastapi.testclient import TestClient

import converters
import persistence
import server


ROOT = Path(__file__).resolve().parents[1]


def test_id418_unknown_routes_return_styled_html_404_and_api_returns_json():
    client = TestClient(server.app)

    # Browser / crawler requests without Accept: application/json get styled 404 HTML
    for headers in ({}, {"Accept": "text/html,application/xhtml+xml"}, {"Accept": "*/*"}):
        resp = client.get("/does-not-exist-v26-check", headers=headers)
        assert resp.status_code == 404
        assert resp.headers["content-type"].startswith("text/html")
        assert "404 Page Not Found" in resp.text
        assert 'href="/"' in resp.text

    # API / explicit JSON requests receive JSON 404
    api_resp = client.get("/api/nonexistent-endpoint-v26")
    assert api_resp.status_code == 404
    assert api_resp.headers["content-type"].startswith("application/json")
    assert api_resp.json() == {"detail": "Not Found"}

    json_page_resp = client.get("/does-not-exist-v26-check", headers={"Accept": "application/json"})
    assert json_page_resp.status_code == 404
    assert json_page_resp.headers["content-type"].startswith("application/json")


def test_id419_single_active_h1_and_workspace_title_suffixes():
    client = TestClient(server.app)

    routes_expected = [
        ("/", "Tool Desk"),
        ("/tool-desk", "Tool Desk"),
        ("/word-to-pdf", "Word to PDF"),
        ("/studio", "Paperplane PDF Studio"),
        ("/ai-intelligence", "AI Document Intelligence"),
        ("/pricing", "Paperplane Pricing"),
        ("/faq", "Frequently asked questions"),
        ("/settings", "Paperplane Settings"),
        ("/feedback", "Feedback"),
        ("/history", "Temporary results — no saved history"),
        ("/download", "Paperplane Downloads"),
        ("/apps", "Paperplane Apps for Desktop and Mobile"),
    ]
    for path, expected_h1 in routes_expected:
        resp = client.get(path)
        assert resp.status_code == 200
        h1_matches = re.findall(r"<h1[^>]*>(.*?)</h1>", resp.text, flags=re.DOTALL)
        assert len(h1_matches) == 1, f"{path} had {len(h1_matches)} H1 tags: {h1_matches}"
        assert expected_h1 in h1_matches[0], f"{path} expected {expected_h1}, got {h1_matches[0]}"

    for path in ("/pricing", "/faq", "/ai-intelligence"):
        resp = client.get(path)
        title_match = re.search(r"<title>(.*?)</title>", resp.text)
        assert title_match, path
        assert "| Paperplane" in title_match.group(1), title_match.group(1)


def test_id421_id422_no_raw_backticks_and_no_guest_user_placeholder():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    pricing_card = html.split("<!-- TIER 3:", 1)[1].split("<!-- TIER", 1)[0]
    assert "`sk_live_...`" not in pricing_card
    assert "<code>sk_live_...</code>" in pricing_card

    topbar_section = html.split('id="topbar-auth-user"', 1)[1].split("</div>", 1)[0]
    assert 'id="topbar-avatar"></span>' in topbar_section
    assert 'id="topbar-username"></span>' in topbar_section
    assert 'aria-hidden="true"' in html.split('id="topbar-auth-user"', 1)[0].splitlines()[-1] + html.split('id="topbar-auth-user"', 1)[1].splitlines()[0]


def test_id423_dashboard_redirect_sets_notice_cookie_and_preserves_301():
    client = TestClient(server.app)
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["location"] == "/tool-desk"
    assert "paperplane_dashboard_notice=1" in resp.headers.get("set-cookie", "")


def test_id389_html_to_pdf_hides_dropzone_in_ssr():
    client = TestClient(server.app)
    resp = client.get("/html-to-pdf")
    assert resp.status_code == 200
    assert '<div class="dropzone" id="dropzone" hidden>' in resp.text


def test_id282_clean_output_stem_strips_internal_counters_and_uuids():
    uuid_hex = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
    assert server._clean_output_stem(Path(f"{uuid_hex}_Annual_Report.pdf")) == "Annual_Report"
    assert server._clean_output_stem(Path(f"12_{uuid_hex}_2026_Budget.pdf")) == "2026_Budget"
    assert server._clean_output_stem(Path(f"{uuid_hex}_2026_Budget.pdf")) == "2026_Budget"
    assert server._clean_output_stem(Path(f"{uuid_hex}_wrong.pdf"), {"_original_filename": "Invoice_Q4.pdf"}) == "Invoice_Q4"


def test_id363_id364_studio_inspect_endpoints_bypass_daily_quota(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "DATABASE", tmp_path / "phase2-quota.sqlite")
    persistence.init_db()
    monkeypatch.setattr(server, "check_operation_quota", lambda *_a, **_kw: (False, 10, "free"))

    sample = tmp_path / "inspect.pdf"
    with fitz.open() as doc:
        p = doc.new_page()
        p.insert_text((72, 72), "Inspection document check")
        doc.save(sample)

    client = TestClient(server.app)
    sec_resp = client.post(
        "/api/studio/security/inspect",
        files={"file": ("inspect.pdf", sample.read_bytes(), "application/pdf")},
    )
    assert sec_resp.status_code == 200

    forms_resp = client.post(
        "/api/studio/forms/analyze",
        files={"file": ("inspect.pdf", sample.read_bytes(), "application/pdf")},
    )
    assert forms_resp.status_code == 200


def test_id251_id107_admin_analytics_counts_exam_pass_and_isolates_sandbox_revenue(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "DATABASE", str(tmp_path / "phase2-admin.sqlite"))
    persistence.init_db()

    for idx, tier in enumerate(("free", "exam_pass", "student_pro", "pro", "developer", "cyber_cafe")):
        uid = persistence.create_user(f"u{idx}@example.invalid", "StrongTestPass!123")
        persistence.set_user_tier(uid, tier)

    metrics = persistence.admin_get_extended_analytics()
    assert metrics["total_users"] == 6
    assert metrics["exam_pass_users"] == 1
    assert metrics["pro_users"] == 4  # pro + student_pro + exam_pass + cyber_cafe
    assert metrics["dev_users"] == 2  # developer + cyber_cafe
    assert metrics["free_users"] == 1

    # Sandbox payment must stay separate from gross_revenue_inr
    with persistence.connect() as conn:
        now = time.time()
        conn.execute(
            "INSERT INTO billing_events (id, event_type, customer_id, payload, created_at) VALUES (?, ?, ?, ?, ?)",
            ("ord_test_1", "cashfree.order_created", "u1", json.dumps({"gateway_environment": "TEST", "tier": "pro"}), now - 5),
        )
        conn.execute(
            "INSERT INTO billing_events (id, event_type, customer_id, payload, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                "evt_test_paid",
                "cashfree.order_verified",
                "u1",
                json.dumps({
                    "gateway_environment": "TEST",
                    "order": {"order_id": "ord_test_1", "order_amount": "3750.00", "order_currency": "INR", "order_status": "PAID"},
                    "payment": {"payment_status": "SUCCESS"},
                }),
                now,
            ),
        )
        conn.commit()

    rev = persistence.admin_get_revenue_analytics()
    assert rev["gross_revenue_inr"] == 0.0
    assert rev["sandbox_gross_inr"] == 3750.0
    assert rev["recent_transactions"][0]["status"] == "Sandbox paid"


def test_id398_uncached_excel_formula_does_not_render_blank(tmp_path):
    xlsx = tmp_path / "uncached.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "Item"
    ws["B1"] = "Cost"
    ws["A2"] = "Paper"
    ws["B2"] = "=10+25"
    wb.save(xlsx)

    pdf_out = tmp_path / "excel.pdf"
    converters.excel_to_pdf(xlsx, pdf_out)
    with fitz.open(pdf_out) as doc:
        text = doc[0].get_text("text")
        assert "=10+25" in text


def test_id333_local_metadata_preserves_original_producer_and_dates():
    worker = (ROOT / "web" / "assets" / "local_pdf_worker.js").read_text(encoding="utf-8")
    assert "operation === 'metadata' ? { updateMetadata: false } : undefined" in worker


def test_id369_ai_workspace_restore_requires_explicit_user_resume():
    app_js = (ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert 'id="ai-restored-resume-btn"' in html
    block = app_js.split("async function restoreAiWorkspace()", 1)[1].split("async function restoreStudioWorkspace()", 1)[0]
    assert "resumeBtn.onclick =" in block
    assert "state.files = [file]" in block.split("resumeBtn.onclick =", 1)[1]
    assert "state.files = [file]" not in block.split("resumeBtn.onclick =", 1)[0]
    assert "writeLocalWork('ai-pdf', localPdfRecord(state.files[0]))" in app_js


def test_ai_chat_stream_answers_generic_questions_even_with_open_pdf(tmp_path, monkeypatch):
    import ai_engine

    source = tmp_path / "notes.pdf"
    with fitz.open() as pdf:
        pdf.new_page().insert_text((72, 72), "Quarterly biology lab notes and microscope setup.")
        pdf.save(source)

    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setattr(ai_engine, "_current_bluesminds_api_key", lambda: "test-key")
    monkeypatch.setattr(
        ai_engine,
        "stream_bluesminds",
        lambda system, user, timeout_seconds=50: iter(["PDF preserves fixed page layout, while DOCX is editable word-processing text."]),
    )

    client = TestClient(server.app)
    with source.open("rb") as handle:
        general = client.post(
            "/api/ai/chat/stream",
            data={"question": "Explain the difference between PDF and DOCX?"},
            files={"file": (source.name, handle, "application/pdf")},
        )
    assert general.status_code == 200
    assert "PDF preserves fixed page layout" in general.text
    assert "No relevant information found" not in general.text

    with source.open("rb") as handle:
        doc_bound = client.post(
            "/api/ai/chat/stream",
            data={"question": "What does this PDF say about Mars?"},
            files={"file": (source.name, handle, "application/pdf")},
        )
    assert doc_bound.status_code == 200
    assert "No relevant information found in the document" in doc_bound.text

    assert ai_engine.correct_false_premise(source, "What is the capital of India?") is None
    assert "not Shanghai" in (ai_engine.correct_false_premise(source, "Shanghai is the capital of China, right?") or "")


def test_id423_dashboard_banner_and_feedback_confirmation_markup():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    app_js = (ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    feedback_js = (ROOT / "web" / "assets" / "feedback.js").read_text(encoding="utf-8")
    assert 'id="dashboard-redirect-notice"' in html
    assert "showDashboardRedirectNotice" in app_js
    assert 'id="feedback-page-confirmation"' in html
    assert 'document.getElementById("feedback-page-confirmation")' in feedback_js


def test_download_h1_placement_and_missing_routes_and_aliases():
    client = TestClient(server.app)
    download = client.get("/download").text
    assert download.count("<h1") == 1
    assert download.index('id="web-download-content"') < download.index("<h1>Paperplane Downloads</h1>")

    for path, heading in (("/about", "About Paperplane PDF"), ("/security", "Document security and processing controls")):
        res = client.get(path)
        assert res.status_code == 200
        assert f"<h1>{heading}</h1>" in res.text

    for auth_path in ("/login", "/signin", "/signup", "/register"):
        res = client.get(auth_path)
        assert res.status_code == 200
        assert "Tool Desk" in res.text

    for alias, target in (
        ("/png-to-pdf", "/jpg-to-pdf"),
        ("/compress-pdf-to-500kb", "/compress-pdf"),
        ("/delete-pages", "/remove-pages-pdf"),
        ("/reorder-pdf", "/organize-pdf"),
        ("/edit", "/edit-pdf"),
    ):
        res = client.get(alias, follow_redirects=False)
        assert res.status_code == 301
        assert res.headers["location"] == target

    sitemap = client.get("/sitemap.xml").text
    for expected in ("/tool-desk</loc>", "/studio</loc>", "/about</loc>", "/security</loc>"):
        assert expected in sitemap


def test_public_info_exit_and_auth_entry_timing_contract():
    app_js = (ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    switch_body = app_js.split("function switchWorkspaceView(", 1)[1].split("function showStudioEmptyState()", 1)[0]
    assert "$('#app-shell')?.classList.remove('public-info-active');" in switch_body
    assert "if (typeof syncVisiblePageHeading === 'function') syncVisiblePageHeading();" in switch_body
    auth_entry = app_js.split("const initialRouteSlug =", 1)[1].split("if (typeof syncVisiblePageHeading", 1)[0]
    assert "waitForInitialAuth().then(ready =>" in auth_entry
    assert "if (ready && !state.user && $('#auth-modal')?.hidden) openAuthModal(authModeTarget);" in auth_entry

