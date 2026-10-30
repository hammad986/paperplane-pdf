import io
import json
import pathlib
import pytest
import fitz
from fastapi.testclient import TestClient

import security_forms_engine
from server import app

client = TestClient(app)


@pytest.fixture
def sample_pdf(tmp_path) -> pathlib.Path:
    p = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "Paperplane Secure Document - Confidential Record", fontsize=16)
    page.insert_text((72, 140), "Customer ID: CUST-99281, SSN: 000-12-3456", fontsize=11)
    doc.save(str(p))
    doc.close()
    return p


@pytest.fixture
def test_credentials():
    cert_pem, key_pem = security_forms_engine.generate_test_certificate(
        common_name="Paperplane Test Signer",
        org="Paperplane QA Suite",
        days=30
    )
    return cert_pem, key_pem


# ==============================================================================
# 1. ACROFORM ENGINE TESTS
# ==============================================================================

def test_form_field_creation_and_analysis(sample_pdf, tmp_path):
    out_pdf = tmp_path / "form_created.pdf"
    # Add text field
    security_forms_engine.add_form_field(sample_pdf, out_pdf, {
        "page": 0, "type": "text", "name": "full_name",
        "rect": [72, 200, 300, 230], "value": "Alice Wonderland", "required": True
    })
    # Add checkbox
    security_forms_engine.add_form_field(out_pdf, out_pdf, {
        "page": 0, "type": "checkbox", "name": "agree_terms",
        "rect": [72, 250, 92, 270], "value": True
    })
    # Add combobox
    security_forms_engine.add_form_field(out_pdf, out_pdf, {
        "page": 0, "type": "combobox", "name": "department",
        "rect": [72, 300, 300, 330], "choice_values": ["Engineering", "Finance", "Legal"], "value": "Engineering"
    })

    analysis = security_forms_engine.analyze_pdf_forms(out_pdf)
    assert analysis["field_count"] == 3
    names = {f["field_name"] for f in analysis["fields"]}
    assert "full_name" in names
    assert "agree_terms" in names
    assert "department" in names


def test_form_field_filling_and_appearance(sample_pdf, tmp_path):
    f1 = tmp_path / "base_form.pdf"
    security_forms_engine.add_form_field(sample_pdf, f1, {
        "page": 0, "type": "text", "name": "account_number",
        "rect": [72, 200, 300, 230], "value": "ACC-1000"
    })
    security_forms_engine.add_form_field(f1, f1, {
        "page": 0, "type": "checkbox", "name": "opt_in",
        "rect": [72, 250, 92, 270], "value": False
    })

    f2 = tmp_path / "filled_form.pdf"
    security_forms_engine.fill_pdf_forms(f1, f2, {
        "account_number": "ACC-9999-VERIFIED",
        "opt_in": True
    })

    analysis = security_forms_engine.analyze_pdf_forms(f2)
    field_map = {f["field_name"]: f for f in analysis["fields"]}
    assert field_map["account_number"]["field_value"] == "ACC-9999-VERIFIED"
    assert field_map["opt_in"]["field_value"] in ("Yes", "1", "true", "True")


def test_form_field_edge_cases_and_unicode(sample_pdf, tmp_path):
    f1 = tmp_path / "unicode_form.pdf"
    security_forms_engine.add_form_field(sample_pdf, f1, {
        "page": 0, "type": "text", "name": "multilingual_notes",
        "rect": [72, 200, 450, 260], "value": "", "multiline": True
    })

    f2 = tmp_path / "unicode_filled.pdf"
    security_forms_engine.fill_pdf_forms(f1, f2, {
        "multilingual_notes": "Special: ë, ñ, 中文, العربية, 🚀 Paperplane"
    })

    data = security_forms_engine.export_form_data(f2)
    assert "🚀 Paperplane" in data["multilingual_notes"]


def test_form_flattening_destroys_all_widgets(sample_pdf, tmp_path):
    f1 = tmp_path / "pre_flatten.pdf"
    security_forms_engine.add_form_field(sample_pdf, f1, {
        "page": 0, "type": "text", "name": "tax_id",
        "rect": [72, 200, 300, 230], "value": "TAX-555"
    })
    assert security_forms_engine.analyze_pdf_forms(f1)["field_count"] == 1

    f2 = tmp_path / "flattened.pdf"
    security_forms_engine.flatten_pdf_forms(f1, f2)
    post_analysis = security_forms_engine.analyze_pdf_forms(f2)
    assert post_analysis["field_count"] == 0

    # Ensure vector text remains readable on page
    doc = fitz.open(str(f2))
    page_text = doc[0].get_text()
    doc.close()
    assert "TAX-555" in page_text


