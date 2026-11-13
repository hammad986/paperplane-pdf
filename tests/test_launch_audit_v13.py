from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from threading import Event
import time
from urllib.parse import parse_qs, urlsplit

import fitz
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont, ImageOps
from pypdf import PdfReader, PdfWriter

import ai_engine
import persistence
import server
from scripts.check_data_mount import check_data_mount

ROOT = Path(__file__).resolve().parents[1]


def pdf_bytes(count=3):
    with fitz.open() as document:
        for number in range(1, count + 1):
            page = document.new_page()
            page.insert_text((60, 60), f"Page {number}: a document for Paperplane verification. This is synthetic.")
        return document.tobytes()


def owner_header():
    return {"X-Admin-Session": persistence.create_admin_session(server.PRIMARY_ADMIN_EMAIL)}


def account_client():
    email = f"audit-{secrets.token_hex(8)}@example.invalid"
    password = secrets.token_urlsafe(24)
    user = persistence.create_user(email, password)
    token = persistence.create_session(email, password)["token"]
    return user, TestClient(server.app, headers={"Authorization": f"Bearer {token}"})


def post_pdf(client, path, data=None, content=None):
    return client.post(path, data=data, files={"file": ("synthetic.pdf", content or pdf_bytes(), "application/pdf")})


