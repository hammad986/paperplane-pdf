import io
import base64
import json
import re
import secrets
import struct
import time
import zlib
from pathlib import Path
import fitz
import pytest
from zipfile import ZipFile
from xml.etree import ElementTree

import ai_engine
import server
import converters
import persistence
import security_forms_engine
from PIL import Image, ImageChops, ImageStat
from pypdf import PdfReader
from fastapi.testclient import TestClient


def test_mobile_result_download_has_touch_target_and_fresh_stylesheet_cache_key():
    styles = (Path(__file__).resolve().parents[1] / "web" / "assets" / "styles.css").read_text(encoding="utf-8")
    html = (Path(__file__).resolve().parents[1] / "web" / "index.html").read_text(encoding="utf-8")
    assert ".result-actions .btn-download { min-height: 44px; box-sizing: border-box; }" in styles
    assert "/assets/styles.css?v=61" in html


def test_developer_api_key_prefix_is_escaped_before_html_rendering():
    app_js = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    escaped_prefix = "<code style=\"font-family: var(--font-mono); font-size: 11px;\">${escapeHtml(k.key_prefix)}</code>"
    assert app_js.count(escaped_prefix) == 2
    assert "<code style=\"font-family: var(--font-mono); font-size: 11px;\">${k.key_prefix}</code>" not in app_js


def test_ai_extraction_quantity_and_source_page_values_are_escaped():
    app_js = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    assert "${escapeHtml(item.quantity != null ? String(item.quantity) : '1')}" in app_js
    assert "Page ${escapeHtml(String(p))}" in app_js


def test_annotation_document_closes_when_annotation_validation_fails(tmp_path, monkeypatch):
    source = tmp_path / "source.pdf"
    document = fitz.open()
    document.new_page()
    document.save(source)
    document.close()

    real_open = fitz.open
    state = {"closed": False}

    class TrackedDocument:
        def __init__(self, path):
            self.document = real_open(path)

        def __enter__(self):
            return self.document.__enter__()

        def __exit__(self, *args):
            state["closed"] = True
            return self.document.__exit__(*args)

    monkeypatch.setattr(converters.fitz, "open", TrackedDocument)
    with pytest.raises(ValueError, match="Unsupported annotation type"):
        converters.annotate_pdf(source, tmp_path / "out.pdf", annotations=[{"type": "invalid"}])

    assert state["closed"] is True


def test_translation_parser_accepts_string_segment_ids_without_accepting_invalid_ids():
    response = json.dumps({"translations": [
        {"id": "0", "text": "तैयार"},
        {"id": 1, "text": "समीक्षा"},
        {"id": True, "text": "must not map to segment 1"},
        {"id": "01", "text": "ambiguous leading zero"},
        {"id": "2", "text": "outside this batch"},
    ]}, ensure_ascii=False)

    assert ai_engine._parse_translation_batch(response, [0, 1]) == {0: "तैयार", 1: "समीक्षा"}


def test_aadhaar_pdf_mask_removes_first_eight_and_preserves_each_synthetic_suffix(tmp_path):
    source = tmp_path / "synthetic-aadhaar.pdf"
    output = tmp_path / "masked-aadhaar.pdf"
    with fitz.open() as document:
        page = document.new_page(width=420, height=240)
        page.insert_text((36, 60), "Synthetic only A: 1234 5678 9012", fontsize=12)
        page.insert_text((36, 110), "Synthetic only B: 2345-6789-3456", fontsize=12)
        page.insert_text((36, 160), "Synthetic only C: 345678901234", fontsize=12)
        document.save(source)

    security_forms_engine.mask_aadhaar_pdf(source, output)

    with fitz.open(output) as masked:
        text = "\n".join(page.get_text() for page in masked)
    assert text.count("XXXX XXXX") == 3
    assert all(suffix in text for suffix in ("9012", "3456", "1234"))
    assert not any(number in text for number in ("1234 5678 9012", "2345-6789-3456", "345678901234"))


def test_password_reset_response_uses_text_nodes_and_same_origin_token_link():
    app_js = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    reset_flow = app_js.split("const forgotPwForm = $('#forgot-password-form')", 1)[1].split("// Password Reset Modal Handlers", 1)[0]
    assert "message.textContent = typeof res.message === 'string'" in reset_flow
    assert "new URL(String(res.dev_reset_url), window.location.href)" in reset_flow
    assert "resetUrl.origin === window.location.origin" in reset_flow
    assert "resetUrl.searchParams.has('reset_token')" in reset_flow
    assert "msg.innerHTML" not in reset_flow


def test_compare_operation_description_names_downloaded_txt_diff():
    operation = TestClient(server.app).get("/api/operations").json()["compare"]
    assert ".txt diff file" in operation["description"]


def test_student_batch_limit_is_enforced_and_full_pro_retains_large_batch():
    from server import plan_limits_payload

    client = TestClient(server.app)
    student_id = persistence.create_user(f"student-batch-{secrets.token_hex(4)}@example.test", "BatchLimitPass123!")
    persistence.set_user_tier(student_id, "student_pro")
    student_token = persistence.create_session_for_user(student_id)["token"]
    student_headers = {"Cookie": f"paperplane_token={student_token}"}
    student_profile = client.get("/api/auth/me", headers=student_headers).json()
    assert student_profile["plan_limits"]["max_batch_files"] == 10

    files11 = [{"name": f"source-{index}.pdf", "size": 1024} for index in range(11)]
    rejected = client.post("/api/uploads/chunked", json={"operation": "merge", "files": files11}, headers=student_headers)
    assert rejected.status_code == 400
    assert "at most 10 files" in rejected.json()["detail"]

    pro_id = persistence.create_user(f"full-pro-batch-{secrets.token_hex(4)}@example.test", "BatchLimitPass123!")
    persistence.set_user_tier(pro_id, "pro")
    pro_token = persistence.create_session_for_user(pro_id)["token"]
    pro_headers = {"Cookie": f"paperplane_token={pro_token}"}
    assert client.get("/api/auth/me", headers=pro_headers).json()["plan_limits"]["max_batch_files"] == 100
    accepted = client.post("/api/uploads/chunked", json={"operation": "merge", "files": files11}, headers=pro_headers)
    assert accepted.status_code == 201
    upload_id = accepted.json()["upload_id"]
    assert client.delete(f"/api/uploads/chunked/{upload_id}", headers=pro_headers).json() == {"deleted": True}
    assert plan_limits_payload("exam_pass")["max_batch_files"] == 10


def test_pdf_edit_tool_does_not_claim_existing_text_replacement():
    client = TestClient(server.app)
    operation = client.get("/api/operations").json()["edit"]
    seo = client.get("/api/seo/edit").json()
    assert operation["label"] == "Add Text & Stamps"
    assert "Existing PDF text cannot be selected or replaced" in operation["description"]
    assert "Existing text cannot currently be selected, replaced, or rewritten" in str(seo["faqs"])
    assert "Add Text, Stamps & Shapes" in seo["heading"]


def test_repair_report_renders_pdf_derived_issues_as_text():
    source = (Path(__file__).resolve().parents[1] / "web" / "assets" / "optimization_engine.js").read_text(encoding="utf-8")
    assert "issues.appendChild(document.createTextNode(`• ${String(issue)}`))" in source
    assert "issues.innerHTML = (report.detected_issues" not in source


def test_admin_revenue_amounts_are_normalized_before_html_rendering():
    root = Path(__file__).resolve().parents[1]
    source = (root / "web" / "assets" / "admin.js").read_text(encoding="utf-8")
    html = (root / "server.py").read_text(encoding="utf-8")
    assert "const amount = Number(ord.amount);" in source
    assert "Number.isFinite(amount) ? amount.toLocaleString(\"en-IN\") : \"0\"" in source
    assert "₹${amountLabel}" in source
    assert "(ord.amount || 0).toLocaleString" not in source
    assert 'admin.js?v=18' in html
    assert '.analytics-section > .chart-card { min-width: 0; }' in html
    assert 'overflow-x: auto;' in html
    assert 'role="region" aria-label="14-day signup trend chart' in html
    assert '@media (max-width: 600px)' in html
    assert 'aria-label="Paying customers and recent transactions" tabindex="0"' in html
    assert '.table-container:focus-visible' in html


def test_admin_signup_chart_escapes_untrusted_dates_and_normalizes_counts():
    root = Path(__file__).resolve().parents[1]
    source = (root / "web" / "assets" / "admin.js").read_text(encoding="utf-8")
    assert "const trendDays = (Array.isArray(days) ? days : []).slice(-14);" in source
    assert "return Number.isFinite(value) ? Math.max(0, Math.trunc(value)) : 0;" in source
    assert 'const dateLabel = escapeHtml(d?.date || "");' in source
    assert 'title="${dateLabel}: ${count} signups"' in source


def test_pdfa_catalog_reports_missing_ghostscript_dependency(monkeypatch):
    monkeypatch.setattr(server.converters.shutil, "which", lambda _name: None)
    operation = TestClient(server.app).get("/api/operations").json()["pdf_to_pdfa"]
    assert operation["available"] is False
    assert operation["status"] == "DEPENDENCY_MISSING"
    assert "Ghostscript" in operation["prerequisite"]


