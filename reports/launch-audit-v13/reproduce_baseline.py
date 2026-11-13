from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import logging
import os
import secrets
import subprocess
import sys

import fitz
from fastapi.testclient import TestClient

logging.disable(logging.CRITICAL)
os.environ["PAPERPLANE_SKIP_DOTENV"] = "1"
os.environ["PAPERPLANE_ENV"] = "development"
os.environ["PAPERPLANE_SECURE_COOKIES"] = "false"
os.environ["PAPERPLANE_FREE_TIER_DAILY_LIMIT"] = "10"
os.environ["CASHFREE_ENV"] = "TEST"
os.environ["PAPERPLANE_ALLOW_BILLING_SIMULATION"] = "false"

def make_pdf(pages):
    with fitz.open() as doc:
        for number in range(1, pages + 1):
            doc.new_page().insert_text((72, 72), f"Baseline synthetic page {number}. This page is used for the isolated launch audit.")
        return doc.tobytes()

def post_file(client, route, pdf, **options):
    return client.post(route, files={"file": ("audit.pdf", pdf, "application/pdf")}, data=options)

def upstream(content):
    class Reply:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def read(self):
            return json.dumps({"choices": [{"message": {"content": content}}]}).encode()
    return Reply()

with TemporaryDirectory(prefix="paperplane-v13-repro-") as data_dir:
    os.environ["PAPERPLANE_DATA_DIR"] = data_dir
    print("Starting isolated imports", file=sys.stderr, flush=True)
    import ai_engine
    import persistence
    import server
    print("Imports completed", file=sys.stderr, flush=True)

    doc3, doc69 = make_pdf(3), make_pdf(69)
    client = TestClient(server.app, follow_redirects=False)
    result = {}
    usage_before = client.get("/api/billing/status").json()["usage_today"]
    calls = []
    def slow_translate(request, timeout):
        calls.append(timeout)
        if timeout < 8:
            raise TimeoutError
        return upstream('{"translations":[{"id":1,"text":"Prueba"}]}')
    provider = {
        "provider": "openai_compatible", "base_url": "https://provider.invalid/v1",
        "model": "audit-model", "api_key": secrets.token_hex(16),
    }
    with patch.object(ai_engine, "_current_bluesminds_api_key", return_value=provider["api_key"]), patch.object(ai_engine, "_runtime_ai_config", return_value=provider), patch.object(ai_engine, "_open_ai_request", side_effect=slow_translate), patch.object(ai_engine.time, "sleep"):
        response = post_file(client, "/api/ai/translate", doc3, target_language="es")
    result["1"] = {"status": response.status_code, "detail": response.json().get("detail") if response.status_code >= 400 else None,
                   "provider_budgets_seconds": calls, "usage_change": client.get("/api/billing/status").json()["usage_today"] - usage_before}
    calls = []
    def slow_summary(request, timeout):
        calls.append(timeout)
        body = json.loads(request.data)
        if "DOCUMENT SECTION" in body["messages"][1]["content"] and timeout < 40:
            raise TimeoutError
        return upstream("The synthetic document contains an audit page. [Page 1]")
    with patch.object(ai_engine, "_runtime_ai_config", return_value=provider), patch.object(ai_engine, "_open_ai_request", side_effect=slow_summary), patch.object(ai_engine.time, "sleep"):
        small = post_file(client, "/api/ai/summarize", doc3)
        large = post_file(client, "/api/ai/summarize", doc69)
    result["2"] = {"small_status": small.status_code, "large_status": large.status_code,
                   "detail": large.json().get("detail"), "provider_budgets_seconds": calls}
    requests = []
    def drive_confirmation(url, **kwargs):
        requests.append(url.split("?", 1)[0])
        if "drive.usercontent.google.com" in url:
            return doc3, "application/pdf"
        return b"\n<!-- proxy markup --><html><form id='download-form'></form></html>", "text/html"
    with patch.object(server.converters, "safe_fetch_url", side_effect=drive_confirmation):
        drive = client.post("/api/cloud/sync", data={"file_url": "https://drive.google.com/file/d/AuditPublicFile/view?resourcekey=synthetic"})
        direct = client.post("/api/cloud/sync", data={"file_url": "https://drive.usercontent.google.com/download?id=AuditPublicFile"})
    result["4"] = {"viewer_status": drive.status_code, "viewer_detail": drive.json().get("detail"),
                   "direct_status": direct.status_code, "direct_pages": direct.json().get("page_count"), "paths": requests}

    source_file = Path("reports/launch-audit-v8/test-files/notes-69page.pdf")
    study_pdf = source_file.read_bytes() if source_file.is_file() else doc69
    with fitz.open(stream=study_pdf, filetype="pdf") as source:
        source_pages = [page.get_text() for page in source]
    reorder = post_file(client, "/api/studio/pages/reorder", study_pdf, order=json.dumps([2, 1, *range(3, 70)]))
    edited = post_file(client, "/api/studio/apply-edits", reorder.content if reorder.is_success else study_pdf, edits="[]")
    exported_pages = []
    if edited.is_success:
        with fitz.open(stream=edited.content, filetype="pdf") as exported:
            exported_pages = [page.get_text() for page in exported]
    for _ in range(10):
        persistence.increment_daily_usage("ip:testclient")
    blocked = post_file(client, "/api/studio/apply-edits", doc3, edits="[]")
    result["49"] = {"fixture_bytes": len(study_pdf), "reorder_status": reorder.status_code, "export_status": edited.status_code,
                    "export_pages": len(exported_pages), "reorder_content_matches": exported_pages == [source_pages[1], source_pages[0], *source_pages[2:]],
                    "exhausted_export_status": blocked.status_code, "quota_detail_is_object": isinstance(blocked.json().get("detail"), dict)}

    email = "baseline-audit@example.invalid"
    local_password = secrets.token_urlsafe(24)
    user_id = persistence.create_user(email, local_password)
    # Spawn a second process, using the same disposable data directory.
    restart_check = (
        "import json,logging,sys; logging.disable(logging.CRITICAL); "
        "from persistence import verify_user_credentials, admin_get_feedbacks; "
        "email,password,feedback_id=json.load(sys.stdin); "
        "print(json.dumps({'login':bool(verify_user_credentials(email,password)), "
        "'feedback_visible':any(r['id']==feedback_id for r in admin_get_feedbacks())}))"
    )
    feedback = client.post("/api/feedback", json={"message": "Synthetic baseline read-after-write", "rating": 5})
    with patch.object(server, "verify_admin_session", return_value=True):
        admin = client.get("/api/admin/feedback", headers={"X-Admin-Session": "<synthetic>"})
    feedback_id = feedback.json().get("feedback_id")
    process = subprocess.run([sys.executable, "-c", restart_check], input=json.dumps([email, local_password, feedback_id]),
                             text=True, capture_output=True, check=True)
    restart = json.loads(process.stdout)
    result["93"] = {"new_process_same_data_directory_login": restart["login"], "compose_database_path": "/data/paperplane.sqlite3"}
    result["102"] = {"submit_status": feedback.status_code, "admin_status": admin.status_code, "visible_in_second_process": restart["feedback_visible"]}

    auth_client = TestClient(server.app, follow_redirects=False)
    with patch.object(server, "CASHFREE_APP_ID", "synthetic"), \
            patch.object(server, "CASHFREE_SECRET_KEY", secrets.token_urlsafe(24)), patch.object(server, "ENVIRONMENT", "production"), \
            patch.object(server, "CASHFREE_ENV", "TEST"), patch.object(server, "_cashfree_request", side_effect=AssertionError("Unexpected outbound checkout")):
        server.app.dependency_overrides[server.current_user] = lambda: user_id
        try:
            status = auth_client.get("/api/billing/status")
            result["98"] = {"configured": status.json().get("cashfree_configured"), "environment": status.json().get("cashfree_environment"),
                            "checkout_statuses": {plan: auth_client.post("/api/billing/checkout-session", json={"tier": plan}).status_code
                                                  for plan in ("exam_pass", "student_pro", "cyber_cafe", "pro", "developer")},
                            "simulation_status": auth_client.post("/api/billing/simulate-pro").status_code}
        finally:
            server.app.dependency_overrides.clear()
    result["101"] = {"server_imported_without_admin_variables": True, "nonempty_code_fallback": bool(server.ADMIN_SECRET_CODE),
                     "nonempty_key_fallback": bool(server.ADMIN_SECRET_KEY)}
    result["132"] = {path: client.get(path).status_code for path in ("/dashboard","/history","/faq","/feedback","/pricing","/plans")}
    settings = client.get("/settings")
    result["133"] = {"status": settings.status_code, "same_document_title_as_tool_desk":
                     settings.text.split("<title>")[1].split("</title>")[0] == client.get("/tool-desk").text.split("<title>")[1].split("</title>")[0]}

    # TestClient emulates the real peer, not a user-controlled forwarded header.
    proxy = TestClient(server.app, client=("172.18.0.4", 50001))
    persistence.increment_daily_usage("ip:172.18.0.4")
    result["184"] = {addr: proxy.get("/api/billing/status", headers={"X-Forwarded-For": addr}).json()["usage_today"]
                     for addr in ("198.51.100.10", "203.0.113.20")}

    print(json.dumps(result, indent=2))

