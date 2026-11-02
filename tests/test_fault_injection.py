from __future__ import annotations

import pathlib
import pytest
import fitz
from fastapi.testclient import TestClient

import converters
import security_forms_engine
from server import (
    app,
    process,
    run_converter_with_timeout,
    COMPRESS_TIMEOUT_SECONDS,
    OCR_TIMEOUT_SECONDS,
    GRAYSCALE_TIMEOUT_SECONDS
)

client = TestClient(app)


@pytest.fixture
def synthetic_pdf(tmp_path: pathlib.Path) -> pathlib.Path:
    """Generates a synthetic PDF document for testing fault boundaries."""
    pdf_path = tmp_path / "fault_test_doc.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "Synthetic Document for Fault Injection and Timeout Testing", fontsize=14)
    page.insert_text((72, 140), "Standard sample payload text for OCR, compression and grayscale tests.", fontsize=10)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def encrypted_synthetic_pdf(synthetic_pdf: pathlib.Path, tmp_path: pathlib.Path) -> pathlib.Path:
    """Generates an encrypted synthetic PDF document."""
    enc_path = tmp_path / "encrypted_doc.pdf"
    security_forms_engine.protect_pdf(synthetic_pdf, enc_path, user_password="TestEncryptedPassword123")
    return enc_path


# ==============================================================================
# 1. TIMEOUT FAULT INJECTION (COMPRESS, OCR, GRAYSCALE)
# ==============================================================================

def test_compress_timeout_fault_injection(synthetic_pdf: pathlib.Path, tmp_path: pathlib.Path, monkeypatch):
    """Proves: Compress timeout returns clean TimeoutError / HTTP 504 JSON, never 502 or partial output."""
    partial_output = tmp_path / "partial_compress.pdf"
    partial_output.write_bytes(b"%PDF-1.4 partial corrupt data")

    def mock_hanging_compress(*args, **kwargs):
        import time
        time.sleep(2.0)
        return {"output_size": 100}

    monkeypatch.setattr(converters, "compress_pdf", mock_hanging_compress)

    # 1. Test runner helper / process() timeout handling
    with pytest.raises(TimeoutError) as exc_info:
        run_converter_with_timeout(
            converters.compress_pdf,
            synthetic_pdf, partial_output,
            timeout_seconds=0.1,
            tool_name="compress",
            source_path=synthetic_pdf,
            output_path=partial_output,
            retry_hint="Try lower resolution."
        )

    assert "Compress processing timed out" in str(exc_info.value)
    assert "Try lower resolution." in str(exc_info.value)
    # Ensure partial file was unlinked and cleaned up
    assert not partial_output.exists()

    # 2. Test Studio endpoint HTTP response under timeout
    monkeypatch.setattr("server.COMPRESS_TIMEOUT_SECONDS", 0.1)
    resp = client.post(
        "/api/studio/compress",
        files={"file": ("doc.pdf", synthetic_pdf.read_bytes(), "application/pdf")},
        data={"preset": "balanced"}
    )
    assert resp.status_code == 504
    data = resp.json()
    assert data["ok"] is False
    assert "timed out" in data["error"].lower()
    assert "retry_hint" in data
    assert resp.headers["content-type"].startswith("application/json")


def test_ocr_timeout_fault_injection(synthetic_pdf: pathlib.Path, tmp_path: pathlib.Path, monkeypatch):
    """Proves: OCR timeout returns clean TimeoutError / HTTP 504 JSON, never 502 or partial output."""
    partial_output = tmp_path / "partial_ocr.pdf"
    partial_output.write_bytes(b"%PDF-1.4 partial corrupt ocr data")

    def mock_hanging_ocr(*args, **kwargs):
        import time
        time.sleep(2.0)
        return {"pages_ocrd": 0}

    monkeypatch.setattr(converters, "ocr_pdf", mock_hanging_ocr)

    # 1. Test runner helper / process() timeout handling
    with pytest.raises(TimeoutError) as exc_info:
        run_converter_with_timeout(
            converters.ocr_pdf,
            synthetic_pdf, partial_output,
            timeout_seconds=0.1,
            tool_name="ocr",
            source_path=synthetic_pdf,
            output_path=partial_output,
            retry_hint="Try smaller page selection."
        )

    assert "Ocr processing timed out" in str(exc_info.value)
    assert "Try smaller page selection." in str(exc_info.value)
    assert not partial_output.exists()

    # 2. Test Studio endpoint HTTP response under timeout
    monkeypatch.setattr("server.OCR_TIMEOUT_SECONDS", 0.1)
    resp = client.post(
        "/api/studio/ocr",
        files={"file": ("doc.pdf", synthetic_pdf.read_bytes(), "application/pdf")},
        data={"language": "eng", "pages": "all", "mode": "all", "dpi": "150"}
    )
    assert resp.status_code == 504
    data = resp.json()
    assert data["ok"] is False
    assert "timed out" in data["error"].lower()
    assert "retry_hint" in data
    assert resp.headers["content-type"].startswith("application/json")