def test_tool_directory_aliases_redirect_to_canonical_pages():
    client = TestClient(server.app)
    for path in ("/tools", "/all-tools"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 301
        assert response.headers["location"] == "/tool-desk"

    scan = client.get("/scan-pdf", follow_redirects=False)
    assert scan.status_code == 301
    assert scan.headers["location"] == "/scan-to-pdf"


def test_seo_landing_routes_have_route_specific_headings_and_content():
    client = TestClient(server.app)
    for slug, heading in (
        ("compress-pdf-to-100kb", "Compress PDF to under 100 KB for Government Applications"),
        ("compress-pdf-to-200kb", "Compress PDF to under 200 KB Online"),
        ("convert-pdf", "Convert PDF files to the format you need"),
        ("pdf-security", "Secure PDF documents without losing control"),
    ):
        response = client.get(f"/{slug}")
        assert response.status_code == 200
        assert f"<h1>{heading}</h1>" in response.text
        assert 'id="seo-page-heading"' in response.text

    download = client.get("/download").text
    apps = client.get("/apps").text
    assert "<h1>Paperplane Downloads</h1>" in download
    assert "<h1>Paperplane Apps for Desktop and Mobile</h1>" in apps
    assert "There are no desktop or mobile installers to download yet" in download
    assert "Choose a platform below to join its release-update waitlist" in apps
    assert download != apps


def test_legal_developer_and_password_reset_routes_render_page_headings():
    client = TestClient(server.app)
    privacy = client.get("/privacy").text
    terms = client.get("/terms").text
    developers = client.get("/developers").text
    reset = client.get("/reset-password").text
    assert '<h1 id="legal-page-title">Paperplane Privacy Policy &amp; Data Protection</h1>' in privacy
    assert '<h1 id="legal-page-title">Terms of Service</h1>' in terms
    assert "<h1>Developer REST API reference</h1>" in developers
    assert 'id="reset-password-title">Reset Account Password</h1>' in reset
    assert 'role="dialog" aria-modal="true" aria-labelledby="reset-password-title"' in reset
    assert 'id="reset-password-modal"' in reset and 'id="reset-password-form"' in reset

    app_js = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    assert "const legalTitle = $('#legal-page-title')" in app_js
    assert "pathSlug === 'compress-pdf-to-100kb' || pathSlug === 'compress-pdf-to-200kb'" in app_js


def test_cloud_import_entry_points_share_one_dialog():
    response = TestClient(server.app).get("/")
    assert response.status_code == 200
    assert response.text.count('id="cloud-modal"') == 1
    assert response.text.count('id="cloud-url"') == 1
    assert response.text.count('id="cloud-submit-btn"') == 1
    app_js = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    assert "if ($('#topbar-cloud-btn')) $('#topbar-cloud-btn').onclick = openCloudModal" in app_js
    assert "if ($('#cloud-drop-btn')) $('#cloud-drop-btn').onclick = openCloudModal" in app_js


def test_processing_mode_uses_one_browser_label_and_states_its_active_mode():
    response = TestClient(server.app).get("/")
    assert response.status_code == 200
    assert 'id="privacy-mode-label">Use browser processing</span>' in response.text
    assert 'aria-label="Use browser processing for the current tool"' in response.text
    assert '<strong>Browser processing</strong>' in response.text
    assert 'aria-label="Prefer browser processing for supported tools"' in response.text
    app_js = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    assert "Browser processing is on for " in app_js
    assert "Browser processing is off for " in app_js
    assert "uploads files for temporary server processing." in app_js
    assert "Prefer browser processing for supported tools" in app_js
    assert "Server Mode" not in response.text and "Local Processing" not in response.text


def test_developer_api_key_creation_is_tier_gated_in_ui_and_server():
    response = TestClient(server.app).get("/")
    assert 'id="settings-create-key-form" hidden' in response.text
    assert 'id="settings-api-key-upgrade-hint"' in response.text

    app_js = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    assert "function updateDeveloperApiKeyAccess" in app_js
    assert "form.hidden = !canManageApiKeys" in app_js
    assert "['developer', 'cyber_cafe'].includes(tier)" in app_js

    client = TestClient(server.app)
    for tier in ("free", "student_pro", "exam_pass"):
        email = f"api-gate-{tier}-{secrets.token_hex(4)}@example.test"
        user_id = persistence.create_user(email, "ApiGatePassword123!")
        persistence.set_user_tier(user_id, tier)
        token = persistence.create_session_for_user(user_id)["token"]
        response = client.post(
            "/api/developer/keys",
            json={"name": "must stay gated"},
            headers={"Cookie": f"paperplane_token={token}"},
        )
        assert response.status_code == 403, (tier, response.status_code, response.text)


def test_authenticated_settings_guest_controls_are_removed_and_restorable():
    app_js = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    assert "if (authenticated) settingsGuestActions.replaceChildren()" in app_js
    assert "else if (!settingsGuestActions.childElementCount) settingsGuestActions.innerHTML = SETTINGS_GUEST_ACTIONS_HTML" in app_js
    assert "#settings-guest-actions').onclick = event =>" in app_js


def test_scan_to_pdf_copy_matches_automatic_enhancement_and_page_size_options():
    description = server.OPERATIONS["scan_pdf"]["description"]
    assert "A4, US Letter, or original photo size at 200 DPI" in description
    assert "Automatic contrast and sharpness enhancement is applied" in description
    assert "optional contrast" not in description.lower()
    app_js = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    assert "value: 'a4'" in app_js and "value: 'letter'" in app_js and "value: 'original'" in app_js


def test_jpg_to_pdf_and_scan_to_pdf_show_real_completion_progress():
    html = TestClient(server.app).get("/").text
    assert 'id="progress-card"' in html and 'id="progress-percent"' in html
    assert 'id="progress-status-title" role="status"' in html
    app_js = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    assert "updateProgress(4, 100, 'Finished!')" in app_js
    assert "$('#progress-card').hidden = false" in app_js


def test_ai_chat_citation_renderers_deduplicate_page_numbers():
    app_js = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    assert "const uniqueCitations = uniqueAiCitationPages(data.citations)" in app_js
    assert "uniqueCitations.map(aiPageCitationTag).join('')" in app_js
    assert "responseCitations = uniqueAiCitationPages(payload.citations)" in app_js


def test_chat_metadata_title_uses_visible_first_page_heading_and_original_filename(tmp_path):
    source = tmp_path / "chat-stream-temporary.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((90, 100), "Project Atlas Evaluation", fontsize=22)
        page.insert_text((90, 155), "A report on the evaluation of sample systems.", fontsize=11)
        pdf.save(source)
    result = ai_engine.chat_with_pdf(source, "What is the title of this document?", filename="atlas-report.pdf")
    assert "Project Atlas Evaluation" in result["answer"]
    assert "atlas-report.pdf" in result["answer"]
    assert "chat-stream-temporary.pdf" not in result["answer"]


def test_watermark_unicode_font_fallback_preserves_checkmark_and_accent(tmp_path):
    source=tmp_path/"unicode-watermark-source.pdf"
    with fitz.open() as pdf:
        pdf.new_page();pdf.save(source)
    output=server.process("watermark",[source],{"text":"v20 stamp ✓ café — APPROVED"},tmp_path)
    with fitz.open(output) as pdf:
        extracted=pdf[0].get_text()
        assert "v20 stamp ✓ café — APPROVED" in extracted,repr(extracted)
        fonts=pdf[0].get_fonts(full=True)
        assert any(pdf.xref_get_key(font[0],"ToUnicode")[0] != "null" for font in fonts)


def test_watermark_and_page_numbers_use_selected_mark_colour_and_contrast_outline(tmp_path):
    source = tmp_path / "contrast-source.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.draw_rect(page.rect, color=(0.08, 0.08, 0.08), fill=(0.08, 0.08, 0.08))
        pdf.save(source)
    options = {"text": "VISIBLE MARK", "mark_color": "#ff0000", "mark_background": "dark"}
    watermark = server.process("watermark", [source], options, tmp_path)
    numbers = server.process("page_numbers", [source], {**options, "format": "{n}"}, tmp_path)
    with fitz.open(stream=server.overlay(612, 792, "VISIBLE MARK", "watermark", options), filetype="pdf") as pdf:
        marks = [span for span in pdf[0].get_texttrace() if "VISIBLE MARK" in "".join(chr(char[0]) for char in span["chars"])]
        assert any(mark["color"] == pytest.approx((1.0, 0.0, 0.0)) and mark["type"] == 0 for mark in marks)
        assert any(mark["color"] == pytest.approx((1.0, 1.0, 1.0)) and mark["type"] == 1 for mark in marks)
    for output, expected in ((watermark, "VISIBLE MARK"), (numbers, "1")):
        with fitz.open(output) as pdf:
            page = pdf[0]
            assert expected in page.get_text()
            rendered_marks = [span for span in page.get_texttrace() if expected in "".join(chr(char[0]) for char in span["chars"])]
            assert rendered_marks
            assert rendered_marks[0]["color"] == pytest.approx((1.0, 0.0, 0.0))


def test_image_watermark_rejects_oversized_pixel_dimensions_before_decode(tmp_path):
    source = tmp_path / "watermark-source.pdf"
    with fitz.open() as document:
        document.new_page().insert_text((72, 72), "Source remains readable")
        document.save(source)

    small_png = tmp_path / "small.png"
    Image.new("RGBA", (1, 1), (255, 0, 0, 255)).save(small_png)
    png_bytes = bytearray(small_png.read_bytes())
    # Keep the tiny IDAT stream but provide a valid IHDR with 24 million pixels.
    struct.pack_into(">II", png_bytes, 16, 24000, 1000)
    struct.pack_into(">I", png_bytes, 29, zlib.crc32(png_bytes[12:29]) & 0xffffffff)
    oversized_png = tmp_path / "oversized.png"
    oversized_png.write_bytes(png_bytes)
    output = tmp_path / "oversized-watermarked.pdf"

    with pytest.raises(ValueError, match="20-megapixel processing limit"):
        converters.apply_image_watermark(source, output, oversized_png)
    assert not output.exists()

    with fitz.open(source) as original:
        assert "Source remains readable" in original[0].get_text()

    data_url = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
    with pytest.raises(ValueError, match="20-megapixel processing limit"):
        server.process("watermark", [source], {"watermark_image_data": data_url}, tmp_path)
    assert not list(tmp_path.glob("wm_*.png"))


def test_server_image_watermark_bounds_payload_and_validates_data_url(tmp_path, monkeypatch):
    source = tmp_path / "watermark-source.pdf"
    with fitz.open() as document:
        document.new_page().insert_text((72, 72), "Source remains readable")
        document.save(source)

    monkeypatch.setattr(server, "MAX_WATERMARK_IMAGE_BYTES", 8)
    oversized = "data:image/png;base64," + base64.b64encode(b"123456789").decode("ascii")
    with pytest.raises(ValueError, match="25 MiB processing limit"):
        server.process("watermark", [source], {"watermark_image_data": oversized}, tmp_path)

    malformed = "data:image/png;base64,%%%"
    with pytest.raises(ValueError, match="data is invalid"):
        server.process("watermark", [source], {"watermark_image_data": malformed}, tmp_path)

    unsupported = "data:image/gif;base64," + base64.b64encode(b"GIF89a").decode("ascii")
    with pytest.raises(ValueError, match="must be a PNG or JPEG"):
        server.process("watermark", [source], {"watermark_image_data": unsupported}, tmp_path)

    truncated_data_url = "data:image/png;base64"
    with pytest.raises(ValueError, match="data URL is invalid"):
        server.process("watermark", [source], {"watermark_image_data": truncated_data_url}, tmp_path)


@pytest.mark.parametrize("operation", ["watermark", "page_numbers"])
def test_overlay_operations_return_terminal_timeout_instead_of_hanging_job(tmp_path, monkeypatch, operation):
    source = tmp_path / f"slow-{operation}.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(source)
    monkeypatch.setattr(server, "WATERMARK_TIMEOUT_SECONDS", 0.001)
    options = {"text": "TEST WATERMARK"} if operation == "watermark" else {"format": "{n}"}
    with pytest.raises(TimeoutError, match="processing timed out"):
        server.process(operation, [source], options, tmp_path)
    assert not (tmp_path / f"slow-{operation}_{operation}.pdf").exists()


def test_image_watermark_returns_terminal_timeout_instead_of_hanging_job(tmp_path, monkeypatch):
    source = tmp_path / "slow-image-watermark.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(source)
    monkeypatch.setattr(server, "WATERMARK_TIMEOUT_SECONDS", 0.001)
    options = {"watermark_image_data": "data:image/png;base64," + base64.b64encode(b"image").decode("ascii")}
    with pytest.raises(TimeoutError, match="processing timed out"):
        server.process("watermark", [source], options, tmp_path)
    assert not (tmp_path / "slow-image-watermark_watermark.pdf").exists()
    assert not list(tmp_path.glob("wm_*.png"))


def test_visual_signature_uses_selected_colour_and_background_outline(tmp_path):
    source = tmp_path / "dark-signature-source.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.draw_rect(page.rect, color=(0.08, 0.08, 0.08), fill=(0.08, 0.08, 0.08))
        pdf.save(source)
    output = server.process("sign", [source], {
        "signature": "Audit Signer", "signer_name": "Audit Signer",
        "signature_color": "#ff0000", "mark_background": "dark"
    }, tmp_path)
    with fitz.open(output) as pdf:
        spans = [span for span in pdf[0].get_texttrace() if "Audit Signer" in "".join(chr(char[0]) for char in span["chars"])]
        assert spans
        assert any(span["color"] == pytest.approx((1.0, 0.0, 0.0)) and span["type"] == 0 for span in spans)
        assert any(span["color"] == pytest.approx((1.0, 1.0, 1.0)) and span["type"] == 1 for span in spans)


def test_drawn_visual_signature_gets_light_outline_on_dark_page(tmp_path):
    source = tmp_path / "dark-image-signature-source.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.draw_rect(page.rect, color=(0.08, 0.08, 0.08), fill=(0.08, 0.08, 0.08))
        pdf.save(source)
    from PIL import Image, ImageDraw
    signature = Image.new("RGBA", (120, 48), (0, 0, 0, 0))
    ImageDraw.Draw(signature).line((5, 38, 34, 6, 55, 32, 82, 4, 113, 28), fill=(0, 0, 255, 255), width=5)
    image_data = io.BytesIO()
    signature.save(image_data, format="PNG")
    output = security_forms_engine.add_visual_signature(
        source, tmp_path / "outlined-drawn-signature.pdf", image_data.getvalue(),
        signer_name="", page_background="dark"
    )
    with fitz.open(output) as pdf:
        images = pdf[0].get_images(full=True)
        assert images
        extracted = pdf.extract_image(images[0][0])
        with Image.open(io.BytesIO(extracted["image"])).convert("RGBA") as placed:
            pixels = placed.get_flattened_data()
            white_outline = sum(1 for pixel in pixels if pixel[:3] == (255, 255, 255) and pixel[3] > 0)
            blue_signature = sum(1 for pixel in pixels if pixel[2] > 200 and pixel[0] < 20 and pixel[3] > 0)
        assert white_outline > 0
        assert blue_signature > 0


def test_mobile_scan_and_installable_web_app_contracts():
    client = TestClient(server.app)
    manifest_response = client.get("/manifest.webmanifest")
    assert manifest_response.status_code == 200
    assert manifest_response.headers["content-type"].startswith("application/manifest+json")
    manifest = manifest_response.json()
    assert manifest["id"] == manifest["start_url"] == "/"
    assert manifest["display"] == "standalone"
    for icon in manifest["icons"]:
        response = client.get(icon["src"])
        assert response.status_code == 200
        assert response.content.startswith(b"\x89PNG\r\n\x1a\n")

    worker_response = client.get("/service-worker.js")
    assert worker_response.status_code == 200
    assert worker_response.headers["service-worker-allowed"] == "/"
    assert "startsWith('/api/')" in worker_response.text

    scan_response = client.get("/scan-to-pdf")
    assert scan_response.status_code == 200
    assert 'rel="manifest" href="/manifest.webmanifest"' in scan_response.text
    assert 'capture="environment"' in scan_response.text
    assert 'id="scan-camera-btn"' in scan_response.text

    nginx = (Path(__file__).resolve().parents[1] / "deploy" / "nginx.conf.template").read_text(encoding="utf-8")
    assert 'Permissions-Policy "camera=(self), microphone=(), geolocation=()"' in nginx


def test_legal_spa_navigation_updates_page_title():
    app_js=(Path(__file__).resolve().parents[1]/"web"/"assets"/"app.js").read_text(encoding="utf-8")
    assert "document.title = `${isTerms ? 'Terms of Service' : 'Privacy Policy'} | Paperplane`" in app_js
    assert "if (state.activeView === 'legal') document.title = `${isPrivacy ? 'Privacy Policy' : 'Terms of Service'} | Paperplane`" in app_js


def test_translate_restart_preserves_selected_target_language():
    app_js=(Path(__file__).resolve().parents[1]/"web"/"assets"/"app.js").read_text(encoding="utf-8")
    assert "const selectedTranslationLanguage = state.operation === 'translate' ? $('#target_language')?.value : null" in app_js
    assert "if (selectedTranslationLanguage && $('#target_language')) $('#target_language').value = selectedTranslationLanguage" in app_js


def test_html_404_page_has_responsive_workspace_navigation():
    response = TestClient(server.app).get("/missing-paperplane-route", headers={"accept": "text/html"})
    assert response.status_code == 404
    assert 'aria-label="Main navigation"' in response.text
    for href in ("/tool-desk", "/studio", "/ai-intelligence", "/pricing"):
        assert f'href="{href}"' in response.text
    assert "flex-wrap: wrap" in response.text


def test_ai_provider_health_is_shared_storage_sanitized_and_worker_readable(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "DATABASE", tmp_path / "provider-health.sqlite")
    persistence.init_db()

    persistence.set_ai_provider_health_status({
        "last_request_at": "2026-11-16T12:00:00+00:00",
        "last_status": "rate_limited",
        "last_provider": "openai_compatible",
        "fallback_active": True,
        "last_failure": "rate_limit",
        "api_key": "must-not-be-stored",
        "raw_provider_body": "must-not-be-stored-either",
    })

    # A fresh database read models another worker process reading shared state.
    loaded = persistence.get_ai_provider_health_status()
    assert loaded == {
        "last_request_at": "2026-11-16T12:00:00+00:00",
        "last_status": "rate_limited",
        "last_provider": "openai_compatible",
        "fallback_active": True,
        "last_failure": "rate_limit",
    }
    with persistence.closing(persistence.connect()) as connection:
        row = connection.execute(
            "SELECT value FROM admin_system_settings WHERE key='AI_PROVIDER_HEALTH'"
        ).fetchone()
    assert "must-not-be-stored" not in row["value"]


def test_translation_below_half_fails_with_actual_fraction(tmp_path, monkeypatch):
    source = tmp_path / "three-blocks.pdf"
    output = tmp_path / "translation.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page()
        for y, text in [(72, "First source block"), (150, "Second source block"), (228, "Third source block")]:
            page.insert_text((72, y), text)
        pdf.save(source)

    monkeypatch.setattr(ai_engine, "TRANSLATION_BATCH_SIZE", 1)
    monkeypatch.setattr(ai_engine, "TRANSLATION_MAX_PARALLEL_BATCHES", 1)
    monkeypatch.setattr(ai_engine, "_translate_text_batch", lambda blocks, *_args, **_kwargs: (
        {blocks[0][0]: "Bloque traducido"} if blocks[0][0] == 0 else {}
    ))
    report = {}
    with pytest.raises(RuntimeError, match="33%.*minimum 50%"):
        ai_engine.translate_pdf_layout(source, output, target_lang="es", report=report)

    assert report["blocks_seen"] == 3
    assert report["blocks_translated"] == 1
    expected_fraction = len("First source block") / sum(map(len, ("First source block", "Second source block", "Third source block")))
    assert report["translated_fraction"] == pytest.approx(expected_fraction)
    assert report["source_characters_translated"] == len("First source block")
    assert report["translation_status"] == "failed"
    assert not output.exists()
    status, detail, _headers = server.translation_failure_response(
        RuntimeError("Only 33% of text blocks were translated (minimum 50%). No translated PDF was produced.")
    )
    assert status == 422 and "33%" in detail


def test_translation_rejects_one_large_block_when_other_blocks_are_preserved(tmp_path, monkeypatch):
    source = tmp_path / "imbalanced-coverage.pdf"
    output = tmp_path / "imbalanced-translation.pdf"
    long_source = "This source paragraph contains important document content. " * 15
    long_translation = "Este párrafo contiene contenido importante del documento. " * 15
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_textbox(fitz.Rect(72, 72, 540, 270), long_source, fontsize=10)
        for y, value in [(340, "Alpha"), (390, "Bravo"), (440, "Charlie")]:
            page.insert_text((72, y), value)
        pdf.save(source)

    monkeypatch.setattr(ai_engine, "TRANSLATION_BATCH_SIZE", 20)
    monkeypatch.setattr(ai_engine, "TRANSLATION_MAX_PARALLEL_BATCHES", 1)
    monkeypatch.setattr(ai_engine, "_translation_chunks", lambda value: [value])
    monkeypatch.setattr(ai_engine, "_translate_text_batch", lambda batch, *_args, **_kwargs: (
        {batch[0][0]: long_translation} if batch and batch[0][0] == 0 else {}
    ))
    report = {}
    with pytest.raises(RuntimeError, match=r"Only 25% of text blocks.*minimum 50%"):
        ai_engine.translate_pdf_layout(source, output, target_lang="es", report=report)

    assert report["translated_fraction"] > 0.5
    assert report["translated_block_fraction"] == pytest.approx(0.25)
    assert report["blocks_translated"] == 1
    assert report["blocks_seen"] == 4
    assert report["translation_status"] == "failed"
    assert not output.exists()


def test_translation_that_only_echoes_source_fails_with_content_change_percentage(tmp_path, monkeypatch):
    source = tmp_path / "provider-echo.pdf"
    output = tmp_path / "echo-translation.pdf"
    source_text = "The planned programme covers planning phases and operational workstreams."
    with fitz.open() as pdf:
        pdf.new_page().insert_text((72, 72), source_text)
        pdf.save(source)

    monkeypatch.setattr(ai_engine, "TRANSLATION_BATCH_SIZE", 1)
    monkeypatch.setattr(ai_engine, "TRANSLATION_MAX_PARALLEL_BATCHES", 1)
    monkeypatch.setattr(ai_engine, "_translate_text_batch", lambda blocks, *_args, **_kwargs: {blocks[0][0]: source_text})
    report = {}
    with pytest.raises(RuntimeError, match=r"Only 0% of source text changed.*minimum 10%"):
        ai_engine.translate_pdf_layout(source, output, target_lang="es", report=report)

    assert report["translated_fraction"] == 1.0
    assert report["translation_change_fraction"] == 0.0
    assert report["translation_status"] == "failed"
    assert not output.exists()
    status, detail, _headers = server.translation_failure_response(
        RuntimeError("Only 0% of source text changed during translation (minimum 10%). No translated PDF was produced.")
    )
    assert status == 422 and "0%" in detail and "minimum 10%" in detail


def test_offline_brief_has_one_heading_and_never_claims_document_wide_absence(tmp_path, monkeypatch):
    source = tmp_path / "twenty-four-pages.pdf"
    with fitz.open() as pdf:
        for number in range(1, 25):
            page = pdf.new_page()
            page.insert_text((72, 72), f"Attribution notice. Page {number} substantive project information.")
            if number == 24:
                page.insert_text((72, 130), "Cancellation deadline 15 December 2026 no-spend limit 900000.")
        pdf.save(source)

    monkeypatch.setattr(ai_engine, "call_llm", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("controlled provider unavailable")))
    summary = ai_engine.summarize_pdf(source)
    assert summary.count("### Executive Summary") == 1
    assert "no additional deadlines are present" not in summary.lower()
    assert "attribution notice" not in summary.lower()
    assert "Cancellation deadline 15 December 2026 no-spend limit 900000" in summary
    assert "pages analyzed" in summary