def test_form_reset_to_defaults(sample_pdf, tmp_path):
    f1 = tmp_path / "form_to_reset.pdf"
    security_forms_engine.add_form_field(sample_pdf, f1, {
        "page": 0, "type": "text", "name": "editable_field",
        "rect": [72, 200, 300, 230], "value": "User Entered Text"
    })
    f2 = tmp_path / "reset_output.pdf"
    security_forms_engine.reset_pdf_forms(f1, f2)

    data = security_forms_engine.export_form_data(f2)
    assert data["editable_field"] == ""


def test_form_export_and_import_roundtrip(sample_pdf, tmp_path):
    f1 = tmp_path / "roundtrip_base.pdf"
    security_forms_engine.add_form_field(sample_pdf, f1, {
        "page": 0, "type": "text", "name": "field_a",
        "rect": [72, 200, 300, 230], "value": "Original Value"
    })
    # Export
    exported = security_forms_engine.export_form_data(f1)
    assert exported == {"field_a": "Original Value"}

    # Import new data
    f2 = tmp_path / "roundtrip_imported.pdf"
    security_forms_engine.import_form_data(f1, f2, {"field_a": "Imported Value 42"})
    new_data = security_forms_engine.export_form_data(f2)
    assert new_data["field_a"] == "Imported Value 42"


# ==============================================================================
# 2. SIGNING ENGINE (VISUAL & DIGITAL PKCS#7)
# ==============================================================================

def test_visual_signature_typed(sample_pdf, tmp_path):
    signed = tmp_path / "typed_signed.pdf"
    security_forms_engine.add_visual_signature(
        sample_pdf, signed, "Jane Doe",
        page_num=0, rect=[72, 600, 280, 680],
        signer_name="Jane Doe", date_str="2026-10-03"
    )
    doc = fitz.open(str(signed))
    text = doc[0].get_text()
    doc.close()
    assert "Jane Doe" in text


def test_visual_signature_image_stamp(sample_pdf, tmp_path):
    # Create minimal 1x1 transparent PNG base64
    tiny_png_b64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    signed = tmp_path / "stamp_signed.pdf"
    security_forms_engine.add_visual_signature(
        sample_pdf, signed, tiny_png_b64,
        page_num=0, rect=[72, 600, 280, 680],
        signer_name="Official Seal"
    )
    doc = fitz.open(str(signed))
    images = doc[0].get_images()
    doc.close()
    assert len(images) >= 1


def test_digital_signature_generation_and_valid_verification(sample_pdf, test_credentials, tmp_path):
    cert_pem, key_pem = test_credentials
    signed = tmp_path / "digitally_signed.pdf"
    security_forms_engine.sign_pdf_digitally(
        sample_pdf, signed, cert_pem, key_pem,
        reason="Contract Ratification", location="Paperplane HQ",
        visual_appearance={"page": 0, "rect": [72, 600, 320, 680]}
    )

    report = security_forms_engine.verify_pdf_signatures(signed)
    assert report["is_signed"] is True
    assert report["signature_count"] == 1
    assert report["overall_status"] == "VALID"
    sig = report["signatures"][0]
    assert sig["status"] == "VALID"
    assert sig["tamper_detected"] is False
    assert "Paperplane Test Signer" in sig["certificate"]["subject"]


def test_digital_signature_tamper_detection(sample_pdf, test_credentials, tmp_path):
    cert_pem, key_pem = test_credentials
    signed = tmp_path / "valid_for_tampering.pdf"
    security_forms_engine.sign_pdf_digitally(
        sample_pdf, signed, cert_pem, key_pem,
        reason="Integrity Guarantee"
    )
    # Confirm it's valid first
    report_orig = security_forms_engine.verify_pdf_signatures(signed)
    assert report_orig["overall_status"] == "VALID"

    # Tamper with byte stream outside byte range
    tampered_bytes = bytearray(signed.read_bytes())
    # Alter byte at offset 50 (within range 1 before signature dictionary)
    tampered_bytes[50] = (tampered_bytes[50] + 1) % 256
    tampered_pdf = tmp_path / "tampered.pdf"
    tampered_pdf.write_bytes(tampered_bytes)

    report_tampered = security_forms_engine.verify_pdf_signatures(tampered_pdf)
    assert report_tampered["overall_status"] == "TAMPERED"
    assert report_tampered["signatures"][0]["tamper_detected"] is True


def test_unsigned_pdf_verification(sample_pdf):
    report = security_forms_engine.verify_pdf_signatures(sample_pdf)
    assert report["is_signed"] is False
    assert report["signature_count"] == 0
    assert report["signatures"] == []


# ==============================================================================
# 3. PDF SECURITY ENGINE (ENCRYPTION, PERMISSIONS, UNLOCK, SANITIZE, REDACT)
# ==============================================================================