@pytest.mark.parametrize("name", ["PAPERPLANE_ADMIN_KEY", "PAPERPLANE_ADMIN_CODE"])
def test_101_admin_settings_required_at_startup(name, tmp_path):
    env = dict(os.environ, PAPERPLANE_DATA_DIR=str(tmp_path))
    del env[name]
    result = subprocess.run([sys.executable, "-c", "import server"], env=env, cwd=ROOT,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert f"{name} must be set" in result.stderr


def test_98_misconfigured_production_is_never_reported_ready(monkeypatch):
    _, client = account_client()
    monkeypatch.setattr(server, "CASHFREE_APP_ID", secrets.token_hex(16))
    monkeypatch.setattr(server, "CASHFREE_SECRET_KEY", secrets.token_hex(16))
    monkeypatch.setattr(server, "CASHFREE_ENV", "TEST")
    monkeypatch.setattr(server, "ENVIRONMENT", "production")
    monkeypatch.setattr(server, "ALLOW_BILLING_SIMULATION", True)
    monkeypatch.setattr(server, "_cashfree_request", lambda *args: pytest.fail("Gateway must not be contacted"))
    assert not client.get("/api/billing/status").json()["cashfree_configured"]
    for tier in ("exam_pass", "student_pro", "cyber_cafe"):
        assert client.post("/api/billing/checkout-session", json={"tier": tier}).status_code == 503
    assert client.post("/api/billing/simulate-pro").status_code == 403


def signed_event(client, secret, event):
    raw = json.dumps(event, separators=(",", ":")).encode()
    timestamp = str(int(time.time() * 1000))
    signature = base64.b64encode(hmac.new(secret.encode(), timestamp.encode() + raw, hashlib.sha256).digest()).decode()
    return client.post("/api/billing/cashfree-webhook", content=raw,
                       headers={"x-webhook-timestamp": timestamp, "x-webhook-signature": signature})


@pytest.mark.parametrize("tier,amount", [("exam_pass", 19), ("student_pro", 49), ("cyber_cafe", 299)])
def test_98_107_checkout_and_signed_sandbox_webhook(tier, amount, monkeypatch):
    user, client = account_client()
    gateway_key = secrets.token_hex(32)
    monkeypatch.setattr(server, "CASHFREE_APP_ID", secrets.token_hex(16))
    monkeypatch.setattr(server, "CASHFREE_SECRET_KEY", gateway_key)
    monkeypatch.setattr(server, "CASHFREE_ENV", "TEST")

    def fake_gateway(method, path, body):
        assert method == "POST" and path == "/orders"
        assert body["order_amount"] == amount and body["order_currency"] == "INR"
        return {"payment_session_id": secrets.token_urlsafe(12)}

    monkeypatch.setattr(server, "_cashfree_request", fake_gateway)
    checkout = client.post("/api/billing/checkout-session", json={"tier": tier})
    assert checkout.status_code == 200
    order = {"order_id": checkout.json()["order_id"], "order_amount": amount + 1, "order_currency": "INR"}
    event = {"type": "PAYMENT_SUCCESS_WEBHOOK", "data": {
        "order": order, "payment": {"payment_status": "SUCCESS"}, "customer_details": {"customer_id": user},
    }}
    assert signed_event(client, gateway_key, event).status_code == 200
    assert persistence.get_user_tier(user) == "free"
    order["order_amount"] = amount
    assert signed_event(client, gateway_key, event).json()["status"] == "OK"
    assert persistence.get_user_tier(user) == tier
    ledger = client.get("/api/admin/revenue", headers=owner_header()).json()
    entry = next(row for row in ledger["recent_transactions"] if row["order_id"] == order["order_id"])
    assert entry["gateway_environment"] == "TEST"
    assert ledger["sandbox_gross_inr"] >= amount


def test_184_proxy_quotas_are_independent_and_spoofing_is_ignored():
    trusted = TestClient(server.app, client=("127.0.0.1", 50000))
    untrusted = TestClient(server.app, client=("192.0.2.1", 50000))
    a = {"X-Forwarded-For": "198.51.100.10"}
    b = {"X-Forwarded-For": "203.0.113.20"}
    for _ in range(10):
        persistence.increment_daily_usage("ip:198.51.100.10")
    assert trusted.get("/api/billing/status", headers=a).json()["remaining_today"] == 0
    assert trusted.get("/api/billing/status", headers=b).json()["remaining_today"] == 10
    assert post_pdf(trusted, "/api/studio/apply-edits").status_code == 200
    assert untrusted.get("/api/billing/status", headers=a).json()["remaining_today"] == 10


class MockProviderReply:
    status = 200

    def __init__(self, answer):
        self.answer = answer

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return json.dumps({"choices": [{"message": {"content": self.answer}}]}).encode()


@pytest.fixture
def mock_ai(monkeypatch):
    key = secrets.token_hex(16)
    monkeypatch.setattr(ai_engine, "_current_bluesminds_api_key", lambda: key)
    monkeypatch.setattr(ai_engine, "_runtime_ai_config", lambda: {
        "provider": "openai_compatible", "base_url": "https://provider.invalid/v1",
        "model": "audit-model", "api_key": key,
    })
    monkeypatch.setattr(ai_engine.time, "sleep", lambda seconds: None)


def test_1_translation_retries_slow_request_and_renders_hindi(mock_ai, monkeypatch):
    calls = []

    def upstream(request, timeout):
        calls.append(timeout)
        if len(calls) == 1:
            raise TimeoutError
        blocks = json.loads(json.loads(request.data)["messages"][1]["content"])
        return MockProviderReply(json.dumps({"translations": [{"id": block["id"], "text": "भारत सरकार"} for block in blocks]}))

    monkeypatch.setattr(ai_engine, "_open_ai_request", upstream)
    response = post_pdf(TestClient(server.app), "/api/ai/translate", {"target_language": "hi"})
    assert response.status_code == 200 and len(calls) == 2 and min(calls) >= 8
    assert response.headers["X-Paperplane-Translation-Mode"] == "translated"
    with fitz.open(stream=response.content, filetype="pdf") as result:
        assert result.page_count == 3
        assert all(any("Devanagari" in font[3] for font in page.get_fonts(full=True)) for page in result)


def test_1_failed_queued_translation_refunds_guest_quota(mock_ai, monkeypatch):
    def reject(*args, **kwargs):
        raise TimeoutError

    monkeypatch.setattr(ai_engine, "_open_ai_request", reject)
    client = TestClient(server.app)
    response = client.post("/api/jobs", data={"operation": "translate"},
                           files={"files": ("synthetic.pdf", pdf_bytes(), "application/pdf")})
    assert response.status_code == 202
    for _ in range(100):
        job = client.get(response.json()["status_url"]).json()
        if job["status"] == "failed":
            break
        time.sleep(0.01)
    assert job["status"] == "failed"
    assert client.get("/api/billing/status").json()["usage_today"] == 0


def test_2_large_summary_covers_all_69_pages_under_bounded_budget(mock_ai, monkeypatch):
    calls = []

    def upstream(request, timeout):
        prompt = json.loads(request.data)["messages"][1]["content"]
        calls.append((timeout, prompt))
        if timeout < 40:
            raise TimeoutError
        return MockProviderReply("The opening and closing pages describe the audit. [Page 1] [Page 69]")

    monkeypatch.setattr(ai_engine, "_open_ai_request", upstream)
    response = post_pdf(TestClient(server.app), "/api/ai/summarize", content=pdf_bytes(69))
    assert response.status_code == 200
    assert response.json()["citations"] == [1, 69]
    assert len(calls) == 4
    assert all(any(f"--- Page {n} ---" in prompt for _, prompt in calls[:3]) for n in range(1, 70))
    oversized = post_pdf(TestClient(server.app), "/api/ai/summarize", content=pdf_bytes(121))
    assert oversized.status_code == 422


@pytest.mark.parametrize("action,expected", [
    ("https://drive.usercontent.google.com/download", 200),
    ("http://127.0.0.1/download", 400),
])
def test_4_drive_confirmation_validates_host_and_preserves_resource_key(monkeypatch, action, expected):
    calls = []

    def fetch(url, **kwargs):
        parsed = urlsplit(url)
        calls.append(parsed)
        assert parse_qs(parsed.query)["resourcekey"] == ["synthetic-resource"]
        if len(calls) == 1:
            return (f'<html><form id="download-form" action="{action}">'
                    '<input type="hidden" name="id" value="synthetic-id">'
                    '<input type="hidden" name="confirm" value="audit-confirm"></form></html>').encode(), "text/html"
        assert parsed.hostname == "drive.usercontent.google.com"
        assert parse_qs(parsed.query)["confirm"] == ["audit-confirm"]
        return pdf_bytes(), "application/pdf"

    monkeypatch.setattr(server.converters, "safe_fetch_url", fetch)
    result = TestClient(server.app).post("/api/cloud/sync", data={
        "file_url": "https://drive.google.com/file/d/synthetic-id/view?resourcekey=synthetic-resource",
    })
    assert result.status_code == expected
    assert len(calls) == (2 if expected == 200 else 1)
    if expected == 200:
        assert result.json()["page_count"] == 3


def test_47_49_studio_reorder_and_export_preserve_all_69_pages():
    client = TestClient(server.app)
    order = [2, 1, 4, 3, *range(5, 70)]
    reordered = post_pdf(client, "/api/studio/pages/reorder", {"order": json.dumps(order)}, pdf_bytes(69))
    assert reordered.status_code == 200 and "content-length" in reordered.headers
    exported = post_pdf(client, "/api/studio/apply-edits", {"edits": "[]"}, reordered.content)
    assert exported.status_code == 200 and "content-length" in exported.headers
    with fitz.open(stream=exported.content, filetype="pdf") as result:
        assert result.page_count == 69
        assert all(page.get_text().startswith(f"Page {n}:") for page, n in zip(result, order))


def test_93_102_account_and_feedback_visible_after_process_restart(tmp_path, monkeypatch):
    database = tmp_path / "paperplane.sqlite3"
    monkeypatch.setattr(persistence, "DATABASE", database)
    persistence.init_db()
    email, password = "isolated-restart@example.invalid", secrets.token_urlsafe(24)
    persistence.create_user(email, password)
    client = TestClient(server.app)
    response = client.post("/api/feedback", json={"message": "Synthetic restart test", "rating": 4})
    assert response.status_code == 200
    state = [email, password, response.json()["feedback_id"]]
    code = """
import json, sys
from persistence import verify_user_credentials, admin_get_feedbacks
email, password, entry = json.load(sys.stdin)
assert verify_user_credentials(email, password)
assert any(item['id'] == entry for item in admin_get_feedbacks())
"""
    completed = subprocess.run([sys.executable, "-c", code], input=json.dumps(state), cwd=ROOT,
                               env=dict(os.environ, PAPERPLANE_DATA_DIR=str(tmp_path)),
                               capture_output=True, text=True, timeout=15)
    assert completed.returncode == 0


def test_93_refuses_to_switch_existing_volume():
    config = {"volumes": {"paperplane_data": {"name": "audit-data"}}}
    volume = {"Destination": "/data", "Type": "volume", "Name": "audit-data", "RW": True}
    check_data_mount(config, [volume])
    for mount in ({**volume, "Name": "other-data"}, {**volume, "RW": False}, {**volume, "Type": "bind"}):
        with pytest.raises(ValueError, match="differs"):
            check_data_mount(config, [mount])


@pytest.mark.parametrize("path,location", [
    ("/dashboard", "/tool-desk"), ("/plans", "/pricing"), ("/billing", "/pricing"),
    ("/metadata", "/pdf-metadata"), ("/photo-compress", "/compress-image-online"),
    ("/compress-photos", "/compress-image-online"), ("/ai-chat", "/ai-pdf-chat"),
    ("/chat-pdf", "/ai-pdf-chat"), ("/pdf-chat", "/ai-pdf-chat"), ("/tools/merge", "/merge-pdf"),
])
def test_132_181_route_aliases_resolve(path, location):
    client = TestClient(server.app)
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 301 and response.headers["location"] == location
    assert client.get(location).status_code == 200


@pytest.mark.parametrize("path,heading", [
    ("/settings", "Paperplane Settings"), ("/pricing", "Paperplane Pricing"),
    ("/history", "Temporary downloads"), ("/feedback", "Feedback"),
    ("/faq", "Frequently asked questions"),
])
def test_132_133_page_matches_its_url(path, heading):
    response = TestClient(server.app).get(path)
    assert response.status_code == 200
    assert f"<h1>{heading}</h1>" in response.text
    assert f'<link rel="canonical" href="http://testserver{path}"' in response.text


def test_150_reader_opens_pdf_with_empty_user_password(tmp_path):
    source = tmp_path / "restricted.pdf"
    writer = PdfWriter()
    writer.add_blank_page(250, 350)
    writer.encrypt(user_password="", owner_password=secrets.token_urlsafe(20))
    writer.write(source)
    for operation in ("merge", "rotate"):
        output = server.process(operation, [source], {}, tmp_path)
        assert len(PdfReader(output).pages) == 1


def test_184_200_204_admin_actions_are_authenticated_audited_and_targeted():
    user, client = account_client()
    user2, _ = account_client()
    assert client.get("/api/auth/me").status_code == 200
    body = {"user_id": user, "tier": "cyber_cafe"}
    assert client.post("/api/admin/users/set-plan", json=body).status_code == 401
    headers = owner_header()
    assert client.post("/api/admin/users/set-plan", json=body, headers=headers).status_code == 200
    assert persistence.get_user_tier(user) == "cyber_cafe"
    for subject in (user, user2):
        persistence.increment_daily_usage(f"user:{subject}")
    assert client.post("/api/admin/users/reset-usage", json={"user_id": user}, headers=headers).status_code == 200
    assert persistence.get_daily_usage(f"user:{user}") == 0
    assert persistence.get_daily_usage(f"user:{user2}") == 1
    directory = client.get("/api/admin/users", headers=headers).json()["users"]
    assert next(item for item in directory if item["id"] == user)["last_active_at"] > 0
    events = persistence.get_recent_audit_logs()
    assert {row["event_type"] for row in events if row["user_id"] == user} >= {"admin_plan_changed", "admin_usage_reset"}


def test_202_203_two_owners_authenticate_independently_and_revoke_only_target(monkeypatch):
    sent = {}
    monkeypatch.setattr(server, "send_admin_login_otp", lambda **kw: sent.update({kw["to_email"]: kw["otp_code"]}) or True)
    owners = sorted(server.ADMIN_OWNER_EMAILS)
    client = TestClient(server.app)
    challenges = {}
    for email in owners:
        response = client.post("/api/admin/auth/step1", json={
            "email": email, "admin_key": server.ADMIN_SECRET_KEY, "admin_code": server.ADMIN_SECRET_CODE,
        })
        assert response.status_code == 200
        challenges[email] = response.json()["challenge"]
    sessions = {}
    for email in owners:
        response = client.post("/api/admin/auth/step2", json={"otp": sent[email], "challenge": challenges[email]})
        assert response.status_code == 200
        sessions[email] = {"X-Admin-Session": response.json()["session_token"]}
    actor, target = owners
    listing = client.get("/api/admin/sessions", headers=sessions[actor]).json()["sessions"]
    assert len([row for row in listing if row["email"] in owners]) >= 2
    assert not any("token_hash" in row for row in listing)
    other_id = next(row["id"] for row in listing if row["email"] == target and not row["current"])
    assert client.delete(f"/api/admin/sessions/{other_id}", headers=sessions[actor]).status_code == 200
    assert client.get("/api/admin/dashboard", headers=sessions[target]).status_code == 401
    assert client.get("/api/admin/dashboard", headers=sessions[actor]).status_code == 200
    assert client.post("/api/admin/auth/logout", headers=sessions[actor]).status_code == 200
    assert client.get("/api/admin/dashboard", headers=sessions[actor]).status_code == 401


def test_107_paid_webhook_replay_cannot_restore_a_reset_plan(monkeypatch):
    user, client = account_client()
    gateway_key = secrets.token_hex(32)
    monkeypatch.setattr(server, "CASHFREE_APP_ID", secrets.token_hex(16))
    monkeypatch.setattr(server, "CASHFREE_SECRET_KEY", gateway_key)
    monkeypatch.setattr(server, "CASHFREE_ENV", "TEST")
    monkeypatch.setattr(server, "_cashfree_request", lambda *a: {"payment_session_id": secrets.token_urlsafe(12)})
    checkout = client.post("/api/billing/checkout-session", json={"tier": "exam_pass"}).json()
    event = {"type": "PAYMENT_SUCCESS_WEBHOOK", "data": {
        "order": {"order_id": checkout["order_id"], "order_amount": 19, "order_currency": "INR"},
        "payment": {"payment_status": "SUCCESS"}, "customer_details": {"customer_id": user},
    }}
    assert signed_event(client, gateway_key, event).status_code == 200
    assert persistence.get_user_tier(user) == "exam_pass"
    assert 86390 < persistence.get_user(user)["subscription_expires_at"] - time.time() <= 86400
    assert persistence.admin_update_user_access(user, server.PRIMARY_ADMIN_EMAIL, "127.0.0.1", "free")
    assert signed_event(client, gateway_key, event).status_code == 200
    assert persistence.get_user_tier(user) == "free"


def test_201_location_is_derived_from_public_ip_only(monkeypatch, tmp_path):
    from types import SimpleNamespace

    calls = []

    class Reader:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, ip):
            calls.append(ip)
            return {"city": {"names": {"en": "Sample city"}},
                    "subdivisions": [{"names": {"en": "Sample region"}}],
                    "country": {"names": {"en": "Sample country"}}}

    monkeypatch.setitem(sys.modules, "maxminddb", SimpleNamespace(open_database=lambda path: Reader()))
    monkeypatch.setenv("PAPERPLANE_GEOIP_DB", str(tmp_path / "sample.mmdb"))
    server._lookup_admin_location.cache_clear()
    try:
        assert server._lookup_admin_location("127.0.0.1") is None
        assert server._lookup_admin_location("8.8.8.8") == "Sample city, Sample region, Sample country"
        assert len(calls) == 1
    finally:
        server._lookup_admin_location.cache_clear()