def test_executive_brief_rejects_duplicate_provider_summaries_and_invented_currency(tmp_path, monkeypatch):
    source = tmp_path / "unitless-report.pdf"
    with fitz.open() as pdf:
        for number in range(1, 25):
            page = pdf.new_page()
            page.insert_text((72, 72), f"Page {number}: unitless amount 42000 and limit 900000 are recorded.")
        pdf[23].insert_text((72, 130), "Cancellation deadline 15 December 2026.")
        pdf.save(source)

    provider_output = (
        "### Executive Summary\nNo additional deadlines are present. [Page 1]\n\n"
        "### Executive Summary\nThe budget is $42,000 and the cap is $900,000. [Page 24]"
    )
    monkeypatch.setattr(ai_engine, "call_llm", lambda *_args, **_kwargs: provider_output)
    summary = ai_engine.summarize_pdf(source)
    assert summary.count("### Executive Summary") == 1
    assert "$42,000" not in summary and "$900,000" not in summary
    assert "no additional deadlines are present" not in summary.lower()
    assert "900000" in summary


def test_executive_brief_marks_single_provider_currency_invention_unspecified(tmp_path, monkeypatch):
    source = tmp_path / "unitless-one-page.pdf"
    with fitz.open() as pdf:
        pdf.new_page().insert_text((72, 72), "The unitless amount 42000 appears in the source report.")
        pdf.save(source)

    monkeypatch.setattr(ai_engine, "call_llm", lambda *_args, **_kwargs: "### Executive Summary\nThe amount is $42,000. [Page 1]")
    summary = ai_engine.summarize_pdf(source)
    assert "42,000 (currency unspecified)" in summary
    assert "$42,000" not in summary


def test_executive_brief_checks_currency_per_amount_and_drops_unsupported_absence(tmp_path, monkeypatch):
    source = tmp_path / "mixed-currency-support.pdf"
    with fitz.open() as pdf:
        pdf.new_page().insert_text(
            (72, 72),
            "Budget 42000 has no currency; separately listed USD 5000 is the fee. No further deadlines are identified."
        )
        pdf.save(source)

    provider_summary = (
        "### Executive Summary\n"
        "No further deadlines are identified. No additional dates are present. [Page 1]\n"
        "The budget is $42,000 and service fee is USD 5,000. [Page 1]"
    )
    monkeypatch.setattr(ai_engine, "call_llm", lambda *_args, **_kwargs: provider_summary)
    summary = ai_engine.summarize_pdf(source)
    assert "42,000 (currency unspecified)" in summary
    assert "USD 5,000" in summary
    assert "no additional dates are present" not in summary.lower()
    assert "No further deadlines are identified." in summary


def test_false_author_claim_is_corrected_when_metadata_and_text_have_no_author(tmp_path):
    source = tmp_path / "unattributed-report.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "A technical note about processing reliability.")
        pdf.save(source)

    answer = ai_engine.chat_with_pdf(source, "Was this written by Albert Einstein?")
    assert answer["retrieval_method"] == "Verified PDF Metadata and Local Fact Check"
    assert "can't verify" in answer["answer"].lower()
    assert "authorship" in answer["answer"].lower()
    assert answer["citations"] == []


def test_annotate_and_hardened_redaction_match_the_same_keyword(tmp_path):
    source = tmp_path / "shared-search.pdf"
    with fitz.open() as pdf:
        pdf.new_page().insert_text((72, 72), "Important review note for cross-tool search verification.")
        pdf.save(source)

    client = TestClient(server.app)
    with source.open("rb") as source_file:
        annotated_response = client.post(
            "/api/pdf/annotate",
            data={"annotations": '[{"type":"highlight","page":1,"text":"Important"}]'},
            files={"file": (source.name, source_file, "application/pdf")},
        )
    with source.open("rb") as source_file:
        redacted_response = client.post(
            "/api/studio/security/redact",
            data={"redactions": '[{"page":0,"text":"Important"}]'},
            files={"file": (source.name, source_file, "application/pdf")},
        )

    assert annotated_response.status_code == redacted_response.status_code == 200
    annotated = fitz.open(stream=annotated_response.content, filetype="pdf")
    redacted = fitz.open(stream=redacted_response.content, filetype="pdf")
    try:
        assert len(list(annotated[0].annots() or [])) == 1
        assert "Important" in annotated[0].get_text()
        assert "Important" not in redacted[0].get_text()
        assert "review note" in redacted[0].get_text()
    finally:
        annotated.close()
        redacted.close()


def test_offline_chat_summary_emits_one_page_citation_per_sampled_excerpt():
    answer = ai_engine._offline_rag_fallback(
        "Answer using document excerpts.",
        "DOCUMENT EXCERPTS:\n[Page 1]:\nProject result total $42.\n\nUSER QUESTION: Summarize the main points in the uploaded PDF.",
    )
    normalized, citations = ai_engine.align_answer_citations(answer, {1})
    assert normalized.count("[Page 1]") == 1
    assert citations == [1]