def test_pdf_encryption_aes256_and_permissions(sample_pdf, tmp_path):
    protected = tmp_path / "protected.pdf"
    security_forms_engine.protect_pdf(
        sample_pdf, protected,
        user_password="userSecret123",
        owner_password="adminSecret456",
        permissions={"allow_printing": False, "allow_copying": False}
    )

    # Document must be encrypted
    doc = fitz.open(str(protected))
    assert doc.is_encrypted is True
    doc.close()

    # Inspection report under user password enforces permission bitmask
    sec_info = security_forms_engine.inspect_pdf_security(protected, password="userSecret123")
    assert sec_info["is_encrypted"] is True
    assert sec_info["encryption_type"] == "AES-256"
    assert sec_info["permissions"]["can_print"] is False
    assert sec_info["permissions"]["can_copy"] is False

    # Master owner password retains full administrative permissions
    sec_info_owner = security_forms_engine.inspect_pdf_security(protected, password="adminSecret456")
    assert sec_info_owner["permissions"]["can_print"] is True


def test_unlock_pdf_with_authentic_password(sample_pdf, tmp_path):
    protected = tmp_path / "locked.pdf"
    security_forms_engine.protect_pdf(
        sample_pdf, protected,
        user_password="pass123",
        owner_password="masterpass456"
    )

    unlocked = tmp_path / "unlocked.pdf"
    security_forms_engine.unlock_pdf(protected, unlocked, password="pass123")

    # Document must now be completely unencrypted
    doc = fitz.open(str(unlocked))
    assert doc.is_encrypted is False
    assert "Customer ID" in doc[0].get_text()
    doc.close()


def test_unlock_pdf_wrong_password_rejected(sample_pdf, tmp_path):
    protected = tmp_path / "locked_strict.pdf"
    security_forms_engine.protect_pdf(sample_pdf, protected, user_password="correct_password")

    unlocked = tmp_path / "fail.pdf"
    with pytest.raises(ValueError, match="Incorrect password"):
        security_forms_engine.unlock_pdf(protected, unlocked, password="wrong_password")


def test_security_inspection_unencrypted(sample_pdf):
    info = security_forms_engine.inspect_pdf_security(sample_pdf)
    assert info["is_encrypted"] is False
    assert info["encryption_type"] is None
    assert info["page_count"] == 1


def test_sanitization_removes_metadata_and_comments(sample_pdf, tmp_path):
    # Add metadata and sticky note comment to source
    doc = fitz.open(str(sample_pdf))
    doc.set_metadata({"title": "Top Secret Document", "author": "Agent Smith"})
    page = doc[0]
    page.add_text_annot(fitz.Point(100, 100), "Sensitive Internal Note")
    annotated = tmp_path / "annotated.pdf"
    doc.save(str(annotated))
    doc.close()

    sanitized = tmp_path / "sanitized.pdf"
    security_forms_engine.sanitize_pdf(annotated, sanitized, {
        "remove_metadata": True,
        "remove_annotations": True,
        "remove_javascript": True
    })

    doc2 = fitz.open(str(sanitized))
    meta = doc2.metadata
    assert not meta.get("title")
    assert not meta.get("author")
    assert len(list(doc2[0].annots())) == 0
    doc2.close()


def test_hardened_redaction_text_glyph_destruction(sample_pdf, tmp_path):
    # Verify sensitive SSN exists prior to redaction
    doc_orig = fitz.open(str(sample_pdf))
    assert "000-12-3456" in doc_orig[0].get_text()
    doc_orig.close()

    redacted = tmp_path / "redacted.pdf"
    security_forms_engine.apply_hardened_redaction(sample_pdf, redacted, [
        {"page": 0, "text": "000-12-3456"}
    ])

    doc_after = fitz.open(str(redacted))
    after_text = doc_after[0].get_text()
    doc_after.close()

    # The character glyphs must be completely destroyed from document stream
    assert "000-12-3456" not in after_text
    assert "Customer ID: CUST-99281" in after_text


def test_hardened_redaction_coordinate_box(sample_pdf, tmp_path):
    redacted = tmp_path / "redacted_box.pdf"
    # Redact top header area
    security_forms_engine.apply_hardened_redaction(sample_pdf, redacted, [
        {"page": 0, "rect": [70, 90, 500, 120]}
    ])
    doc_after = fitz.open(str(redacted))
    after_text = doc_after[0].get_text()
    doc_after.close()
    assert "Confidential Record" not in after_text


# ==============================================================================
# 4. FASTAPI STUDIO ENDPOINTS INTEGRATION TESTS
# ==============================================================================