@pytest.mark.parametrize("separator", [" ", ""])
def test_188_aadhaar_image_redaction_burns_pixels_without_removing_last_four(tmp_path, separator):
    from security_forms_engine import mask_aadhaar_image

    source = tmp_path / "synthetic-card.png"
    font = None
    for path in ("C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(path).is_file():
            font = ImageFont.truetype(path, 78)
            break
    if font is None:
        font = ImageFont.load_default(size=78)
    digits = "".join(str((index * 7 + 2) % 10) for index in range(12))
    marker = separator.join(digits[i:i + 4] for i in (0, 4, 8))
    image = Image.new("RGB", (950, 210), "white")
    ImageDraw.Draw(image).text((40, 45), marker, fill="black", font=font)
    image.save(source)
    output = mask_aadhaar_image(source, tmp_path / "masked.png")
    with Image.open(output) as masked:
        assert masked.size == image.size
        prefix = separator.join((digits[:4], digits[4:8]))
        suffix_start = int(40 + font.getlength(prefix + separator))
        # Some OCR boxes round the cutoff into the next character's leading
        # whitespace. Compare its ink, rather than the surrounding blank pixels.
        last_four = image.crop((suffix_start, 30, 950, 190))
        ink_box = ImageOps.invert(last_four).getbbox()
        assert ink_box is not None
        preserved = (suffix_start + ink_box[0], 30 + ink_box[1],
                     suffix_start + ink_box[2], 30 + ink_box[3])
        prefix_ink = ImageOps.invert(image.crop((36, 30, suffix_start, 190))).getbbox()
        assert prefix_ink is not None
        masked_prefix = (36 + prefix_ink[0], 30 + prefix_ink[1],
                         36 + prefix_ink[2], 30 + prefix_ink[3])
        assert masked.crop(masked_prefix).getextrema() == ((0, 0), (0, 0), (0, 0))
        assert masked.crop(preserved).tobytes() == image.crop(preserved).tobytes()


def test_23_184_concurrent_ai_requests_cannot_take_same_guest_quota_slot(monkeypatch):
    monkeypatch.setattr(server, "REQUIRE_AUTH", False)
    subject = "ip:192.0.2.73"
    day = date.today().isoformat()
    with persistence.connect() as connection:
        connection.execute(
            "INSERT INTO user_usage (subject, usage_date, count) VALUES (?, ?, ?)",
            (subject, day, server.FREE_TIER_DAILY_LIMIT - 1),
        )
    started, release = Event(), Event()

    def summarize(_path):
        started.set()
        assert release.wait(8)
        return "Synthetic brief. [Page 1]"

    monkeypatch.setattr(ai_engine, "summarize_pdf", summarize)
    with TestClient(server.app, client=("192.0.2.73", 34567)) as client, ThreadPoolExecutor(1) as executor:
        first = executor.submit(post_pdf, client, "/api/ai/summarize")
        try:
            assert started.wait(5)
            rejected = post_pdf(client, "/api/studio/pages/rotate", {"pages": "[1]", "degrees": "90"})
            assert rejected.status_code == 402
            assert rejected.json()["detail"]["code"] == "TIER_LIMIT_REACHED"
        finally:
            release.set()
        assert first.result().status_code == 200
    assert persistence.get_daily_usage(subject, day) == server.FREE_TIER_DAILY_LIMIT


def test_9_invalid_smart_metadata_upload_does_not_create_result_or_consume_quota(monkeypatch):
    monkeypatch.setattr(server, "REQUIRE_AUTH", False)
    with TestClient(server.app, client=("192.0.2.74", 34567)) as client:
        rejected = post_pdf(client, "/api/ai/extract", content=b"not a PDF")
        assert rejected.status_code == 422
        assert "data" not in rejected.json()
    assert persistence.get_daily_usage("ip:192.0.2.74") == 0


def test_23_incomplete_chat_stream_refunds_daily_quota(monkeypatch):
    monkeypatch.setattr(server, "REQUIRE_AUTH", False)

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("AI service timed out.")

    monkeypatch.setattr(ai_engine, "stream_bluesminds", unavailable)
    with TestClient(server.app, client=("192.0.2.75", 34567)) as client:
        response = client.post("/api/ai/chat/stream", data={"question": "Explain the difference between pears and apples."})
        assert response.status_code == 200
        assert "event: error" in response.text and "event: done" not in response.text
        assert persistence.get_daily_usage("ip:192.0.2.75") == 0