@pytest.mark.parametrize("provider", ["openai_compatible", "anthropic", "gemini"])
def test_executive_brief_provider_request_uses_zero_temperature(provider, monkeypatch):
    import json

    provider_responses = {
        "openai_compatible": {"choices": [{"message": {"content": "Brief [Page 1]"}}]},
        "anthropic": {"content": [{"type": "text", "text": "Brief [Page 1]"}]},
        "gemini": {"candidates": [{"content": {"parts": [{"text": "Brief [Page 1]"}]}}]},
    }
    captured = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(provider_responses[provider]).encode()

    def fake_open_request(request, **_kwargs):
        captured["payload"] = json.loads(request.data)
        return FakeResponse()

    credentials = {"provider": provider, "model": "controlled-model", "api_key": "test-key",
                   "base_url": "https://provider.example.test/v1"}
    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setattr(ai_engine, "_runtime_ai_config", lambda: dict(credentials))
    monkeypatch.setattr(ai_engine, "_open_ai_request", fake_open_request)

    assert ai_engine.call_llm("system", "document", temperature=0.0) == "Brief [Page 1]"
    payload = captured["payload"]
    actual = payload.get("generationConfig", {}).get("temperature") if provider == "gemini" else payload.get("temperature")
    assert actual == 0.0


def test_pdf_to_word_sanitizes_xml_controls_and_preserves_unicode(tmp_path):
    source = tmp_path / "unicode-report.pdf"
    output = tmp_path / "unicode-report.docx"
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "Valid Unicode: café")
        pdf.save(source)

    assert converters._sanitize_xml_text("before\x00\x01 नमस्ते 😀 after") == "before नमस्ते 😀 after"
    converters.pdf_to_word(source, output)
    with ZipFile(output) as archive:
        document_xml = archive.read("word/document.xml")
        ElementTree.fromstring(document_xml)
        text = document_xml.decode("utf-8")
        assert "café" in text


def test_rotate_landing_copy_matches_whole_document_behavior():
    rotate = server.SEO_CATALOG["rotate"]
    copy = " ".join([rotate["title"], rotate["description"], rotate["heading"], rotate["intro"], *rotate["how_to"],
                     *(answer for _question, answer in rotate["faqs"])])
    assert "whole document" in copy.lower() or "entire pdf" in copy.lower()
    assert "page-by-page rotation workflow" not in copy.lower()
    assert "Choose a single thumbnail" not in copy


def test_metadata_edit_preserves_unedited_provenance_and_dates(tmp_path):
    source, output = tmp_path / "metadata-source.pdf", tmp_path / "metadata-output.pdf"
    with fitz.open() as pdf:
        pdf.new_page().insert_text((72, 72), "Metadata preservation fixture")
        pdf.set_metadata({"title": "Old title", "author": "Original author", "subject": "Original subject",
                          "creator": "LaTeX with hyperref", "producer": "Original Producer",
                          "creationDate": "D:20200102030405Z", "modDate": "D:20210304050607Z"})
        pdf.save(source)
    outdir = tmp_path / "second"
    outdir.mkdir()
    result = server.process("metadata", [source], {"title": "Updated title"}, outdir)
    metadata = PdfReader(str(result)).metadata
    assert metadata.title == "Updated title"
    assert metadata.author == "Original author"
    assert metadata.creator == "LaTeX with hyperref"
    assert metadata.producer == "Original Producer"
    assert metadata.raw_get("/CreationDate") == "D:20200102030405Z"
    assert metadata.raw_get("/ModDate") == "D:20210304050607Z"


def test_metadata_job_exposes_output_metadata_without_consuming_guest_download(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "DATABASE", tmp_path / "metadata-export.sqlite")
    monkeypatch.setattr(server, "JOBS", tmp_path / "jobs")
    persistence.init_db()
    job_id, guest_token = persistence.create_job("metadata", None, 3600)
    job_dir = server.JOBS / job_id
    job_dir.mkdir(parents=True)
    output = job_dir / "metadata-result.pdf"
    with fitz.open() as pdf:
        pdf.new_page().insert_text((72, 72), "Metadata JSON export result")
        pdf.set_metadata({"title": "Updated title", "author": "Updated author", "subject": "Updated subject",
                          "creator": "Original creator", "producer": "Original producer"})
        pdf.save(output)
    persistence.update_job(job_id, status="completed", progress=100, output_name=output.name, output_size=output.stat().st_size)

    client = TestClient(server.app)
    cookies = {f"guest_job_{job_id}": guest_token}
    status = client.get(f"/api/jobs/{job_id}", cookies=cookies)
    assert status.status_code == 200
    assert status.json()["output_metadata"] == {
        "title": "Updated title", "author": "Updated author", "subject": "Updated subject",
        "keywords": "", "creator": "Original creator", "producer": "Original producer",
        "creation_date": "", "modification_date": "", "page_count": 1,
    }

    # The metadata view/export is sidecar data and must not spend the guest's
    # one-time PDF download capability.
    download = client.get(f"/api/jobs/{job_id}/download", cookies=cookies)
    assert download.status_code == 200
    assert PdfReader(io.BytesIO(download.content)).metadata.title == "Updated title"
    assert client.get(f"/api/jobs/{job_id}/download", cookies=cookies).status_code == 404


def test_app_job_idempotency_replays_guest_job_and_rejects_other_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "DATABASE", tmp_path / "idempotent-jobs.sqlite")
    monkeypatch.setattr(server, "JOBS", tmp_path / "jobs")
    monkeypatch.setattr(server.executor, "submit", lambda *args, **kwargs: None)
    server.JOBS.mkdir()
    persistence.init_db()
    client = TestClient(server.app)
    key = "v23-retry-test-key-00000000000001"
    with fitz.open() as source:
        source.new_page().insert_text((72, 72), "IDEMPOTENCY SOURCE MARKER")
        pdf_bytes = source.tobytes()

    def submit(target, request_key):
        return target.post(
            "/api/jobs", headers={"Idempotency-Key": request_key},
            data={"operation": "merge", "options": "{}"},
            files=[("files", ("input.pdf", pdf_bytes, "application/pdf"))],
        )

    first = submit(client, key)
    assert first.status_code == 202, first.text
    first_id = first.json()["job_id"]
    assert first.cookies.get(f"guest_job_{first_id}")

    replay = submit(client, key)
    assert replay.status_code == 200, replay.text
    assert replay.json()["job_id"] == first_id
    assert replay.json()["idempotent"] is True
    assert replay.cookies.get(f"guest_job_{first_id}") == first.cookies.get(f"guest_job_{first_id}")

    other_guest = TestClient(server.app, client=("10.10.10.10", 43210))
    conflict = submit(other_guest, key)
    assert conflict.status_code == 409
    with persistence.closing(persistence.connect()) as connection:
        assert connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
        row = connection.execute("SELECT key_hash FROM app_job_submission_keys").fetchone()
        assert row and row["key_hash"] != key and len(row["key_hash"]) == 64


def test_pdf_to_markdown_omits_job_name_and_restores_span_word_gaps(tmp_path):
    source, output = tmp_path / "a5e7074e4bb844cdb8a39a50783e06b5_browser-download.pdf", tmp_path / "out.md"
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "performing", fontsize=11)
        page.insert_text((126, 72), "models", fontsize=11)
        pdf.set_metadata({"title": ""})
        pdf.save(source)
    converters.pdf_to_markdown(source, output)
    markdown = output.read_text(encoding="utf-8")
    assert "a5e7074e4bb844cdb8a39a50783e06b5" not in markdown
    assert "performing models" in markdown


def test_pdf_to_markdown_uses_original_upload_name_and_keeps_body_text_out_of_headings(tmp_path):
    source = tmp_path / "random-job-id_8-c5-report.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "Report body sentence one.", fontsize=12)
        page.insert_text((72, 96), "Report body sentence two.", fontsize=12)
        page.insert_text((72, 140), "Findings", fontsize=14)
        pdf.set_metadata({"title": ""})
        pdf.save(source)

    result = server.process(
        "pdf_to_markdown", [source], {"_original_filename": "Annual Report.pdf"}, tmp_path
    )
    markdown = result.read_text(encoding="utf-8")
    assert markdown.startswith("# Annual Report\n")
    assert "random-job-id" not in markdown
    assert "## Report body sentence" not in markdown
    assert "## Findings" in markdown


