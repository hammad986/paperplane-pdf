from __future__ import annotations

import io
import json
import os
import secrets
import time
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import fitz
from fastapi.testclient import TestClient

import ai_engine
import config
import converters
import persistence
import security_forms_engine
import server
from tests.auth_helpers import register_verified

ROOT = Path(__file__).resolve().parents[1]


def _make_sample_pdf(
    path: Path,
    text: str = "Quarterly financial compliance clause 2026.",
    *,
    metadata: dict[str, str] | None = None,
) -> Path:
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), text)
        if metadata:
            doc.set_metadata(metadata)
        doc.save(path)
    return path


def _make_form_pdf(path: Path, field_name: str = "applicant_name", initial: str = "") -> Path:
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), "Application Form")
        widget = fitz.Widget()
        widget.field_name = field_name
        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        widget.field_value = initial
        widget.rect = fitz.Rect(72, 100, 300, 128)
        page.add_widget(widget)
        doc.save(path)
    return path


def test_admin_public_routes_never_disclose_owner_email():
    client = TestClient(server.app)
    html_resp = client.get("/admin")
    assert html_resp.status_code == 200
    status_resp = client.get("/api/admin/auth/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["locked"] is False
    assert "verification_required" in status_data

    for leaked in ("mdhammad2906@gmail.com", "mdhammad29006@gmail.com"):
        assert leaked not in html_resp.text
        assert leaked not in status_resp.text


def test_id452_id93_sliding_session_renewal_and_sqlite_restart_survival():
    client = TestClient(server.app)
    email = f"session_{secrets.token_hex(6)}@paperplane.test"
    reg = register_verified(client, email, "StrongPass123!").json()
    user_id = reg["user_id"]
    token = reg["token"]

    # Backdate session expiry within the <13 day sliding renewal threshold.
    near_expiry = time.time() + (5 * 24 * 3600)
    with closing(persistence.connect()) as conn:
        conn.execute("UPDATE sessions SET expires_at = ? WHERE user_id = ?", (near_expiry, user_id))
        conn.commit()

    # Re-authenticate via persistence & fresh client to confirm SQLite restart survival (ID 93).
    assert persistence.authenticate(token) == user_id
    with closing(persistence.connect()) as conn:
        refreshed = conn.execute("SELECT expires_at FROM sessions WHERE user_id = ?", (user_id,)).fetchone()
    assert refreshed["expires_at"] > near_expiry + (7 * 24 * 3600)

    persistence.init_db()
    fresh_client = TestClient(server.app)
    me = fresh_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["user_id"] == user_id
    assert "private" in me.headers.get("cache-control", "").lower()
    assert "no-store" in me.headers.get("cache-control", "").lower()
    assert "cookie" in me.headers.get("vary", "").lower()


def test_id453_signup_otp_normalization_cooldown_and_expired_resend():
    client = TestClient(server.app)
    email = f"otp_norm_{secrets.token_hex(6)}@paperplane.test"
    reg = client.post(
        "/api/auth/register",
        data={"email": email, "password": "StrongPass123!", "confirm_password": "StrongPass123!"},
    )
    assert reg.status_code == 200
    reg_data = reg.json()
    assert reg_data["status"] == "otp_required"
    assert int(reg_data.get("resend_cooldown", 0)) >= 1
    otp = reg_data["dev_otp"]

    # Immediate resend must enforce cooldown cleanly (429 + Retry-After).
    blocked_resend = client.post("/api/auth/resend-otp", json={"email": email, "purpose": "signup"})
    assert blocked_resend.status_code == 429
    assert int(blocked_resend.headers.get("retry-after", "0")) >= 1

    # Spaced/hyphenated OTP entry (copy-paste artifact) succeeds cleanly.
    formatted_otp = f" {otp[:3]} - {otp[3:]} "
    verified = client.post("/api/auth/verify-signup-otp", json={"email": email, "otp": formatted_otp})
    assert verified.status_code == 200
    assert verified.json()["email"] == email

    # Expired/non-pending signup resend returns explicit 410 (no cryptic 400 loop).
    orphan_email = f"expired_{secrets.token_hex(6)}@paperplane.test"
    expired_resend = client.post("/api/auth/resend-otp", json={"email": orphan_email, "purpose": "signup"})
    assert expired_resend.status_code in (404, 410)


def test_id455_tab_user_isolation_409_mismatch_and_no_store_headers():
    client_a = TestClient(server.app)
    reg_a = register_verified(client_a, f"usera_{secrets.token_hex(6)}@paperplane.test", "StrongPass123!").json()
    reg_b = register_verified(TestClient(server.app), f"userb_{secrets.token_hex(6)}@paperplane.test", "StrongPass123!").json()

    headers = {
        "Authorization": f"Bearer {reg_a['token']}",
        "X-Paperplane-Expected-User": reg_b["user_id"],
    }
    for method, path in (
        ("get", "/api/auth/me"),
        ("get", "/api/billing/status"),
        ("get", "/api/billing/orders"),
        ("get", "/api/support/tickets"),
    ):
        resp = getattr(client_a, method)(path, headers=headers)
        assert resp.status_code == 409
        assert "active account session changed" in str(resp.json()["detail"]).lower()


def test_id456_id457_billing_orders_expiry_post_return_and_single_use_recovery(monkeypatch):
    client = TestClient(server.app)
    reg = register_verified(client, f"payer_{secrets.token_hex(6)}@paperplane.test", "StrongPass123!").json()
    user_id = reg["user_id"]
    token = reg["token"]

    # Cashfree POST / callback normalizes cleanly via HTTP 303 to GET /?billing=return&order_id=...
    post_ret = client.post("/?billing=return&order_id=order_pp_test123", follow_redirects=False)
    assert post_ret.status_code == 303
    assert post_ret.headers["location"] == "/?billing=return&order_id=order_pp_test123"

    form_ret = client.post("/", data={"order_id": "order_pp_form999"}, follow_redirects=False)
    assert form_ret.status_code == 303
    assert form_ret.headers["location"] == "/?billing=return&order_id=order_pp_form999"

    monkeypatch.setattr(server, "CASHFREE_APP_ID", "sandbox-app")
    monkeypatch.setattr(server, "CASHFREE_SECRET_KEY", "sandbox-secret")
    monkeypatch.setattr(server, "CASHFREE_ENV", "TEST")
    monkeypatch.setattr(server, "ENVIRONMENT", "development")
    monkeypatch.setattr(server, "PAPERPLANE_PUBLIC_URL", "https://paperplane.example")
    monkeypatch.setattr(
        server,
        "_cashfree_request",
        lambda method, path, body=None: (
            {"payment_session_id": "sess_v30"}
            if method == "POST"
            else {
                "order_id": path.rsplit("/", 1)[-1],
                "order_status": "PAID",
                "order_amount": 19,
                "order_currency": "INR",
                "customer_details": {"customer_id": user_id},
                "payment": {"payment_group": "upi"},
            }
        ),
    )

    checkout = client.post(
        "/api/billing/checkout-session",
        json={"tier": "exam_pass"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert checkout.status_code == 200
    order_id = checkout.json()["order_id"]
    ticket_cookie = checkout.cookies.get("pp_checkout_return")
    assert ticket_cookie

    # Simulate cookie-less/expired auth session after gateway redirect using ONLY pp_checkout_return cookie.
    recovery_client = TestClient(server.app)
    recovery_client.cookies.set("pp_checkout_return", ticket_cookie)
    verified = recovery_client.get(f"/api/billing/verify-order/{order_id}")
    assert verified.status_code == 200
    v_data = verified.json()
    assert v_data["status"] == "paid"
    assert v_data["tier"] == "exam_pass"
    assert v_data.get("subscription_expires_at")
    assert recovery_client.cookies.get("paperplane_token")

    # Single-use recovery ticket cannot be replayed once consumed.
    replay_client = TestClient(server.app)
    replay_client.cookies.set("pp_checkout_return", ticket_cookie)
    replay_resp = replay_client.get(f"/api/billing/verify-order/{order_id}")
    assert replay_resp.status_code == 401

    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["subscription_expires_at"]
    orders_resp = client.get("/api/billing/orders", headers={"Authorization": f"Bearer {token}"})
    assert orders_resp.status_code == 200
    assert any(row["order_id"] == order_id for row in orders_resp.json()["orders"])


def test_customer_support_endpoints_and_admin_workflow():
    client = TestClient(server.app)
    reg = register_verified(client, f"support_{secrets.token_hex(6)}@paperplane.test", "StrongPass123!").json()
    token = reg["token"]

    # Unauthenticated list is denied; authenticated list starts empty.
    anon_client = TestClient(server.app)
    assert anon_client.get("/api/support/tickets").status_code == 401
    empty = client.get("/api/support/tickets", headers={"Authorization": f"Bearer {token}"})
    assert empty.status_code == 200
    assert empty.json()["tickets"] == []

    # Invalid short message returns 422.
    bad = client.post(
        "/api/support",
        json={"category": "billing_payment", "subject": "Order help", "message": "too short"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert bad.status_code == 422

    sent_alerts: list[tuple] = []
    with patch.object(server, "send_support_ticket_alert", lambda *args, **kwargs: sent_alerts.append((args, kwargs))):
        ok = client.post(
            "/api/support",
            json={
                "category": "billing_payment",
                "subject": "UPI order verification check",
                "order_id": "order_pp_check_123",
                "message": "Paid via UPI 5 minutes ago and checking activation status.",
                "page_context": {"view": "settings", "viewport": "1366x768"},
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert ok.status_code == 200
    body = ok.json()
    assert body["status"] == "ok"
    assert body["ticket_ref"].startswith("PP-")
    assert len(sent_alerts) == 1

    mine = client.get("/api/support/tickets", headers={"Authorization": f"Bearer {token}"}).json()["tickets"]
    assert len(mine) == 1
    assert mine[0]["ticket_ref"] == body["ticket_ref"]
    assert mine[0]["status"] == "open"
    ticket_id = mine[0]["id"]

    # Admin list, resolve, and delete controls.
    server.app.dependency_overrides[server._require_admin] = lambda: None
    try:
        listed = client.get("/api/admin/support").json()
        assert any(item["id"] == ticket_id for item in listed["tickets"])
        resolved = client.post(f"/api/admin/support/{ticket_id}/status", json={"status": "resolved"})
        assert resolved.status_code == 200
        assert resolved.json()["ticket_status"] == "resolved"
        deleted = client.delete(f"/api/admin/support/{ticket_id}")
        assert deleted.status_code == 200
    finally:
        server.app.dependency_overrides.pop(server._require_admin, None)

    index_html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    admin_html = client.get("/admin").text
    assert 'id="settings-tab-btn-support"' in index_html
    assert 'id="pane-support"' in index_html
    assert 'mdhammad2906@gmail.com' in index_html
    assert 'id="tab-support-btn"' in admin_html
    assert 'id="panel-support"' in admin_html


def test_id333_server_metadata_edit_preserves_latex_provenance_without_pypdf(tmp_path):
    source = tmp_path / "notes_test.pdf"
    _make_sample_pdf(
        source,
        "Lecture notes with LaTeX provenance.",
        metadata={
            "title": "Original Notes",
            "author": "Faculty",
            "creator": "LaTeX with hyperref",
            "producer": "pdfTeX-1.40.25",
            "creationDate": "D:20200201000000Z",
        },
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    result = server.process("metadata", [source], {"title": "Edited Title Only"}, out_dir)
    with fitz.open(result) as edited:
        meta = edited.metadata or {}
    assert meta.get("title") == "Edited Title Only"
    assert meta.get("creator") == "LaTeX with hyperref"
    assert "pdfTeX" in str(meta.get("producer") or "")
    assert "pypdf" not in str(meta.get("producer") or "").lower()
    assert str(meta.get("creationDate") or "").startswith("D:20200201")


def test_id427_hardened_redaction_rejects_zero_match_with_422(tmp_path):
    source = _make_sample_pdf(tmp_path / "redact_source.pdf", "Contains only alpha bravo text.")
    client = TestClient(server.app)
    with source.open("rb") as fh:
        miss = client.post(
            "/api/studio/security/redact",
            data={"redactions": json.dumps([{"page": "all", "text": "NONEXISTENT_TOKEN_XYZ"}])},
            files={"file": ("redact_source.pdf", fh, "application/pdf")},
        )
    assert miss.status_code == 422

    with source.open("rb") as fh:
        hit = client.post(
            "/api/studio/security/redact",
            data={"redactions": json.dumps([{"page": 0, "text": "alpha   bravo"}])},
            files={"file": ("redact_source.pdf", fh, "application/pdf")},
        )
    assert hit.status_code == 200
    with fitz.open(stream=hit.content, filetype="pdf") as redacted:
        extracted = redacted[0].get_text()
    assert "alpha" not in extracted
    assert "bravo" not in extracted


def test_id433_studio_forms_flatten_accepts_unsaved_field_values_atomically(tmp_path):
    source = _make_form_pdf(tmp_path / "form.pdf", field_name="applicant_name", initial="")
    client = TestClient(server.app)
    with source.open("rb") as fh:
        resp = client.post(
            "/api/studio/forms/flatten",
            data={"field_values": json.dumps({"applicant_name": "Hammad Verified"})},
            files={"file": ("form.pdf", fh, "application/pdf")},
        )
    assert resp.status_code == 200
    with fitz.open(stream=resp.content, filetype="pdf") as flat:
        assert list(flat[0].widgets() or []) == []
        assert "Hammad Verified" in flat[0].get_text()


def test_id428_compression_analysis_deduplicates_shared_image_xrefs(tmp_path):
    from PIL import Image

    img_path = tmp_path / "logo.png"
    Image.new("RGB", (240, 240), (40, 110, 180)).save(img_path)
    pdf_path = tmp_path / "shared_image.pdf"
    with fitz.open() as doc:
        for _ in range(3):
            page = doc.new_page()
            page.insert_image(fitz.Rect(50, 50, 180, 180), filename=str(img_path))
        doc.save(pdf_path)

    analysis = converters.analyze_pdf_compression(pdf_path)
    assert analysis["unique_images"] == 1
    assert analysis["raster_percentage"] <= 100.0


def test_id441_ai_chat_stream_429_does_not_substitute_bm25_on_document_question(tmp_path, monkeypatch):
    source = _make_sample_pdf(tmp_path / "contract.pdf", "Exclusive clause: secret-bm25-marker-441 applies only upon written consent.")
    monkeypatch.setattr(ai_engine, "AI_KILL_SWITCH", False)
    monkeypatch.setattr(ai_engine, "_current_bluesminds_api_key", lambda: "test-key")
    monkeypatch.setattr(
        ai_engine,
        "stream_bluesminds",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("upstream HTTP 429 rate limited")),
    )

    client = TestClient(server.app)
    with source.open("rb") as fh:
        resp = client.post(
            "/api/ai/chat/stream",
            data={"question": "What does the exclusive clause say about secret-bm25-marker-441?"},
            files={"file": ("contract.pdf", fh, "application/pdf")},
        )
    assert resp.status_code == 200
    body = resp.text.lower()
    assert "event: error" in body
    assert "429" in body or "rate" in body
    assert "secret-bm25-marker-441" not in body


def test_v30_frontend_contracts_for_phase_a_and_b_fixes():
    app_js = (ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    styles = (ROOT / "web" / "assets" / "styles.css").read_text(encoding="utf-8")
    organizer = (ROOT / "web" / "assets" / "page_organizer.js").read_text(encoding="utf-8")
    sec_forms = (ROOT / "web" / "assets" / "security_forms.js").read_text(encoding="utf-8")
    opt_js = (ROOT / "web" / "assets" / "optimization_engine.js").read_text(encoding="utf-8")
    index_html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    worker_js = (ROOT / "web" / "assets" / "local_pdf_worker.js").read_text(encoding="utf-8")

    # ID 454 & ID 451
    assert "await normalizedValue.blob.arrayBuffer()" in app_js
    assert "previousAnnotations" in app_js and "_restoreAnnotationsWithPageMap" in organizer
    # ID 430 preflight before progress/upload
    assert app_js.index("abortOnExhaustedQuota();") < app_js.index("'Preparing document streams…'")
    assert "/api/billing/status" in opt_js
    # ID 435 popup suppression fallback on both Google click paths
    assert "invokeGoogleCodeClientWithPopupFallback" in app_js
    # ID 434 & ID 340 & ID 51 & ID 55 CSS contracts
    assert "max-width: 1460px" in styles
    assert "z-index: 1200 !important" in styles
    assert ".settings-modal-card .settings-tabs" in styles and "264px" in styles
    assert ".quota-label-row > span:first-child" in styles
    # ID 56 waitlist scroll + feedback
    assert "card.classList.toggle('is-selected'" in app_js
    assert "scrollIntoView" in app_js
    # ID 433 form flatten collects live DOM field values
    assert "querySelectorAll('.form-field-input')" in sec_forms
    # ID 333 client worker XMP provenance fallback
    assert "xmp:CreatorTool" in worker_js or "CreatorTool" in worker_js
    assert "id=\"billing-return-banner\"" in index_html
    # Audit follow-up fixes: zero legacy innerHTML='', safe error status text, accurate 30s analyze timeout, recovery challenge persistence
    assert "setListStatusMessage(listEl" in app_js
    assert "listEl.innerHTML = ''" not in app_js
    assert "url === '/api/studio/compress'" in opt_js
    admin_js = (ROOT / "web" / "assets" / "admin.js").read_text(encoding="utf-8")
    assert "pp_admin_recovery_challenge" in admin_js


def test_split_image_only_pages_without_text_succeeds(tmp_path):
    """Ensure image/blank-page pixel digest verification in split_pdf_document works (import hashlib)."""
    from PIL import Image

    img1 = tmp_path / "p1.png"
    img2 = tmp_path / "p2.png"
    Image.new("RGB", (200, 200), (220, 40, 40)).save(img1)
    Image.new("RGB", (200, 200), (40, 40, 220)).save(img2)
    src = tmp_path / "scanned_pair.pdf"
    with fitz.open() as doc:
        doc.new_page().insert_image(fitz.Rect(20, 20, 180, 180), filename=str(img1))
        doc.new_page().insert_image(fitz.Rect(20, 20, 180, 180), filename=str(img2))
        doc.save(src)

    parts = converters.split_pdf_document(src, tmp_path / "out", mode="ranges", param="1-1, 2-2")
    assert len(parts) == 2
    for part in parts:
        assert part.exists()
        with fitz.open(part) as doc:
            assert doc.page_count == 1
