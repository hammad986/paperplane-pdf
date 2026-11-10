from __future__ import annotations

import base64
from pathlib import Path

import fitz
from fastapi.testclient import TestClient

import ai_engine
import server


def make_pdf_bytes(pages: int = 2) -> bytes:
    document = fitz.open()
    for index in range(1, pages + 1):
        page = document.new_page()
        page.insert_text((72, 72), f"Audit fixture page {index}")
    payload = document.tobytes()
    document.close()
    return payload


def test_cloud_import_reports_pdf_page_count_and_sanitized_original_name(monkeypatch):
    pdf_bytes = make_pdf_bytes(3)
    fetched_urls: list[str] = []

    def fake_fetch(url, max_size, timeout, response_metadata):
        fetched_urls.append(url)
        response_metadata.update({
            "content_disposition": "attachment; filename*=UTF-8''notes%20test.pdf",
            "final_url": "https://drive.google.com/uc?export=download&id=test-id",
        })
        return pdf_bytes, "application/pdf"

    monkeypatch.setattr(server.converters, "safe_fetch_url", fake_fetch)
    response = TestClient(server.app).post(
        "/api/cloud/sync",
        data={"file_url": "https://drive.google.com/file/d/test-id/view?usp=sharing", "provider": "direct"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filename"] == "notes test.pdf"
    assert payload["page_count"] == 3
    assert payload["size"] == len(pdf_bytes)
    assert base64.b64decode(payload["data_url"].split(",", 1)[1]) == pdf_bytes
    assert fetched_urls == ["https://drive.google.com/uc?export=download&confirm=t&id=test-id"]


def test_cloud_import_does_not_rewrite_a_lookalike_drive_hostname(monkeypatch):
    pdf_bytes = make_pdf_bytes(1)
    requested_url = "https://drive.google.com.evil.invalid/file/d/not-a-drive-id/view"
    fetched_urls: list[str] = []

    def fake_fetch(url, max_size, timeout, response_metadata):
        fetched_urls.append(url)
        response_metadata["final_url"] = url
        return pdf_bytes, "application/pdf"

    monkeypatch.setattr(server.converters, "safe_fetch_url", fake_fetch)
    response = TestClient(server.app).post("/api/cloud/sync", data={"file_url": requested_url})

    assert response.status_code == 200
    assert fetched_urls == [requested_url]
    assert response.json()["provider"] == "direct"


def test_cloud_import_rejects_embedded_credentials_before_fetch(monkeypatch):
    fetched: list[str] = []
    monkeypatch.setattr(server.converters, "safe_fetch_url", lambda url, **kwargs: fetched.append(url))

    response = TestClient(server.app).post(
        "/api/cloud/sync",
        data={"file_url": "https://drive.google.com@attacker.invalid/file/d/test/view"},
    )

    assert response.status_code == 400
    assert "credentials" in response.json()["detail"]
    assert fetched == []


def test_ai_connection_success_text_does_not_claim_workflows_are_healthy(monkeypatch):
    monkeypatch.setattr(
        ai_engine,
        "test_bluesminds_connectivity",
        lambda: {"status": "connected", "http_status": 200},
    )

    response = TestClient(server.app).get("/api/ai/test-connection")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "connected"
    assert "Short AI connection check passed" in payload["message"]
    assert "Full PDF workflows can still fail or time out" in payload["message"]


def test_ai_panels_keep_reserved_runtime_and_result_regions():
    html = (Path(__file__).resolve().parents[1] / "web" / "index.html").read_text(encoding="utf-8")
    css = (Path(__file__).resolve().parents[1] / "web" / "assets" / "styles.css").read_text(encoding="utf-8")
    javascript = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")

    assert 'class="summary-runtime-slot"' in html
    assert 'class="summary-actions-slot"' in html
    assert 'id="extract-runtime-status"' in html
    assert 'id="extract-cancel-btn"' in html
    assert "summary-runtime-slot" in css and "extract-runtime-slot" in css
    assert "summaryRequestTimedOut" in javascript and "extractionRequestTimedOut" in javascript
    assert "waiting for the AI service response" in javascript


def test_studio_mobile_page_actions_have_a_dedicated_panel_slot():
    html = (Path(__file__).resolve().parents[1] / "web" / "index.html").read_text(encoding="utf-8")
    javascript = (Path(__file__).resolve().parents[1] / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    css = (Path(__file__).resolve().parents[1] / "web" / "assets" / "styles.css").read_text(encoding="utf-8")

    assert 'id="studio-mobile-page-actions-slot"' in html
    assert "studio-mobile-page-actions-slot" in javascript
    assert "studio-mobile-page-actions" in css


def test_plan_limits_and_photo_resizer_names_are_explicit_and_consistent():
    root = Path(__file__).resolve().parents[1]
    html = (root / "web" / "index.html").read_text(encoding="utf-8")
    javascript = (root / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    backend = (root / "server.py").read_text(encoding="utf-8")

    assert "Free web tools:" in html
    assert "Paid web tools: no daily operation cap" in html
    assert "Developer API quotas are separate." not in javascript
    assert "Compare accepts 2 files; other tools accept 1 file per run." in html
    assert '"label": "Exam Photo & Signature Resizer"' in backend
    assert '"heading": "Exam Photo & Signature Resizer for SSC & UPSC"' in backend
    assert "FREE SOVEREIGN" not in html + javascript