def test_admin_analytics_counts_every_plan_and_uses_utc_calendar_day(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "DATABASE", str(tmp_path / "analytics.sqlite3"))
    persistence.init_db()
    tiers = ("free", "exam_pass", "student_pro", "pro", "developer")
    for index, tier in enumerate(tiers):
        email = f"analytics-{index}@example.invalid"
        user_id = persistence.create_user(email, "strong-test-password")
        persistence.set_user_tier(user_id, tier)
    now = time.time()
    midnight_utc = int(now // 86400) * 86400
    with persistence.connect() as connection:
        for index, created_at in enumerate((midnight_utc - 60, midnight_utc + 60)):
            connection.execute(
                "INSERT INTO jobs (id, user_id, guest_token, operation, status, created_at, expires_at) "
                "VALUES (?, NULL, NULL, 'merge', 'completed', ?, ?)",
                (f"analytics-job-{index}", created_at, now + 3600),
            )
        connection.commit()

    metrics = persistence.admin_get_extended_analytics()
    assert metrics["total_users"] == sum(metrics["tier_breakdown"].values()) == len(tiers)
    assert metrics["tier_breakdown"] == {tier: 1 for tier in tiers}
    assert metrics["total_jobs"] == 2
    assert metrics["jobs_today"] == 1


def test_ai_citations_collapse_consecutive_pages_and_bound_scattered_labels():
    aligned, pages = ai_engine.align_answer_citations(
        "The repeated claim is supported [Pages 1, 2, 3, 4, 5, 6].", set(range(1, 7))
    )
    assert "[Pages 1-6]" in aligned
    assert pages == list(range(1, 7))

    scattered = list(range(1, 200, 2))
    aligned, pages = ai_engine.align_answer_citations(
        "Many distinct references [Pages " + ", ".join(map(str, scattered)) + "].", scattered
    )
    citation = re.search(r"\[Pages [^\]]+\]", aligned).group(0)
    assert len(citation) <= 120
    assert "more pages" in citation
    assert pages == scattered


def test_resize_photo_fits_requested_canvas_without_distortion(tmp_path):
    source, output = tmp_path / "wide.png", tmp_path / "resized.png"
    image = Image.new("RGB", (200, 100), "red")
    image.save(source)
    result = converters.resize_photo(source, output, width=100, height=100)
    with Image.open(result) as resized:
        assert resized.size == (100, 100)
        assert resized.getpixel((50, 10)) == (255, 255, 255)
        assert resized.getpixel((50, 50))[0] > 240


def test_smart_metadata_skips_attribution_and_uses_prominent_title(tmp_path, monkeypatch):
    source = tmp_path / "attribution.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 50), "Provided proper attribution is provided, Google hereby grants permission to use this work.", fontsize=8)
        page.insert_text((180, 150), "Attention Is All You Need", fontsize=22)
        page.insert_text((72, 220), "Abstract", fontsize=14)
        page.insert_text((72, 250), "A paper about attention models.", fontsize=10)
        pdf.save(source)
    monkeypatch.setattr(ai_engine, "_extract_metadata_with_agentrouter", lambda *_args: None)
    metadata = ai_engine.extract_metadata_entities(source, "general")
    assert metadata["general_data"]["title"] == "Attention Is All You Need"


def test_compression_missed_target_warning_is_persisted(tmp_path, monkeypatch):
    source = tmp_path / "input.pdf"
    outdir = tmp_path / "job"
    outdir.mkdir()
    with fitz.open() as pdf:
        pdf.new_page()
        pdf.save(source)

    def controlled_compression(_fn, _source, output, **_kwargs):
        with fitz.open() as pdf:
            pdf.new_page().insert_text((72, 72), "Compressed result")
            pdf.save(output)
        return {"content_preserved_original": False, "target_achieved": False,
                "note": "Compressed to 1,790.0 KB; the requested target could not be reached while preserving document content."}

    monkeypatch.setattr(server, "run_converter_with_timeout", controlled_compression)
    server.process("compress", [source], {"preset": "under_100kb"}, outdir)
    warning = (outdir / ".job-warning").read_text(encoding="utf-8")
    assert "1,790.0 KB" in warning and "target could not be reached" in warning


def test_compress_pdf_downsamples_soft_mask_images_without_losing_transparency(tmp_path):
    source = tmp_path / "soft-mask-source.pdf"
    output = tmp_path / "soft-mask-compressed.pdf"
    size = (1400, 1000)
    noise = Image.effect_noise(size, 70).convert("RGB")
    alpha = Image.linear_gradient("L").resize(size)
    rgba = noise.convert("RGBA")
    rgba.putalpha(alpha)
    image_bytes = io.BytesIO()
    rgba.save(image_bytes, format="PNG")
    with fitz.open() as document:
        page = document.new_page(width=700, height=500)
        page.insert_text((40, 40), "Soft mask preservation marker")
        page.insert_image(fitz.Rect(20, 60, 680, 480), stream=image_bytes.getvalue())
        document.save(source)

    result = converters.compress_pdf(source, output, preset="100kb")
    with fitz.open(source) as original, fitz.open(output) as compressed:
        assert compressed.page_count == original.page_count == 1
        assert compressed[0].get_text() == original[0].get_text()
        original_images = original[0].get_images(full=True)
        compressed_images = compressed[0].get_images(full=True)
        assert original_images and original_images[0][1]
        assert compressed_images and compressed_images[0][1]
        image_xref, mask_xref = compressed_images[0][:2]
        pixmap = fitz.Pixmap(compressed, image_xref)
        mask = fitz.Pixmap(compressed, mask_xref)
        assert pixmap.width < size[0]
        assert mask.width == pixmap.width
        source_pix = original[0].get_pixmap(matrix=fitz.Matrix(0.5, 0.5), alpha=False)
        output_pix = compressed[0].get_pixmap(matrix=fitz.Matrix(0.5, 0.5), alpha=False)
        source_image = Image.frombytes("RGB", (source_pix.width, source_pix.height), source_pix.samples)
        output_image = Image.frombytes("RGB", (output_pix.width, output_pix.height), output_pix.samples)
        assert sum(ImageStat.Stat(ImageChops.difference(source_image, output_image)).mean) / 3 < 3
    assert output.stat().st_size < source.stat().st_size
    assert result["validation_passed"] is True


def test_launch_gating_legal_and_support_routes_are_present_and_honest():
    client = TestClient(server.app)
    privacy = client.get("/privacy")
    assert privacy.status_code == 200
    assert "Draft — owner review required" in privacy.text
    assert "AI provider configured for this deployment" in privacy.text
    assert "At-rest encryption" in privacy.text
    assert "never used to train" not in privacy.text.lower()
    for path, marker in (("/refund", "DRAFT"), ("/contact", "response expectation"), ("/status", "No live uptime monitor")):
        response = client.get(path)
        assert response.status_code == 200
        assert marker.lower() in response.text.lower()
    tool = client.get("/merge-pdf")
    assert "/pricing#pricing-limits-table" in tool.text


def test_seo_and_navigation_copy_matches_pdf_tool_capabilities():
    client = TestClient(server.app)
    response = client.get("/api/seo/pdf_to_jpg")
    assert response.status_code == 200
    selected_pages_faq = next(answer for question, answer in response.json()["faqs"]
                              if question == "Can I convert only selected PDF pages?")
    assert "currently exports every page" in selected_pages_faq
    html = client.get("/").text
    assert 'href="/history">Temporary results</a>' in html
    assert 'class="theme-choice-card active" id="theme-light-btn"' in html
    assert 'class="theme-choice-card" id="theme-dark-btn"' in html
    faq = client.get("/faq").text
    assert faq.count("<details>") == 4
    history = client.get("/history").text
    assert "Temporary results — no saved history" in history
    assert "does not keep a job or download history list" in history


def test_pdf_to_markdown_uses_a_bounded_long_document_budget(tmp_path, monkeypatch):
    source = tmp_path / "markdown-source.pdf"
    output_dir = tmp_path / "markdown-job"
    output_dir.mkdir()
    with fitz.open() as pdf:
        pdf.new_page().insert_text((72, 72), "Markdown timeout budget regression.")
        pdf.save(source)
    captured = {}

    def controlled_runner(function, *args, **kwargs):
        captured.update(kwargs)
        runner_options = {key: kwargs.pop(key) for key in ("timeout_seconds", "tool_name", "source_path", "output_path", "retry_hint")}
        captured.update(runner_options)
        return function(*args, **kwargs)

    monkeypatch.setattr(server, "run_converter_with_timeout", controlled_runner)
    result = server.process("pdf_to_markdown", [source], {}, output_dir)
    assert result.suffix == ".md" and result.is_file()
    assert captured["timeout_seconds"] == server.PDF_TO_MARKDOWN_TIMEOUT_SECONDS == 480.0
    assert captured["tool_name"] == "PDF to Markdown"
    assert "split it into smaller page ranges" in captured["retry_hint"]


def test_completed_pdf_job_status_includes_output_page_count(tmp_path, monkeypatch):
    job_id = "page-count-result-card"
    job_dir = tmp_path / job_id
    job_dir.mkdir()
    output_path = job_dir / "merged.pdf"
    with fitz.open() as pdf:
        for number in range(1, 4):
            pdf.new_page().insert_text((72, 72), f"Page count marker {number}")
        pdf.save(output_path)
    monkeypatch.setattr(server, "JOBS", tmp_path)
    monkeypatch.setattr(server, "get_job", lambda *args, **kwargs: {
        "id": job_id, "status": "completed", "operation": "merge",
        "output_name": output_path.name, "output_size": output_path.stat().st_size,
    })

    response = TestClient(server.app).get(f"/api/jobs/{job_id}")

    assert response.status_code == 200
    assert response.json()["page_count"] == 3


def test_result_card_shows_page_count_for_server_and_local_pdf_results():
    app_js = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    assert "job.page_count" in app_js
    assert "countPdfPagesInBlob(blob)" in app_js
    assert "Page count unavailable" in app_js


def test_organizer_order_cards_reserve_room_for_labels_and_controls():
    css = (Path(__file__).resolve().parents[1] / "web" / "assets" / "styles.css").read_text(encoding="utf-8")
    assert "grid-template-columns: repeat(auto-fill, minmax(140px, 1fr))" in css
    assert ".organizer-order-card strong { min-width: 0; color: var(--text-main); font-size: 12px; white-space: nowrap; }" in css
    assert ".organizer-order-card strong { white-space: normal; }" in css


def test_sidebar_suite_map_matches_the_tool_desk_groups():
    app_js = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    html = (Path(__file__).resolve().parents[1] / "web" / "index.html").read_text(encoding="utf-8")
    assert "'Optimize': ['compress', 'repair', 'ocr']" in app_js
    assert "'Security': ['sign', 'protect', 'unlock', 'redact', 'forms', 'mask_aadhaar']" in app_js
    assert "'AI': ['ai_chat', 'ai_extract', 'summarize', 'translate']" in app_js
    assert 'data-category="AI"' in html and 'data-category="Security"' in html and 'data-category="Optimize"' in html
    assert "AI &amp; Security" not in html and 'nav-cat-badge">13<' not in html


def test_studio_page_size_labels_use_pdfjs_visible_page_dimensions():
    app_js = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    assert "basePage.getViewport({ scale: 1 })" in app_js
    assert "slot.dataset.pdfPageWidthPt" in app_js and "slot.dataset.pdfPageHeightPt" in app_js
    assert "slot.setAttribute('aria-label', `Page ${target}, ${pageSizeLabel}`)" in app_js
    assert "slot.title = pageSizeLabel" in app_js


def test_studio_bulk_page_stack_uses_one_layout_measurement_and_fragment():
    app_js = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    slot_builder = app_js.split("function createStudioPageSlot(", 1)[1].split("function prepareStudioPageStack(", 1)[0]
    stack_builder = app_js.split("function prepareStudioPageStack(", 1)[1].split("function studioPageSlot(", 1)[0]
    assert "parent = $('#studio-page-stack')" in slot_builder
    assert "parent?.appendChild(slot)" in slot_builder
    assert "document.createDocumentFragment()" in stack_builder
    assert "createStudioPageSlot(pageNum, initialWidth, slots)" in stack_builder
    assert "const batchSize = 16" in stack_builder
    assert "pageNum % batchSize === 0" in stack_builder
    assert "await new Promise(resolve => setTimeout(resolve, 0))" in stack_builder
    assert "loadEpoch !== studioWorkspaceEpoch" in stack_builder
    assert "stack.replaceChildren(slots)" in stack_builder
    assert "slots.appendChild(slot)" not in stack_builder


def test_studio_organizer_thumbnail_cards_are_time_sliced_and_stale_safe():
    root = Path(__file__).resolve().parents[1]
    organizer_js = (root / "web" / "assets" / "page_organizer.js").read_text(encoding="utf-8")
    render = organizer_js.split("async renderThumbnails()", 1)[1].split("async _renderCardCanvas", 1)[0]
    assert "thumbnailRenderEpoch" in render
    assert "document.createDocumentFragment()" in render
    assert "batchDeadline = performance.now() + 40" in render
    assert "performance.now() >= batchDeadline" in render
    assert "window.scheduler?.yield" in render
    assert "renderEpoch !== this.thumbnailRenderEpoch" in render


def test_studio_thumbnail_observer_does_not_prefetch_offscreen_pages():
    root = Path(__file__).resolve().parents[1]
    organizer_js = (root / "web" / "assets" / "page_organizer.js").read_text(encoding="utf-8")
    observer = organizer_js.split("_initIntersectionObserver()", 1)[1].split("loadDocument(", 1)[0]
    assert "root: document.getElementById('studio-thumbnails-container')" in observer
    assert "rootMargin: '0px 0px'" in observer
    assert "if (entry.isIntersecting)" in observer
    assert "this._renderCardCanvas(card, pageNum)" in observer


def test_studio_thumbnail_blob_cache_is_async_and_stale_document_safe():
    root = Path(__file__).resolve().parents[1]
    organizer_js = (root / "web" / "assets" / "page_organizer.js").read_text(encoding="utf-8")
    renderer = organizer_js.split("async _renderCardCanvas", 1)[1].split("_updateCardStates", 1)[0]
    cache_cleanup = organizer_js.split("_clearThumbnailCache()", 1)[1].split("loadDocument(", 1)[0]
    assert "canvas.toBlob(resolve, 'image/jpeg', 0.85)" in renderer
    assert "URL.createObjectURL(blob)" in renderer
    assert "sourceDoc !== this.pdfDoc" in renderer
    assert "renderEpoch !== this.thumbnailRenderEpoch" in renderer
    assert "!card.isConnected" in renderer
    assert "URL.revokeObjectURL(url)" in cache_cleanup
    assert "this.state.thumbnailCache.clear()" in cache_cleanup


def test_studio_mobile_page_observer_does_not_prefetch_full_viewports():
    app_js = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    observer = app_js.split("function setupStudioPageObserver()", 1)[1].split("function getStudioPageScale", 1)[0]
    assert "const isMobileViewport = window.matchMedia('(max-width: 900px)').matches" in observer
    assert "root: isMobileViewport ? null : area" in observer
    assert "rootMargin: isMobileViewport ? '0px 0px' : '120% 0px'" in observer


def test_studio_canvas_pruning_tracks_rendered_pages_without_full_dom_scan():
    app_js = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    prune = app_js.split("function pruneStudioPageCanvases(", 1)[1].split("function alignStudioPageInViewport(", 1)[0]
    assert "renderedPages: new Set()" in app_js
    assert "state.studio.renderedPages.add(target)" in app_js
    assert "for (const pageNum of state.studio.renderedPages)" in prune
    assert "querySelectorAll" not in prune
    assert "state.studio.renderedPages.delete(pageNum)" in prune
    assert "state.studio.renderedPages.clear()" in app_js


def test_workspace_switch_avoids_redundant_scroll_to_calls():
    app_js = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    switch = app_js.split("function switchWorkspaceView(", 1)[1].split("\nfunction ", 1)[0]
    assert "if (mainArea && mainArea.scrollTop > 0) mainArea.scrollTo" in switch
    assert "if ((window.scrollY || document.documentElement.scrollTop) > 0) window.scrollTo" in switch
    assert switch.count("window.scrollTo") == 1


def test_studio_toasts_avoid_document_overlap_and_announce_accessibly():
    app_js = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    toast = app_js.split("function showToast(", 1)[1].split("\nfunction ", 1)[0]
    assert "toast.setAttribute('role', type === 'error' ? 'alert' : 'status')" in toast
    assert "toast.setAttribute('aria-live', type === 'error' ? 'assertive' : 'polite')" in toast
    assert "toast.setAttribute('aria-atomic', 'true')" in toast
    assert "const pageSheet = canvas?.closest('.studio-page-sheet') || canvas" in toast
    assert "const pageRect = pageSheet?.getBoundingClientRect() || canvasRect" in toast
    assert "const pageVisible = pageRect && pageRect.width > 0 && pageRect.height > 0" in toast
    assert "const clearGapTop = pageVisible ? pageRect.bottom + 12 : toolbarBottom + 8" in toast
    assert "clearGapTop + toastHeight <= bottomBoundary - 8" in toast
    assert "if (pageVisible && !gapPlacementFits)" in toast
    assert "const leftGap = pageRect.left - 8" in toast
    assert "window.innerWidth > 900 && rightGap >= toast.getBoundingClientRect().width + 8" in toast
    assert "window.innerWidth > 900 && leftGap >= toast.getBoundingClientRect().width + 8" in toast
    assert "toast.classList.add('toast-visually-hidden')" in toast
    assert "#studio-mobile-dock" in toast
    assert "never cover a visible PDF or the" in toast


def test_compare_supports_browser_local_selectable_text_diff():
    app_js = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    operations = app_js.split("const CLIENT_SIDE_SUPPORTED_OPERATIONS", 1)[1].split(";", 1)[0]
    compare = app_js.split("if (state.operation === 'compare')", 1)[1].split("if (state.operation === 'pdf_to_text')", 1)[0]
    assert "'compare'" in operations
    assert "diffPdfTextLines(left, right)" in compare
    assert "Selectable text comparison" in compare
    assert "page layout, images, and scanned text are not compared" in compare
    assert "2_000_000" in app_js and "20,000 combined text lines" in app_js
    assert "workLimit = 250_000" in app_js and "if (++work > workLimit)" in app_js
    assert "'/assets/app.js?v=154'" in (Path(__file__).resolve().parents[1] / "web" / "assets" / "service-worker.js").read_text(encoding="utf-8")


def test_pdf_to_markdown_browser_path_discloses_its_formatting_limits():
    root = Path(__file__).resolve().parents[1]
    app_js = (root / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    operations = app_js.split("const CLIENT_SIDE_SUPPORTED_OPERATIONS", 1)[1].split(";", 1)[0]
    local_path = app_js.split("if (state.operation === 'pdf_to_markdown')", 1)[1].split("if (state.operation === 'pdf_to_text')", 1)[0]
    index_html = (root / "web" / "index.html").read_text(encoding="utf-8")
    assert "'pdf_to_markdown'" in operations
    assert "extractPdfMarkdown(file" in local_path
    assert "text/markdown;charset=utf-8" in local_path
    assert "tables, math layout, and scanned text are not reconstructed" in local_path
    assert "Browser mode extracts selectable text and basic heading/list formatting" in app_js
    assert "up to 500 pages" in app_js and "2_000_000" in app_js and "20_000" in app_js
    assert "PDF-to-Markdown (basic)" in index_html
    assert 'src="/assets/app.js?v=154"' in index_html


def test_scan_to_pdf_local_path_declares_enhancement_limit_and_size_safety():
    root = Path(__file__).resolve().parents[1]
    app_js = (root / "web/assets/app.js").read_text(encoding="utf-8")
    index_html = (root / "web/index.html").read_text(encoding="utf-8")
    worker = (root / "web/assets/service-worker.js").read_text(encoding="utf-8")
    assert "'scan_pdf'" in app_js.split("const CLIENT_SIDE_SUPPORTED_OPERATIONS", 1)[1].split(";", 1)[0]
    assert "without automatic contrast or sharpness enhancement" in app_js
    assert "switch browser processing off to use enhanced server processing" in app_js
    assert "totalSourcePixels > 100_000_000" in app_js
    assert "pageWidth = image.naturalWidth * 72 / 200" in app_js
    assert 'src="/assets/app.js?v=154"' in index_html
    assert "paperplane-shell-v95" in worker
    assert "'/assets/styles.css?v=61'" in worker
    assert 'href="/assets/styles.css?v=61"' in index_html
    assert "'/assets/styles.css?v=51'" not in worker


def test_jpg_to_pdf_local_path_preserves_aspect_and_bounds_canvas_work():
    app_js = (Path(__file__).resolve().parents[1] / "web/assets/app.js").read_text(encoding="utf-8")
    operations = app_js.split("const CLIENT_SIDE_SUPPORTED_OPERATIONS", 1)[1].split(";", 1)[0]
    local_image_pdf = app_js.split("if (state.operation === 'jpg_to_pdf')", 1)[1].split("if (state.operation === 'photo_compress')", 1)[0]
    assert "'jpg_to_pdf'" in operations
    assert "const fitScale = Math.min(width / image.naturalWidth, height / image.naturalHeight)" in local_image_pdf
    assert "Math.min(8192 / image.naturalWidth, 8192 / image.naturalHeight" in local_image_pdf
    assert "totalSourcePixels > 100_000_000" in local_image_pdf
    assert "local_processing: true" in local_image_pdf


def test_grayscale_pdf_supports_bounded_browser_local_rendering_and_preserves_gray_source():
    root = Path(__file__).resolve().parents[1]
    app_js = (root / "web/assets/app.js").read_text(encoding="utf-8")
    worker = (root / "web/assets/local_pdf_worker.js").read_text(encoding="utf-8")
    runtime = (root / "web/assets/pdf_runtime.js").read_text(encoding="utf-8")
    index_html = (root / "web/index.html").read_text(encoding="utf-8")
    service_worker = (root / "web/assets/service-worker.js").read_text(encoding="utf-8")
    supported = app_js.split("const CLIENT_SIDE_SUPPORTED_OPERATIONS", 1)[1].split(";", 1)[0]
    grayscale = app_js.split("async function processClientSide", 1)[1].split("if (state.operation === 'grayscale')", 1)[1].split("if (state.operation === 'sign')", 1)[0]
    assert "'grayscale'" in supported
    assert "isAlreadyGrayscale" in grayscale and "new Blob([await file.arrayBuffer()]" in grayscale
    assert "150 / 72" in grayscale and "rowsPerChunk = 128" in grayscale
    assert "window.scheduler.yield()" in grayscale and "context.putImageData(imageData, 0, 0)" in grayscale
    assert "32_000_000" in grayscale and "64 * 1024 * 1024" in grayscale
    assert "Unlock it before converting to grayscale" in grayscale
    assert "grayscale_pages" in worker and "result.embedPng(files[index])" in worker
    assert "local_pdf_worker.js?v=26" in runtime
    assert "Grayscale PDF" in index_html and "searchable text" in index_html
    assert 'src="/assets/app.js?v=154"' in index_html
    assert "paperplane-shell-v95" in service_worker
    assert "'/assets/local_pdf_worker.js?v=26'" in service_worker
    assert "menuBtn.onclick = () => sidebar?.classList.contains('mobile-open')" in app_js


def test_pdf_to_markdown_converts_heading_and_collapses_doubled_bullet_marker(tmp_path):
    source = tmp_path / "markdown-heading-bullet.pdf"
    output = tmp_path / "markdown-heading-bullet.md"
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((60, 70), "Heading From Source", fontsize=22)
        page.insert_text((60, 100), "Regular descriptive paragraph.", fontsize=10)
        page.insert_text((60, 130), "- - Normalize the broken bullet.", fontsize=10)
        for point, text in (((70, 190), "Item"), ((220, 190), "Amount"),
                            ((70, 220), "Revenue"), ((220, 220), "12%")):
            page.insert_text(point, text, fontsize=10)
        shape = page.new_shape()
        for start, end in (((60, 170), (320, 170)), ((60, 200), (320, 200)),
                           ((60, 230), (320, 230)), ((60, 170), (60, 230)),
                           ((190, 170), (190, 230)), ((320, 170), (320, 230))):
            shape.draw_line(start, end)
        shape.finish(color=(0, 0, 0), width=1)
        shape.commit()
        pdf.save(source)
    converters.pdf_to_markdown(source, output)

    markdown = output.read_text(encoding="utf-8")
    assert "# Heading From Source" in markdown
    assert "- Normalize the broken bullet." in markdown
    assert "- - Normalize" not in markdown
    assert "| Item | Amount |" in markdown and "| Revenue | 12% |" in markdown


def test_pdf_to_markdown_preserves_words_split_by_space_only_spans(tmp_path):
    source = tmp_path / "markdown-space-spans.pdf"
    output = tmp_path / "markdown-space-spans.md"
    with fitz.open() as pdf:
        page = pdf.new_page()
        font_size = 22
        x = 60
        page.insert_text((x, 70), "Paper", fontsize=font_size)
        x += fitz.get_text_length("Paper", fontsize=font_size) + 0.5
        page.insert_text((x, 70), " ", fontsize=font_size)
        x += fitz.get_text_length(" ", fontsize=font_size)
        page.insert_text((x, 70), "plane", fontsize=font_size)
        pdf.save(source)

    converters.pdf_to_markdown(source, output)

    markdown = output.read_text(encoding="utf-8")
    assert "# Paper plane" in markdown
    assert "# Paperplane" not in markdown


def test_browser_photo_resize_uses_contain_fit_for_two_dimensions():
    app_js = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    assert "function fitPhoto(image, width, height)" in app_js
    assert "const canvas = targetW && targetH ? fitPhoto(img, finalW, finalH) : drawPhoto(img, finalW, finalH);" in app_js
    assert "centered on a white canvas" in app_js


def test_grayscale_ui_discloses_rasterization_and_links_to_ocr():
    app_js = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    assert "Colored pages are rendered as images" in app_js
    assert "text may lose searchability" in app_js
    assert '<a href=\"/ocr-pdf\">run OCR PDF</a>' in app_js


def test_developer_api_copy_has_one_copy_label_and_spaces_before_key_example():
    response = TestClient(server.app).get("/developers")
    assert response.status_code == 200
    intro = re.search(r'<div class="api-docs-hero-box".*?<p[^>]*>(.*?)</p>', response.text, re.S).group(1)
    copy_button = re.search(r'<button[^>]*id="btn-copy-full-api-code"[^>]*>(.*?)</button>', response.text, re.S).group(1)
    assert "keys (<code>sk_live_...</code>)" in intro
    assert "keys(<code>" not in intro
    assert copy_button.count("Copy") == 1


def test_public_plan_names_match_billing_catalog_across_pricing_and_account_views():
    html = TestClient(server.app).get("/pricing").text
    catalog = server.public_pricing_catalog()
    cards = list(re.finditer(r'<div class="pricing-tier-card[^\"]*" data-plan-tier="([^"]+)">', html))
    titles = {}
    for index, match in enumerate(cards):
        end = cards[index + 1].start() if index + 1 < len(cards) else html.find("</div>\n      </div>", match.end())
        card_html = html[match.end():end if end > match.end() else len(html)]
        title = re.search(r'<h4 class="tier-title">(.*?)</h4>', card_html, re.S)
        assert title, f"missing title for {match.group(1)}"
        titles[match.group(1)] = re.sub(r"\s+", " ", title.group(1).replace("&amp;", "&")).strip()
    assert titles == {tier: details["label"] for tier, details in catalog.items()}
    app_js = Path("web/assets/app.js").read_text(encoding="utf-8")
    assert "tierName = 'Exam Pass'" in app_js
    assert "shortLabel = 'Exam Pass'" in app_js
    assert "Student Pro</h4>" not in html
    assert "Exam & 24h Pass</h4>" not in html


def test_ai_workspace_and_quota_copy_avoid_outdated_storage_and_limit_claims():
    client = TestClient(server.app)
    ai_html = client.get("/ai-intelligence").text
    assert "Your AI PDF and full chat history save in this browser" not in ai_html
    index_html = client.get("/").text
    assert "Unlimited · 500 MB · 100 files" not in index_html
    assert 'id="settings-quota-description"' in index_html
    limits = server.plan_limits_payload()
    assert f"files up to {limits['free_max_file_size_mb']} MB each" in index_html
    assert f"files up to {limits['pro_max_file_size_mb']} MB each" in index_html
    app_js = Path("web/assets/app.js").read_text(encoding="utf-8")
    assert "No daily operation cap" in app_js
    assert "${state.planLimits.free_operations_per_day} server operations per day" in app_js


def test_public_api_spec_links_resolve_without_developer_page_loop():
    client = TestClient(server.app)
    developers = client.get("/developers")
    swagger = client.get("/spec/swagger")
    redoc = client.get("/spec/redoc")
    schema = client.get("/spec/openapi.json")
    assert developers.status_code == swagger.status_code == redoc.status_code == schema.status_code == 200
    swagger_init = client.get("/assets/swagger-init.js")
    assert '<script src="/assets/swagger-init.js"></script>' in swagger.text
    assert "<script>" not in swagger.text
    assert swagger_init.status_code == 200 and "url: '/spec/openapi.json'" in swagger_init.text
    assert 'spec-url="/spec/openapi.json"' in redoc.text
    assert schema.json()["openapi"].startswith("3.")
    assert "/spec/swagger" in developers.text and "/spec/redoc" in developers.text
    assert client.get("/docs", follow_redirects=True).url.path == "/spec/swagger"
    assert client.get("/api-docs", follow_redirects=True).url.path == "/spec/swagger"
    assert client.get("/redoc", follow_redirects=True).url.path == "/spec/redoc"


def test_merge_seo_does_not_claim_unavailable_thumbnail_reordering():
    client = TestClient(server.app)
    response = client.get("/api/seo/merge")
    assert response.status_code == 200
    body = response.json()
    assert "Files are merged in the order you add them" in body["intro"]
    assert "Rearrange thumbnails before processing" not in body["how_to"]
    assert any("remove files and add them again" in answer for _, answer in body["faqs"])


def test_footer_shows_the_running_application_version():
    client = TestClient(server.app)
    response = client.get("/")
    assert response.status_code == 200
    assert f'id="app-version">Version {server.app.version}</span>' in response.text


def test_ai_and_apps_workflows_explain_how_to_use_them():
    client = TestClient(server.app)
    html = client.get("/").text
    assert 'How AI Intelligence works' in html
    assert 'Run OCR first when a scanned PDF has no searchable text.' in html
    assert 'How the apps waitlist works' in html
    assert 'browser-based PDF tools while native desktop and mobile apps are in development' in html


def test_mobile_settings_uses_compact_horizontal_navigation_and_single_content_scroller():
    styles = (Path(__file__).resolve().parents[1] / "web/assets/styles.css").read_text(encoding="utf-8")
    mobile = styles[styles.index("@media (max-width: 767px)"):]
    settings = mobile[:mobile.index(".endpoints-table-wrapper")]
    assert "flex-wrap: nowrap" in settings
    assert "overflow-x: auto" in settings
    assert ".settings-modal-card .settings-tab-btn small { display: none; }" in settings
    assert ".settings-modal-card .settings-content { flex: 1 1 auto; min-height: 0;" in settings


def test_auth_pending_keeps_sidebar_profile_space_without_flashing_identity():
    styles = (Path(__file__).resolve().parents[1] / "web/assets/styles.css").read_text(encoding="utf-8")
    assert ".auth-pending .profile-card, .auth-restoring .profile-card { visibility: visible; }" in styles
    assert ".auth-pending #user-name, .auth-pending #user-role-badge," in styles
    assert ".auth-restoring #user-name, .auth-restoring #user-role-badge { visibility: hidden; }" in styles


def test_browser_processing_support_copy_matches_between_sidebar_and_settings():
    response = TestClient(server.app).get("/")
    assert response.status_code == 200
    expected = "Available for Merge, Split / extract, Remove pages, Rotate PDF, Page Organizer, Scan to PDF, JPG/PNG to PDF, PDF-to-JPG, Grayscale PDF, Crop PDF, Add Text & Stamps, Sign PDF, Fill PDF Forms, Flatten PDF forms, Edit PDF Metadata, PDF-to-Text, Compare PDF text, PDF-to-Markdown (basic), PDF-to-Word (text-first), Page Numbers, text and image watermarks, and photo tools"
    assert f'id="privacy-mode-support" class="privacy-mode-support">{expected}</small>' in response.text
    assert f'id="settings-client-privacy-support">{expected}.</small>' in response.text


def test_pdf_to_text_forms_flatten_metadata_page_numbers_and_crop_are_zero_upload_tools():
    root = Path(__file__).resolve().parents[1]
    app_js = (root / "web/assets/app.js").read_text(encoding="utf-8")
    index_html = (root / "web/index.html").read_text(encoding="utf-8")
    service_worker = (root / "web/assets/service-worker.js").read_text(encoding="utf-8")
    assert "'pdf_to_text'" in app_js.split("const CLIENT_SIDE_SUPPORTED_OPERATIONS", 1)[1].split(";", 1)[0]
    assert "'pdf_to_jpg'" in app_js.split("const CLIENT_SIDE_SUPPORTED_OPERATIONS", 1)[1].split(";", 1)[0]
    assert "'flatten'" in app_js.split("const CLIENT_SIDE_SUPPORTED_OPERATIONS", 1)[1].split(";", 1)[0]
    assert "'forms'" in app_js.split("const CLIENT_SIDE_SUPPORTED_OPERATIONS", 1)[1].split(";", 1)[0]
    assert "'metadata'" in app_js.split("const CLIENT_SIDE_SUPPORTED_OPERATIONS", 1)[1].split(";", 1)[0]
    assert "'page_numbers'" in app_js.split("const CLIENT_SIDE_SUPPORTED_OPERATIONS", 1)[1].split(";", 1)[0]
    assert "'crop'" in app_js.split("const CLIENT_SIDE_SUPPORTED_OPERATIONS", 1)[1].split(";", 1)[0]
    assert "'watermark'" in app_js.split("const CLIENT_SIDE_SUPPORTED_OPERATIONS", 1)[1].split(";", 1)[0]
    assert "'edit'" in app_js.split("const CLIENT_SIDE_SUPPORTED_OPERATIONS", 1)[1].split(";", 1)[0]
    assert "'sign'" in app_js.split("const CLIENT_SIDE_SUPPORTED_OPERATIONS", 1)[1].split(";", 1)[0]
    assert "pdfjsLib.getDocument" in app_js
    assert "No selectable text was found. Run OCR first" in app_js
    worker = (root / "web/assets/local_pdf_worker.js").read_text(encoding="utf-8")
    assert "if (operation === 'flatten')" in worker
    assert "form.flatten();" in worker
    assert "field.setText(value)" in worker
    assert "operation === 'metadata'" in worker and "pdf[setter]" in worker
    assert "if (operation === 'page_numbers')" in worker and "setTextRenderingMode(TextRenderingMode.FillAndOutline)" in worker
    assert "if (operation === 'crop')" in worker and "page.setCropBox" in worker
    assert "if (operation === 'watermark')" in worker and "page.node.newExtGState" in worker
    assert "if (operation === 'zip_jpg')" in worker and "zipPages(files.map" in worker
    assert "if (operation === 'edit')" in worker and "page.drawText(text" in worker
    assert "if (operation === 'sign')" in worker and "pdf.embedPng(files[1])" in worker
    assert "if (operation === 'metadata')" in app_js and "options[key] = value" in app_js
    assert "PDF-to-Text" in index_html
    assert all(label in index_html for label in ("Fill PDF Forms", "Flatten PDF forms", "Edit PDF Metadata", "Page Numbers", "Crop PDF"))
    assert "local_pdf_worker.js?v=26" in (root / "web/assets/pdf_runtime.js").read_text(encoding="utf-8")
    assert 'src="/assets/pdf_runtime.js?v=25"' in index_html
    assert 'src="/assets/app.js?v=154"' in index_html
    assert 'src="/assets/page_organizer.js?v=20"' in index_html
    assert "paperplane-shell-v95" in service_worker
    assert "'/assets/app.js?v=154'" in service_worker
    assert "'/assets/page_organizer.js?v=20'" in service_worker
    assert "'/assets/styles.css?v=61'" in service_worker


def test_pricing_grid_uses_responsive_two_column_desktop_tracks():
    index_html = (Path(__file__).resolve().parents[1] / "web/index.html").read_text(encoding="utf-8")
    styles = (Path(__file__).resolve().parents[1] / "web/assets/styles.css").read_text(encoding="utf-8")
    grid_markup = re.search(r'<div class="pricing-tiers-grid"([^>]*)>', index_html)
    assert grid_markup and "style=" not in grid_markup.group(1)
    assert re.search(r"\.pricing-tiers-grid\s*\{\s*display:\s*grid;\s*grid-template-columns:\s*1fr 1fr;", styles)
    assert re.search(r"@media\s*\(max-width:\s*760px\)\s*\{\s*\.pricing-tiers-grid\s*\{\s*grid-template-columns:\s*1fr;", styles)


def test_offscreen_studio_worker_encodes_thumbnails_off_thread_and_keeps_fallback():
    root = Path(__file__).resolve().parents[1]
    worker = (root / "web/assets/studio_render_worker.js").read_text(encoding="utf-8")
    organizer = (root / "web/assets/page_organizer.js").read_text(encoding="utf-8")
    runtime = (root / "web/assets/pdf_runtime.js").read_text(encoding="utf-8")
    service_worker = (root / "web/assets/service-worker.js").read_text(encoding="utf-8")
    assert "new OffscreenCanvas(1, 1)" in worker
    assert "studio_render_worker.js?v=4" in runtime
    assert "studio_render_worker.js?v=4" in service_worker
    thumbnail_fallback = organizer.split("// A failed thumbnail request must not tear down", 1)[1].split("if (sourceDoc !== this.pdfDoc", 1)[0]
    assert ".close()" not in thumbnail_fallback


def test_offline_shell_precaches_pdf_dependencies_for_browser_local_processing():
    worker = (Path(__file__).resolve().parents[1] / "web/assets/service-worker.js").read_text(encoding="utf-8")
    assert "const CACHE_NAME = 'paperplane-shell-v95'" in worker
    assert all(asset in worker for asset in (
        "'/assets/pdf.min.js'",
        "'/assets/pdf.worker.min.js'",
        "'/assets/pdf-lib.min.js'",
        "'/assets/local_pdf_worker.js?v=26'",
    ))


def test_tool_directory_counts_integrated_ai_features_without_duplicate_cards():
    app_js = (Path(__file__).resolve().parents[1] / "web/assets/app.js").read_text(encoding="utf-8")
    assert "const matchingOps = cat.ops.filter(id => {" in app_js
    assert "const ops = matchingOps.filter(id => !AI_WORKSPACE_FEATURE_OPERATIONS.has(id));" in app_js
    assert "totalVisible += matchingOps.length;" in app_js
    assert "const totalDistinctTools = Object.keys(state.operations).length;" in app_js
    assert "if (allFilter) allFilter.textContent = `All ${totalDistinctTools} Tools`;" in app_js
    assert "Chat with a PDF, extract Smart Metadata, and create an Executive Brief" in app_js


def test_acroform_field_rendering_uses_safe_dom_text_apis():
    source = (Path(__file__).resolve().parents[1] / "web/assets/security_forms.js").read_text(encoding="utf-8")
    render_start = source.index("// Render fields editor list")
    render_end = source.index("async applyFormFill()", render_start)
    render = source[render_start:render_end]
    assert "row.innerHTML" not in render
    assert "nameLabel.textContent = fieldName" in render
    assert "option.textContent = optionValue" in render
    assert "input.value = String(field.field_value ?? '')" in render
    assert "input.dataset.name = fieldName" in render
    organizer = (Path(__file__).resolve().parents[1] / "web/assets/page_organizer.js").read_text(encoding="utf-8")
    assert "pageLabel.textContent = String(p.label || pageNum)" in organizer
    assert '${p.label || pageNum}' not in organizer


def test_pdf_to_word_browser_path_builds_disclosed_text_first_docx():
    root = Path(__file__).resolve().parents[1]
    app_js = (root / "web/assets/app.js").read_text(encoding="utf-8")
    index_html = (root / "web/index.html").read_text(encoding="utf-8")
    service_worker = (root / "web/assets/service-worker.js").read_text(encoding="utf-8")
    supported = app_js.split("const CLIENT_SIDE_SUPPORTED_OPERATIONS", 1)[1].split(";", 1)[0]
    word_path = app_js.split("if (state.operation === 'pdf_to_word')", 1)[1].split("if (state.operation === 'pdf_to_text')", 1)[0]
    assert "'pdf_to_word'" in supported
    assert "const markdown = await extractPdfMarkdown(file, isCurrent, localProgress)" in word_path
    assert "const blob = buildTextOnlyDocx(markdown)" in word_path
    assert "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in app_js
    assert "w:pageBreakBefore" in app_js and "escapeDocxXml" in app_js
    assert "images, exact layout, and table structure are not" in app_js
    assert "Server Processing for supported table/layout reconstruction" in app_js
    assert 'src="/assets/app.js?v=154"' in index_html
    assert "'/assets/app.js?v=154'" in service_worker
    assert "const CACHE_NAME = 'paperplane-shell-v95'" in service_worker


def test_ai_empty_document_context_topbar_does_not_reserve_blank_height():
    root = Path(__file__).resolve().parents[1]
    styles = (root / "web/assets/styles.css").read_text(encoding="utf-8")
    index_html = (root / "web/index.html").read_text(encoding="utf-8")
    service_worker = (root / "web/assets/service-worker.js").read_text(encoding="utf-8")
    assert ".ai-studio-topbar:has(#ai-active-doc-bar[hidden])" in styles
    assert "min-height: 0 !important" in styles
    assert ".ai-engine-notice-bar" in styles
    assert 'href="/assets/styles.css?v=61"' in index_html
    assert "'/assets/styles.css?v=61'" in service_worker
    assert "const CACHE_NAME = 'paperplane-shell-v95'" in service_worker



def test_mobile_fixed_workspace_bar_scroll_padding_keeps_focus_visible():
    styles = (Path(__file__).resolve().parents[1] / "web" / "assets" / "styles.css").read_text(encoding="utf-8")
    mobile_nav_clearance = styles.split("/* Keep focused AI actions visible above the fixed mobile workspace bar. */", 1)[1]
    assert "@media (max-width: 900px)" in mobile_nav_clearance
    assert "html {\n    scroll-padding-bottom: calc(76px + env(safe-area-inset-bottom, 0px));" in mobile_nav_clearance
    assert ".main-area {\n    scroll-padding-bottom: calc(76px + env(safe-area-inset-bottom, 0px));" in mobile_nav_clearance


def test_cashfree_sandbox_failure_alert_creates_one_owner_assigned_issue():
    import json
    from scripts.alert_cashfree_probe_failure import TITLE, ensure_failure_issue

    requests = []

    def opener(request, timeout):
        requests.append(request)
        if request.get_method() == "GET":
            return io.BytesIO(b"[]")
        return io.BytesIO(json.dumps({"number": 123, "title": TITLE}).encode("utf-8"))

    created, issue_number = ensure_failure_issue(
        "hammad986/paperplane-pdf", "test-token-do-not-log", "44357454438", opener=opener
    )
    assert created is True and issue_number == 123
    assert [request.get_method() for request in requests] == ["GET", "POST"]
    created_issue = json.loads(requests[1].data)
    assert created_issue["title"] == TITLE
    assert created_issue["assignees"] == ["hammad986"]
    assert "@hammad986" in created_issue["body"]
    assert "actions/runs/44357454438" in created_issue["body"]
    assert "does not submit a payment" in created_issue["body"]
    assert "test-token-do-not-log" in requests[0].get_header("Authorization")

    def existing_issue(request, timeout):
        assert request.get_method() == "GET"
        return io.BytesIO(json.dumps([{"number": 123, "title": TITLE}]).encode("utf-8"))

    duplicate_created, existing_number = ensure_failure_issue(
        "hammad986/paperplane-pdf", "test-token-do-not-log", "44357454438", opener=existing_issue
    )
    assert duplicate_created is False and existing_number == 123


def test_cashfree_sandbox_workflow_alerts_once_on_failure_with_minimum_permissions():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/cashfree-sandbox-probe.yml").read_text(encoding="utf-8")
    assert "contents: read" in workflow
    assert "issues: write" in workflow
    assert workflow.index("name: Validate Cashfree TEST credentials") < workflow.index("name: Install browser probe dependencies")
    credential_check = workflow.split("name: Validate Cashfree TEST credentials", 1)[1].split("      - uses: actions/setup-python", 1)[0]
    assert '"$CASHFREE_APP_ID"' in credential_check
    assert '"$CASHFREE_SECRET_KEY"' in credential_check
    assert "::error::Cashfree TEST credentials are not configured." in credential_check
    assert "CASHFREE_APP_ID" not in credential_check.replace('"$CASHFREE_APP_ID"', "")
    assert "CASHFREE_SECRET_KEY" not in credential_check.replace('"$CASHFREE_SECRET_KEY"', "")
    assert "if: failure()" in workflow
    assert "python scripts/alert_cashfree_probe_failure.py" in workflow
    alert = (root / "scripts/alert_cashfree_probe_failure.py").read_text(encoding="utf-8")
    assert "does not submit a payment" in alert
    assert "state=open&per_page=100" in alert


def test_hidden_tool_catalogs_are_not_rendered_before_initial_workspace_routing():
    root = Path(__file__).resolve().parents[1]
    source = (root / "web/assets/app.js").read_text(encoding="utf-8")
    start = source.index("async function init() {")
    end = source.index("\nfunction handleInitialRouting()", start)
    init = source[start:end]
    initial_setup = init.split("handleInitialRouting();", 1)[0]
    assert "renderSidebarTools();" in initial_setup
    assert "renderHomeToolsGrid();" not in initial_setup
    assert "renderToolDeskDirectory();" not in initial_setup
    assert init.index("handleInitialRouting();") < init.index("const availability = safeFetch('/api/operations'")
    availability = init.split("const availability = safeFetch('/api/operations'", 1)[1]
    assert "if (state.activeView === 'home') renderHomeToolsGrid();" in availability
    assert "if (state.activeView === 'tool-desk') renderToolDeskDirectory();" in availability


def test_command_palette_escapes_operation_metadata_before_html_rendering():
    root = Path(__file__).resolve().parents[1]
    source = (root / "web/assets/app.js").read_text(encoding="utf-8")
    start = source.index("function renderCommandResults(query) {")
    end = source.index("\nwindow.selectOperationFromCommand", start)
    renderer = source[start:end]
    assert 'data-command-operation="${escapeHtml(key)}"' in renderer
    assert "<strong>${escapeHtml(item.label || key)}</strong>" in renderer
    assert "${escapeHtml(item.description || 'Production workflow')}" in renderer
    assert "<span class=\"command-item-badge\">${escapeHtml(item.category || '')}</span>" in renderer
    sidebar_start = source.index("function renderSidebarTools() {")
    sidebar_end = source.index("\n// ----------------------------------------------------------------------\n// Tool Desk catalog", sidebar_start)
    sidebar = source[sidebar_start:sidebar_end]
    assert 'data-select-operation="${escapeHtml(key)}"' in sidebar
    assert '${escapeHtml(item.label || key)}' in sidebar
    home_start = source.index("function renderHomeToolsGrid(")
    home_end = source.index("\nfunction renderToolDeskDirectory", home_start)
    home = source[home_start:home_end]
    assert '${escapeHtml(op.label || opId)}' in home
    assert "${escapeHtml(op.description || 'Fast, sovereign document processing.')" in home
    assert "${escapeHtml(badgeText)}" in home
    update_button_start = source.index("function updateButton() {")
    update_button_end = source.index("\nfunction getToolRequiredFieldState", update_button_start)
    update_button = source[update_button_start:update_button_end]
    assert '${escapeHtml(toolLabel)} unavailable' in update_button
    assert update_button.count('${escapeHtml(activeToolLabel)} Now') == 2
    assert "const CACHE_NAME = 'paperplane-shell-v95'" in (root / "web/assets/service-worker.js").read_text(encoding="utf-8")
    assert 'src="/assets/app.js?v=154"' in (root / "web/index.html").read_text(encoding="utf-8")


def test_studio_batch_selection_skips_redundant_toolbar_geometry_sync():
    root = Path(__file__).resolve().parents[1]
    source = (root / "web/assets/page_organizer.js").read_text(encoding="utf-8")
    start = source.index("    _updateBatchToolbar({ syncLayout = true } = {}) {")
    end = source.index("\n    _bindSubnavEvents()", start)
    method = source[start:end]
    assert "const wasHidden = bar.hidden;" in method
    assert "if (syncLayout && wasHidden !== bar.hidden) window.syncStudioBatchPanelLocation?.();" in method


def test_studio_mobile_pages_position_reuses_resize_observer_geometry_cache():
    root = Path(__file__).resolve().parents[1]
    source = (root / "web/assets/app.js").read_text(encoding="utf-8")
    start = source.index("function syncStudioMobilePagesPanelPosition() {")
    end = source.index("\nfunction updateStudioMobilePageSummary()", start)
    sync = source[start:end]
    assert "studioMobilePagesTop === null" in sync
    assert "scheduleStudioMobileToolbarMeasure();" in sync
    assert "toolbar.getBoundingClientRect()" not in sync
    assert "window.matchMedia('(max-height: 600px)').matches" in sync
    assert "calc(8px + env(safe-area-inset-top, 0px))" in sync
    top_update_start = source.index("function updateStudioMobilePagesTop(toolbar) {")
    top_update_end = source.index("\nfunction scheduleStudioMobileToolbarMeasure()", top_update_start)
    top_update = source[top_update_start:top_update_end]
    assert "(max-width: 900px) and (max-height: 600px)" in top_update
    assert "getBoundingClientRect()" not in top_update.split("if (window.matchMedia", 1)[1].split("if (!toolbar", 1)[0]
    observer_start = source.index("const studioMobileToolbar = $('#studio-toolbar');")
    observer_end = source.index("\nfunction syncStudioMobilePagesPanelPosition()", observer_start)
    observer = source[observer_start:observer_end]
    assert "new ResizeObserver(" in observer
    assert "updateStudioMobilePagesTop(studioMobileToolbar);" in observer
    worker = (root / "web/assets/service-worker.js").read_text(encoding="utf-8")
    index_html = (root / "web/index.html").read_text(encoding="utf-8")
    assert 'name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover"' in index_html
    assert "const CACHE_NAME = 'paperplane-shell-v95'" in worker
    assert "'/assets/app.js?v=154'" in worker
    assert 'src="/assets/app.js?v=154"' in index_html
    styles = (root / "web/assets/styles.css").read_text(encoding="utf-8")
    assert "height: calc(64px + env(safe-area-inset-top, 0px)) !important;" in styles
    assert "padding-top: env(safe-area-inset-top, 0px) !important;" in styles
    assert styles.count("padding: calc(64px + env(safe-area-inset-top, 0px)) 0 0 !important;") >= 2
    short_height = styles.split("@media (max-width: 900px) and (max-height: 600px) {", 1)[1].split("\n  /* Layouts follow", 1)[0]
    assert "#app-shell.studio-pages-open .studio-thumbnails-bar" in short_height
    assert "inset: var(--studio-mobile-pages-top" in short_height
    assert "top: calc(8px + env(safe-area-inset-top, 0px)) !important" in short_height
    assert "calc(8px + env(safe-area-inset-bottom, 0px))" in short_height
    assert "z-index: 970 !important" in short_height
    assert "#app-shell.studio-pages-open .studio-mobile-page-actions" in short_height
    assert "max-height: 40px !important" in short_height
    assert "#studio-mobile-page-actions-slot .studio-tool-group" in short_height
    assert "grid-template-columns: repeat(2, minmax(0, 1fr)) !important" in short_height
    assert "padding: 0 6px 4px !important" in short_height


def test_studio_page_scale_reuses_resize_observed_canvas_width():
    root = Path(__file__).resolve().parents[1]
    source = (root / "web/assets/app.js").read_text(encoding="utf-8")
    measure_start = source.index("function updateStudioCanvasAreaWidth(area) {")
    measure_end = source.index("\nfunction syncStudioMobilePagesPanelPosition()", measure_start)
    measurement = source[measure_start:measure_end]
    assert "state.studio.canvasAreaWidth = area.clientWidth || 0" in measurement
    observer_start = source.index("const studioPageStack = $('#studio-page-stack');")
    observer_end = source.index("\nif (studioPageStack)", observer_start)
    observer = source[observer_start:observer_end]
    assert "new ResizeObserver(" in observer
    assert "studioCanvasAreaObserver.observe(studioCanvasArea)" in observer
    assert "updateStudioCanvasAreaWidth(studioCanvasArea)" in observer
    scale_start = source.index("function getStudioPageScale(baseViewport) {")
    scale_end = source.index("\nfunction updateStudioPageSlotSize(", scale_start)
    scale = source[scale_start:scale_end]
    assert "state.studio.canvasAreaWidth || area?.clientWidth || window.innerWidth" in scale
    assert "measuredWidth - horizontalPadding" in scale


def test_studio_toast_repositions_after_toolbar_and_page_geometry_changes():
    root = Path(__file__).resolve().parents[1]
    source = (root / "web/assets/app.js").read_text(encoding="utf-8")
    start = source.index("function showToast(message, type = 'success', duration = 3500) {")
    end = source.index("\nfunction triggerConfetti()", start)
    toast = source[start:end]
    assert "Math.ceil(Math.max(toolbarBottom + 10" in toast
    assert "new ResizeObserver(scheduleStudioToastPosition)" in toast
    assert "positionObserver.observe(toolbar)" in toast
    assert "positionObserver.observe(pageSheet)" in toast
    assert "window.addEventListener('resize', scheduleStudioToastPosition)" in toast
    assert "positionFrame = requestAnimationFrame(() => {" in toast


def test_studio_mid_size_desktop_ribbons_scroll_instead_of_wrapping():
    root = Path(__file__).resolve().parents[1]
    styles = (root / "web/assets/styles.css").read_text(encoding="utf-8")
    compact_tablet = styles.rsplit("@media (min-width: 901px) and (max-width: 1023px)", 1)[1]
    assert "studio-primary-ribbon" in compact_tablet
    assert "studio-sub-ribbon" in compact_tablet
    assert "flex-flow: row nowrap !important" in compact_tablet
    assert "overflow-x: auto !important" in compact_tablet
    assert "overscroll-behavior-inline: contain" in compact_tablet
    assert "touch-action: pan-x" in compact_tablet


def test_overlay_escape_stack_avoids_document_wide_mutation_rescans():
    root = Path(__file__).resolve().parents[1]
    source = (root / "web/assets/app.js").read_text(encoding="utf-8")
    start = source.index("function installOverlayEscapeStack() {")
    end = source.index("\nfunction initFooterReveal()", start)
    installer = source[start:end]
    assert "new MutationObserver" not in installer
    assert "const visible = syncOpenOverlayStack();" in installer
    sync_start = source.index("function syncOpenOverlayStack() {")
    assert "document.querySelectorAll('.modal-backdrop:not([hidden])" in source[sync_start:start]


def test_google_and_cashfree_sdks_are_requested_only_when_their_flows_open():
    root = Path(__file__).resolve().parents[1]
    index_html = (root / "web" / "index.html").read_text(encoding="utf-8")
    app_js = (root / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    service_worker = (root / "web" / "assets" / "service-worker.js").read_text(encoding="utf-8")
    assert "https://accounts.google.com/gsi/client" not in index_html
    assert "https://sdk.cashfree.com/js/v3/cashfree.js" not in index_html
    assert "loadExternalSdk(GOOGLE_IDENTITY_SDK_URL" in app_js
    assert "await loadExternalSdk('https://sdk.cashfree.com/js/v3/cashfree.js'" in app_js
    assert "app.js?v=154" in index_html and "app.js?v=154" in service_worker
    assert "paperplane-shell-v95" in service_worker
