from __future__ import annotations

import pathlib
import pytest
import fitz
from fastapi.testclient import TestClient

import security_forms_engine
from server import app, process

client = TestClient(app)

TEST_USER_PASSWORD = "SyntheticUserPass2026!"
TEST_OWNER_PASSWORD = "SyntheticOwnerPass2026!"
WRONG_PASSWORD = "CompletelyWrongPassword999!"


@pytest.fixture
def synthetic_pdf(tmp_path: pathlib.Path) -> pathlib.Path:
    """Creates a minimal 2-page synthetic PDF fixture entirely in memory."""
    pdf_path = tmp_path / "synthetic_doc.pdf"
    doc = fitz.open()
    
    page1 = doc.new_page(width=612, height=792)
    page1.insert_text((72, 100), "Synthetic Document - Page 1 Confidential Payload", fontsize=14)
    page1.insert_text((72, 140), "Account Number: ACC-TEST-88192, Status: Active", fontsize=11)
    
    page2 = doc.new_page(width=612, height=792)
    page2.insert_text((72, 100), "Synthetic Document - Page 2 Verification Data", fontsize=14)
    page2.insert_text((72, 140), "Checksum: SHA256-TEST-OK", fontsize=11)
    
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def test_protect_pdf_creates_encrypted_output(synthetic_pdf: pathlib.Path, tmp_path: pathlib.Path):
    """Proves: Protect with a test password produces an encrypted PDF (opening without password fails)."""
    protected_pdf = tmp_path / "protected.pdf"
    result = security_forms_engine.protect_pdf(
        synthetic_pdf,
        protected_pdf,
        user_password=TEST_USER_PASSWORD,
        owner_password=TEST_OWNER_PASSWORD
    )
    assert result == protected_pdf
    assert protected_pdf.exists()
    assert protected_pdf.stat().st_size > 0

    # Verify file is truly encrypted
    doc = fitz.open(str(protected_pdf))
    assert doc.is_encrypted is True
    assert doc.needs_pass == 1

    # Attempting to read content without authentication must fail
    with pytest.raises(ValueError, match="document closed or encrypted"):
        _ = doc[0].get_text()

    # Wrong password authentication returns 0
    assert doc.authenticate(WRONG_PASSWORD) == 0

    # Correct user password authenticates successfully
    auth_result = doc.authenticate(TEST_USER_PASSWORD)
    assert auth_result > 0
    assert "Page 1 Confidential Payload" in doc[0].get_text()
    doc.close()


def test_unlock_with_correct_password_returns_readable_pdf(synthetic_pdf: pathlib.Path, tmp_path: pathlib.Path):
    """Proves: Unlock with the CORRECT test password succeeds and returns a readable unencrypted PDF."""
    protected_pdf = tmp_path / "protected_to_unlock.pdf"
    security_forms_engine.protect_pdf(synthetic_pdf, protected_pdf, user_password=TEST_USER_PASSWORD)

    unlocked_pdf = tmp_path / "unlocked.pdf"
    result = security_forms_engine.unlock_pdf(protected_pdf, unlocked_pdf, password=TEST_USER_PASSWORD)
    assert result == unlocked_pdf
    assert unlocked_pdf.exists()
    assert unlocked_pdf.stat().st_size > 0

    # Output must be completely unencrypted and readable without any password
    doc = fitz.open(str(unlocked_pdf))
    assert doc.is_encrypted is False
    assert doc.needs_pass == 0
    assert len(doc) == 2
    assert "Page 1 Confidential Payload" in doc[0].get_text()
    assert "Page 2 Verification Data" in doc[1].get_text()
    doc.close()


def test_unlock_with_wrong_password_fails_explicitly(synthetic_pdf: pathlib.Path, tmp_path: pathlib.Path):
    """Proves: Unlock with a WRONG password fails with a clean, explicit error (not silent success)."""
    protected_pdf = tmp_path / "protected_wrong.pdf"
    security_forms_engine.protect_pdf(synthetic_pdf, protected_pdf, user_password=TEST_USER_PASSWORD)

    unlocked_pdf = tmp_path / "never_created.pdf"
    with pytest.raises(ValueError, match="Incorrect password provided for document unlock."):
        security_forms_engine.unlock_pdf(protected_pdf, unlocked_pdf, password=WRONG_PASSWORD)

    assert not unlocked_pdf.exists()


def test_unlock_with_empty_or_whitespace_password_rejected(synthetic_pdf: pathlib.Path, tmp_path: pathlib.Path):
    """Proves: Unlock with an empty or whitespace password is rejected cleanly."""
    protected_pdf = tmp_path / "protected_empty.pdf"
    security_forms_engine.protect_pdf(synthetic_pdf, protected_pdf, user_password=TEST_USER_PASSWORD)

    unlocked_pdf = tmp_path / "never_created_empty.pdf"
    for empty_pw in ("", "   ", "\t\n"):
        with pytest.raises(ValueError, match="Please provide the password to unlock this protected PDF."):
            security_forms_engine.unlock_pdf(protected_pdf, unlocked_pdf, password=empty_pw)
        assert not unlocked_pdf.exists()


def test_protect_with_empty_passwords_rejected(synthetic_pdf: pathlib.Path, tmp_path: pathlib.Path):
    """Proves: Protect with empty user and owner passwords is clean rejected."""
    out_pdf = tmp_path / "never_created_prot.pdf"
    for empty_pw in ("", "   "):
        with pytest.raises(ValueError, match="A non-empty password is required to encrypt this PDF."):
            security_forms_engine.protect_pdf(synthetic_pdf, out_pdf, user_password=empty_pw, owner_password=empty_pw)
        assert not out_pdf.exists()