def test_grayscale_timeout_fault_injection(synthetic_pdf: pathlib.Path, tmp_path: pathlib.Path, monkeypatch):
    """Proves: Grayscale timeout returns clean TimeoutError with retry hint and cleans up partials."""
    partial_output = tmp_path / "partial_gray.pdf"
    partial_output.write_bytes(b"%PDF-1.4 partial corrupt gray data")

    def mock_hanging_grayscale(*args, **kwargs):
        import time
        time.sleep(2.0)
        return {"page_count": 1}

    monkeypatch.setattr(converters, "convert_pdf_to_grayscale", mock_hanging_grayscale)

    with pytest.raises(TimeoutError) as exc_info:
        run_converter_with_timeout(
            converters.convert_pdf_to_grayscale,
            synthetic_pdf, partial_output,
            timeout_seconds=0.1,
            tool_name="grayscale",
            source_path=synthetic_pdf,
            output_path=partial_output,
            retry_hint="Try splitting the PDF."
        )

    assert "Grayscale processing timed out" in str(exc_info.value)
    assert "Try splitting the PDF." in str(exc_info.value)
    assert not partial_output.exists()


# ==============================================================================
# 2. UPSTREAM EXCEPTION FAULT INJECTION (COMPRESS, OCR)
# ==============================================================================

def test_compress_upstream_exception_fault_injection(synthetic_pdf: pathlib.Path, monkeypatch):
    """Proves: Unhandled upstream converter exception returns HTTP 500 JSON with retry hint, not 502."""
    def mock_failing_compress(*args, **kwargs):
        raise RuntimeError("PyMuPDF internal error: corrupt image cross-reference table")

    monkeypatch.setattr(converters, "compress_pdf", mock_failing_compress)

    resp = client.post(
        "/api/studio/compress",
        files={"file": ("doc.pdf", synthetic_pdf.read_bytes(), "application/pdf")},
        data={"preset": "balanced"}
    )
    assert resp.status_code == 500
    data = resp.json()
    assert data["ok"] is False
    assert "Compression failed" in data["error"]
    assert "corrupt image" in data["error"]
    assert "retry_hint" in data
    assert resp.headers["content-type"].startswith("application/json")


def test_ocr_upstream_exception_fault_injection(synthetic_pdf: pathlib.Path, monkeypatch):
    """Proves: Upstream OCR worker failure returns HTTP 500 JSON with retry hint, not 502."""
    def mock_failing_ocr(*args, **kwargs):
        raise RuntimeError("Tesseract engine worker failure: segfault code 139")

    monkeypatch.setattr(converters, "ocr_pdf", mock_failing_ocr)

    resp = client.post(
        "/api/studio/ocr",
        files={"file": ("doc.pdf", synthetic_pdf.read_bytes(), "application/pdf")},
        data={"language": "eng", "pages": "all", "mode": "all", "dpi": "150"}
    )
    assert resp.status_code == 500
    data = resp.json()
    assert data["ok"] is False
    assert "OCR processing failed" in data["error"]
    assert "Tesseract engine" in data["error"]
    assert "retry_hint" in data
    assert resp.headers["content-type"].startswith("application/json")


# ==============================================================================
# 3. ENCRYPTED INPUT GUARDS (COMPRESS, OCR, GRAYSCALE)
# ==============================================================================

def test_encrypted_input_rejected_cleanly_across_tools(encrypted_synthetic_pdf: pathlib.Path, tmp_path: pathlib.Path):
    """Proves: Password-protected input is proactively rejected with clean 400 error across all tools."""
    # 1. Direct converter call checks
    out1 = tmp_path / "out1.pdf"
    with pytest.raises(ValueError, match="This document is password-protected. Please unlock it before compressing."):
        converters.compress_pdf(encrypted_synthetic_pdf, out1)

    out2 = tmp_path / "out2.pdf"
    with pytest.raises(ValueError, match="This document is password-protected. Please unlock it before running OCR."):
        converters.ocr_pdf(encrypted_synthetic_pdf, out2)

    out3 = tmp_path / "out3.pdf"
    with pytest.raises(ValueError, match="This document is password-protected. Please unlock it before converting to grayscale."):
        converters.convert_pdf_to_grayscale(encrypted_synthetic_pdf, out3)

    # 2. Studio API endpoints return clean 400 JSON responses
    resp_comp = client.post(
        "/api/studio/compress",
        files={"file": ("enc.pdf", encrypted_synthetic_pdf.read_bytes(), "application/pdf")},
        data={"preset": "balanced"}
    )
    assert resp_comp.status_code == 400
    assert "password-protected" in resp_comp.json()["error"]

    resp_ocr = client.post(
        "/api/studio/ocr",
        files={"file": ("enc.pdf", encrypted_synthetic_pdf.read_bytes(), "application/pdf")},
        data={"language": "eng", "pages": "all", "mode": "all", "dpi": "150"}
    )
    assert resp_ocr.status_code == 400
    assert "password-protected" in resp_ocr.json()["error"]


# ==============================================================================
# 4. NORMAL EXECUTION WITHOUT FAULTS
# ==============================================================================

def test_normal_compress_ocr_grayscale_success(synthetic_pdf: pathlib.Path, tmp_path: pathlib.Path):
    """Proves: Uninterrupted runs of Compress, OCR, and Grayscale succeed without error."""
    # Compress
    out_comp = tmp_path / "success_compress.pdf"
    rep_comp = converters.compress_pdf(synthetic_pdf, out_comp, preset="balanced")
    assert out_comp.exists()
    assert rep_comp["page_count"] == 1

    # OCR
    out_ocr = tmp_path / "success_ocr.pdf"
    rep_ocr = converters.ocr_pdf(synthetic_pdf, out_ocr, language="eng", pages="all")
    assert out_ocr.exists()
    assert rep_ocr["success"] is True

    # Grayscale
    out_gray = tmp_path / "success_gray.pdf"
    rep_gray = converters.convert_pdf_to_grayscale(synthetic_pdf, out_gray)
    assert out_gray.exists()
    assert rep_gray["page_count"] == 1