def test_api_studio_forms_lifecycle(sample_pdf):
    # 1. Add field via API
    add_resp = client.post(
        "/api/studio/forms/add-field",
        files={"file": ("doc.pdf", sample_pdf.read_bytes(), "application/pdf")},
        data={"field_data": json.dumps({"page": 0, "type": "text", "name": "api_field", "rect": [50, 50, 200, 80], "value": "Initial"})}
    )
    assert add_resp.status_code == 200
    pdf_with_field = add_resp.content

    # 2. Analyze form fields via API
    analyze_resp = client.post(
        "/api/studio/forms/analyze",
        files={"file": ("doc.pdf", pdf_with_field, "application/pdf")}
    )
    assert analyze_resp.status_code == 200
    data = analyze_resp.json()
    assert data["field_count"] >= 1
    assert any(f["field_name"] == "api_field" for f in data["fields"])

    # 3. Fill form field via API
    fill_resp = client.post(
        "/api/studio/forms/fill",
        files={"file": ("doc.pdf", pdf_with_field, "application/pdf")},
        data={"field_values": json.dumps({"api_field": "Updated via API"})}
    )
    assert fill_resp.status_code == 200
    pdf_filled = fill_resp.content

    # 4. Export form field via API
    export_resp = client.post(
        "/api/studio/forms/export",
        files={"file": ("doc.pdf", pdf_filled, "application/pdf")}
    )
    assert export_resp.status_code == 200
    exported_json = export_resp.json()
    assert exported_json.get("api_field") == "Updated via API"

    # 5. Flatten form fields via API
    flat_resp = client.post(
        "/api/studio/forms/flatten",
        files={"file": ("doc.pdf", pdf_filled, "application/pdf")}
    )
    assert flat_resp.status_code == 200
    flat_analyze = client.post(
        "/api/studio/forms/analyze",
        files={"file": ("doc.pdf", flat_resp.content, "application/pdf")}
    ).json()
    assert flat_analyze["field_count"] == 0


def test_api_studio_security_protect_and_unlock(sample_pdf):
    # 1. Protect PDF
    prot_resp = client.post(
        "/api/studio/security/protect",
        files={"file": ("doc.pdf", sample_pdf.read_bytes(), "application/pdf")},
        data={"user_password": "apiPassword456", "owner_password": "apiAdminPassword789"}
    )
    assert prot_resp.status_code == 200
    protected_pdf = prot_resp.content

    # 2. Inspect security
    insp_resp = client.post(
        "/api/studio/security/inspect",
        files={"file": ("doc.pdf", protected_pdf, "application/pdf")},
        data={"password": "apiAdminPassword789"}
    )
    assert insp_resp.status_code == 200
    sec_info = insp_resp.json()
    assert sec_info["is_encrypted"] is True

    # 3. Unlock PDF
    unlock_resp = client.post(
        "/api/studio/security/unlock",
        files={"file": ("doc.pdf", protected_pdf, "application/pdf")},
        data={"password": "apiPassword456"}
    )
    assert unlock_resp.status_code == 200
    unlocked_pdf = unlock_resp.content

    # Verify unlocked is unencrypted
    unlocked_info = client.post(
        "/api/studio/security/inspect",
        files={"file": ("doc.pdf", unlocked_pdf, "application/pdf")}
    ).json()
    assert unlocked_info["is_encrypted"] is False


def test_api_studio_digital_signing_and_verification(sample_pdf):
    # Sign digitally
    sign_resp = client.post(
        "/api/studio/sign/digital",
        files={"file": ("doc.pdf", sample_pdf.read_bytes(), "application/pdf")},
        data={"signer_name": "API Compliance Officer", "reason": "Audit Approved"}
    )
    assert sign_resp.status_code == 200
    signed_pdf = sign_resp.content

    # Verify signature
    verify_resp = client.post(
        "/api/studio/sign/verify",
        files={"file": ("doc.pdf", signed_pdf, "application/pdf")}
    )
    assert verify_resp.status_code == 200
    v_report = verify_resp.json()
    assert v_report["is_signed"] is True
    assert v_report["overall_status"] == "VALID"


def test_api_studio_security_redaction(sample_pdf):
    redact_resp = client.post(
        "/api/studio/security/redact",
        files={"file": ("doc.pdf", sample_pdf.read_bytes(), "application/pdf")},
        data={"redactions": json.dumps([{"page": 0, "text": "Customer ID"}])}
    )
    assert redact_resp.status_code == 200
    doc = fitz.open(stream=redact_resp.content, filetype="pdf")
    text = doc[0].get_text()
    doc.close()
    assert "Customer ID" not in text
    assert "SSN" in text


def test_api_rejection_of_invalid_pdf():
    resp = client.post(
        "/api/studio/forms/analyze",
        files={"file": ("bad.pdf", b"NOT A REAL PDF CONTENT", "application/pdf")}
    )
    assert resp.status_code in (400, 422)