def test_protect_already_protected_pdf_rejected(synthetic_pdf: pathlib.Path, tmp_path: pathlib.Path):
    """Proves: Applying protection to an already-protected document raises a clean error."""
    protected_pdf = tmp_path / "already_prot.pdf"
    security_forms_engine.protect_pdf(synthetic_pdf, protected_pdf, user_password=TEST_USER_PASSWORD)

    out_pdf = tmp_path / "double_protected.pdf"
    with pytest.raises(ValueError, match="This document is already password-protected. Please unlock it before applying new protection."):
        security_forms_engine.protect_pdf(protected_pdf, out_pdf, user_password="AnotherPassword123")
    assert not out_pdf.exists()


def test_unlock_unencrypted_pdf_rejected(synthetic_pdf: pathlib.Path, tmp_path: pathlib.Path):
    """Proves: Calling unlock on an unencrypted document raises a clean error."""
    unlocked_pdf = tmp_path / "unneeded_unlock.pdf"
    with pytest.raises(ValueError, match="The provided document is not password-protected."):
        security_forms_engine.unlock_pdf(synthetic_pdf, unlocked_pdf, password=TEST_USER_PASSWORD)
    assert not unlocked_pdf.exists()


def test_api_studio_protect_and_unlock_clean_json_errors(synthetic_pdf: pathlib.Path):
    """Proves: Studio API endpoints return clean 400 JSON errors, never 500 or misleading HTML."""
    # 1. Protect with empty password -> 400 Bad Request
    resp = client.post(
        "/api/studio/security/protect",
        files={"file": ("doc.pdf", synthetic_pdf.read_bytes(), "application/pdf")},
        data={"user_password": "", "owner_password": ""}
    )
    assert resp.status_code == 400
    err_body = resp.json()
    assert err_body["ok"] is False
    assert "A non-empty password is required" in err_body["error"]
    assert "retry_hint" in err_body

    # 2. Protect with valid password -> 200 OK
    resp_prot = client.post(
        "/api/studio/security/protect",
        files={"file": ("doc.pdf", synthetic_pdf.read_bytes(), "application/pdf")},
        data={"user_password": TEST_USER_PASSWORD, "owner_password": TEST_OWNER_PASSWORD}
    )
    assert resp_prot.status_code == 200
    assert resp_prot.headers["content-type"] == "application/pdf"
    prot_bytes = resp_prot.content

    # 3. Unlock with empty password -> 400 Bad Request
    resp_empty = client.post(
        "/api/studio/security/unlock",
        files={"file": ("doc.pdf", prot_bytes, "application/pdf")},
        data={"password": "   "}
    )
    assert resp_empty.status_code == 400
    err_empty = resp_empty.json()
    assert err_empty["ok"] is False
    assert "Please provide the password to unlock this protected PDF." in err_empty["error"]

    # 4. Unlock with wrong password -> 400 Bad Request (NOT 500)
    resp_wrong = client.post(
        "/api/studio/security/unlock",
        files={"file": ("doc.pdf", prot_bytes, "application/pdf")},
        data={"password": WRONG_PASSWORD}
    )
    assert resp_wrong.status_code == 400
    err_wrong = resp_wrong.json()
    assert err_wrong["ok"] is False
    assert "Incorrect password provided for document unlock." in err_wrong["error"]

    # 5. Unlock on unencrypted PDF -> 400 Bad Request
    resp_unenc = client.post(
        "/api/studio/security/unlock",
        files={"file": ("doc.pdf", synthetic_pdf.read_bytes(), "application/pdf")},
        data={"password": TEST_USER_PASSWORD}
    )
    assert resp_unenc.status_code == 400
    err_unenc = resp_unenc.json()
    assert err_unenc["ok"] is False
    assert "The provided document is not password-protected." in err_unenc["error"]

    # 6. Unlock with correct password -> 200 OK
    resp_ok = client.post(
        "/api/studio/security/unlock",
        files={"file": ("doc.pdf", prot_bytes, "application/pdf")},
        data={"password": TEST_USER_PASSWORD}
    )
    assert resp_ok.status_code == 200
    assert resp_ok.headers["content-type"] == "application/pdf"
    unl_doc = fitz.open(stream=resp_ok.content, filetype="pdf")
    assert unl_doc.is_encrypted is False
    assert unl_doc.needs_pass == 0
    assert "Page 1 Confidential Payload" in unl_doc[0].get_text()
    unl_doc.close()


def test_process_dispatch_protect_and_unlock_roundtrip(synthetic_pdf: pathlib.Path, tmp_path: pathlib.Path):
    """Proves: Job runner process() dispatch handles Protect and Unlock cleanly."""
    job_dir_1 = tmp_path / "job_protect"
    job_dir_1.mkdir()
    prot_res = process("protect", [synthetic_pdf], {"password": TEST_USER_PASSWORD}, job_dir_1)
    assert prot_res.exists()
    
    doc = fitz.open(str(prot_res))
    assert doc.is_encrypted is True
    doc.close()

    job_dir_2 = tmp_path / "job_unlock"
    job_dir_2.mkdir()
    unl_res = process("unlock", [prot_res], {"password": TEST_USER_PASSWORD}, job_dir_2)
    assert unl_res.exists()

    unl_doc = fitz.open(str(unl_res))
    assert unl_doc.is_encrypted is False
    assert "Page 1 Confidential Payload" in unl_doc[0].get_text()
    unl_doc.close()

    # Wrong password in process("unlock") raises clean ValueError
    job_dir_3 = tmp_path / "job_wrong"
    job_dir_3.mkdir()
    with pytest.raises(ValueError, match="Incorrect password provided for document unlock."):
        process("unlock", [prot_res], {"password": WRONG_PASSWORD}, job_dir_3)
