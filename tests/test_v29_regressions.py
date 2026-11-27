import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

import docx
import fitz
from fastapi.testclient import TestClient

import converters
import security_forms_engine
import server


ROOT = Path(__file__).resolve().parents[1]


def test_id447_id448_legacy_redirects_and_sitemap_routes_return_200():
    client = TestClient(server.app)

    expected_redirects = {
        "/api/docs": "/spec/swagger",
        "/refunds": "/refund",
        "/results": "/history",
        "/page-organizer": "/organize-pdf",
        "/tools/page-organizer": "/organize-pdf",
        "/add-text": "/edit-pdf",
        "/tools/add-text": "/edit-pdf",
        "/exam-resizer": "/ssc-photo-resizer",
        "/tools/exam-resizer": "/ssc-photo-resizer",
    }
    for source_path, target_path in expected_redirects.items():
        resp = client.get(source_path, follow_redirects=False)
        assert resp.status_code == 301, f"{source_path} returned {resp.status_code}"
        assert resp.headers.get("location") == target_path

    sitemap_resp = client.get("/sitemap.xml")
    assert sitemap_resp.status_code == 200
    root_xml = ET.fromstring(sitemap_resp.text)
    loc_paths = [
        urlparse(elem.text.strip()).path or "/"
        for elem in root_xml.iter()
        if elem.tag.endswith("loc") and elem.text
    ]
    assert len(loc_paths) >= 60
    for route_path in loc_paths:
        page_resp = client.get(route_path, follow_redirects=False)
        assert page_resp.status_code == 200, f"Sitemap URL {route_path} returned {page_resp.status_code}"


def test_id446_studio_protected_pdf_mutations_and_reencryption(tmp_path):
    source = tmp_path / "locked.pdf"
    with fitz.open() as pdf:
        for i in range(1, 4):
            page = pdf.new_page()
            page.insert_text((72, 72), f"Page {i} SECRET_LINE")
        pdf.save(
            source,
            encryption=fitz.PDF_ENCRYPT_AES_256,
            user_pw="open123",
            owner_pw="open123",
            permissions=fitz.PDF_PERM_PRINT | fitz.PDF_PERM_COPY,
        )

    client = TestClient(server.app)
    raw_bytes = source.read_bytes()

    no_pw = client.post(
        "/api/studio/page/delete",
        data={"page_number": "1"},
        files={"file": ("locked.pdf", raw_bytes, "application/pdf")},
    )
    assert no_pw.status_code == 400
    assert "password" in no_pw.text.lower()

    deleted = client.post(
        "/api/studio/page/delete",
        data={"page_number": "1", "password": "open123"},
        files={"file": ("locked.pdf", raw_bytes, "application/pdf")},
    )
    assert deleted.status_code == 200
    with fitz.open(stream=deleted.content, filetype="pdf") as out_doc:
        assert bool(out_doc.needs_pass) is True
        assert out_doc.authenticate("open123") > 0
        assert len(out_doc) == 2

    rotated = client.post(
        "/api/studio/pages/rotate",
        data={"pages": "[1]", "degrees": "90", "password": "open123"},
        files={"file": ("locked.pdf", raw_bytes, "application/pdf")},
    )
    assert rotated.status_code == 200
    with fitz.open(stream=rotated.content, filetype="pdf") as rot_doc:
        assert bool(rot_doc.needs_pass) is True
        assert rot_doc.authenticate("open123") > 0
        assert rot_doc[0].rotation == 90

    redacted = client.post(
        "/api/studio/security/redact",
        data={"redactions": '[{"page": 0, "text": "SECRET_LINE"}]', "password": "open123"},
        files={"file": ("locked.pdf", raw_bytes, "application/pdf")},
    )
    assert redacted.status_code == 200
    with fitz.open(stream=redacted.content, filetype="pdf") as red_doc:
        assert bool(red_doc.needs_pass) is True
        assert red_doc.authenticate("open123") > 0
        assert "SECRET_LINE" not in red_doc[0].get_text("text")

    compressed = client.post(
        "/api/studio/compress",
        data={"preset": "balanced", "password": "open123"},
        files={"file": ("locked.pdf", raw_bytes, "application/pdf")},
    )
    assert compressed.status_code == 200
    with fitz.open(stream=compressed.content, filetype="pdf") as comp_doc:
        assert bool(comp_doc.needs_pass) is True
        assert comp_doc.authenticate("open123") > 0
        assert len(comp_doc) == 3


def test_id428_69_page_security_inspect_returns_200_quickly(tmp_path):
    source = tmp_path / "manual_69.pdf"
    with fitz.open() as pdf:
        for i in range(1, 70):
            page = pdf.new_page()
            page.insert_text((72, 72), f"Security audit benchmark page {i}")
        pdf.save(source)

    t0 = time.monotonic()
    direct_report = security_forms_engine.inspect_pdf_security(source)
    elapsed = time.monotonic() - t0
    assert direct_report["page_count"] == 69
    assert direct_report["is_digitally_signed"] is False
    assert elapsed < 5.0

    client = TestClient(server.app)
    resp = client.post(
        "/api/studio/security/inspect",
        files={"file": ("manual_69.pdf", source.read_bytes(), "application/pdf")},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["page_count"] == 69
    assert payload["is_digitally_signed"] is False


def test_id282_clean_output_stems_strip_internal_uuid_prefixes(tmp_path):
    prefixed_hex = "12_0123456789abcdef0123456789abcdef_budget_report.pdf"
    prefixed_uuid = "12345678-1234-1234-1234-123456789abc_invoice_q4.docx"
    assert converters.clean_display_stem(prefixed_hex) == "budget_report"
    assert converters.clean_display_stem(prefixed_uuid) == "invoice_q4"
    assert server._clean_output_stem(tmp_path / prefixed_hex) == "budget_report"
    assert server._clean_output_stem(None, {"_original_filename": prefixed_uuid}) == "invoice_q4"

    prefixed_pdf = tmp_path / prefixed_hex
    with fitz.open() as pdf:
        for idx in range(1, 3):
            p = pdf.new_page()
            p.insert_text((72, 72), f"Annual report line {idx}")
        pdf.save(prefixed_pdf)

    docx_out = tmp_path / "out.docx"
    converters.pdf_to_word(prefixed_pdf, docx_out, document_name=prefixed_hex)
    word_doc = docx.Document(str(docx_out))
    assert word_doc.core_properties.title == "budget_report"

    md_out = tmp_path / "out.md"
    converters.pdf_to_markdown(prefixed_pdf, md_out, document_name=prefixed_hex)
    assert md_out.read_text(encoding="utf-8").startswith("# budget_report\n\n")

    html_out = tmp_path / "out.html"
    converters.pdf_to_html(prefixed_pdf, html_out, document_name=prefixed_hex)
    assert "<title>budget_report</title>" in html_out.read_text(encoding="utf-8")

    split_dir = tmp_path / "split_parts"
    parts = converters.split_pdf_document(prefixed_pdf, split_dir, "every_n", "1")
    assert all(p.name.startswith("budget_report_part") for p in parts)


def test_id443_id444_id445_id449_id450_id375_frontend_contracts():
    app_js = (ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    worker_js = (ROOT / "web" / "assets" / "studio_render_worker.js").read_text(encoding="utf-8")
    styles_css = (ROOT / "web" / "assets" / "styles.css").read_text(encoding="utf-8")
    index_html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

    # ID 444 / 427-render: no bitmaprenderer transferFromImageBitmap() call, fallback on Standard-14/Type3 fonts
    assert "transferFromImageBitmap(" not in app_js
    assert "ensureStudio2dContext();" in app_js
    assert "context.drawImage(workerBitmap, 0, 0);" in app_js
    assert "fontObj.missingFile || !fontObj.data || fontObj.isType3Font" in worker_js

    # ID 443: paid tier guard and silent Studio clear on logout
    assert "if (isPaidTierData(state.user) || isPaidTierData(state.billing)) return;" in app_js
    assert "clearStudioPdf({ silent: true })" in app_js

    # ID 449 & 450: toast above modal backdrop (>=3000) and live OTP countdown sync
    toast_z_values = [int(m) for m in re.findall(r"\.toast-notice[^{]*\{[^}]*z-index:\s*(\d+)", styles_css)]
    assert toast_z_values and all(z >= 3000 for z in toast_z_values), toast_z_values
    assert 'id="auth-otp-status"' in index_html
    assert "startOtpCountdown(Number(waitMatch[1]), { syncErrorCountdown: true })" in app_js

    # ID 446: all Studio mutation modules read the active Studio password
    for rel in (
        "web/assets/page_organizer.js",
        "web/assets/editor.js",
        "web/assets/optimization_engine.js",
        "web/assets/security_forms.js",
        "web/assets/conversion_engine.js",
    ):
        content = (ROOT / rel).read_text(encoding="utf-8")
        assert "window.getPaperplaneStudioPassword?.()" in content, rel

    opt_js = (ROOT / "web" / "assets" / "optimization_engine.js").read_text(encoding="utf-8")
    assert "postStudioForm('/api/studio/compress/analyze'" in opt_js

    # ID 375: Studio More Tools compress button stays in Studio instead of selectOperation navigation
    assert "studio-compress-btn" not in app_js


def test_id446_additional_protected_studio_routes(tmp_path):
    source = tmp_path / "locked_extra.pdf"
    with fitz.open() as pdf:
        for i in range(1, 3):
            p = pdf.new_page()
            p.insert_text((72, 72), f"Confidential line page {i}")
        pdf.save(
            source,
            encryption=fitz.PDF_ENCRYPT_AES_256,
            user_pw="open123",
            owner_pw="open123",
            permissions=fitz.PDF_PERM_PRINT | fitz.PDF_PERM_COPY,
        )

    client = TestClient(server.app)
    raw = source.read_bytes()

    analyze_ok = client.post(
        "/api/studio/compress/analyze",
        data={"password": "open123"},
        files={"file": ("locked_extra.pdf", raw, "application/pdf")},
    )
    assert analyze_ok.status_code == 200
    assert analyze_ok.json()["analysis"]["page_count"] == 2

    meta_ok = client.post(
        "/api/studio/pages/metadata",
        data={"password": "open123"},
        files={"file": ("locked_extra.pdf", raw, "application/pdf")},
    )
    assert meta_ok.status_code == 200
    assert meta_ok.json()["data"]["totalPages"] == 2
    assert len(meta_ok.json()["data"]["pages"]) == 2

    split_ok = client.post(
        "/api/studio/documents/split",
        data={"mode": "ranges", "param": "1", "password": "open123"},
        files={"file": ("locked_extra.pdf", raw, "application/pdf")},
    )
    assert split_ok.status_code == 200
    with fitz.open(stream=split_ok.content, filetype="pdf") as sp_doc:
        assert bool(sp_doc.needs_pass) is True
        assert sp_doc.authenticate("open123") > 0
        assert len(sp_doc) == 1

    conv_ok = client.post(
        "/api/studio/convert",
        data={"target_format": "txt", "options": "{}", "password": "open123"},
        files={"file": ("locked_extra.pdf", raw, "application/pdf")},
    )
    assert conv_ok.status_code == 200
    assert "Confidential line page 1" in conv_ok.text

    forms_analyze = client.post(
        "/api/studio/forms/analyze",
        data={"password": "open123"},
        files={"file": ("locked_extra.pdf", raw, "application/pdf")},
    )
    assert forms_analyze.status_code == 200

    forms_add = client.post(
        "/api/studio/forms/add-field",
        data={"field_data": '{"page": 0, "type": "text", "name": "signer", "rect": [72, 120, 250, 148], "value": "Ada"}', "password": "open123"},
        files={"file": ("locked_extra.pdf", raw, "application/pdf")},
    )
    assert forms_add.status_code == 200
    with fitz.open(stream=forms_add.content, filetype="pdf") as fa_doc:
        assert bool(fa_doc.needs_pass) is True
        assert fa_doc.authenticate("open123") > 0
        assert any(w.field_name == "signer" for w in (fa_doc[0].widgets() or ()))

