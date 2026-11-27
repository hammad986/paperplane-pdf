"""Controlled real-browser verification for signup OTP resend notice and replacement."""
from __future__ import annotations
import json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

def run_round(round_no: int):
    evidence = {"round": round_no, "page_errors": [], "console_errors": [], "expected_rejection_console": []}
    with TemporaryDirectory(prefix="paperplane-id60-") as temp_name:
        temp = Path(temp_name); data = temp / "data"; data.mkdir(); sink = temp / "mail-sink.json"
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
        runner = temp / "controlled_server.py"
        runner.write_text('''import json, os, uvicorn\nfrom pathlib import Path\nimport server\ndef fake_send(to_email, code, purpose):\n    Path(os.environ["PAPERPLANE_TEST_MAIL_SINK"]).write_text(json.dumps({"code":code,"purpose":purpose}), encoding="utf-8")\n    return True\nserver.send_otp_email = fake_send\nserver.can_resend_otp = lambda email, purpose, cooldown=60: (True, 0)\nuvicorn.run(server.app, host="127.0.0.1", port=int(os.environ["PAPERPLANE_PORT"]), log_level="error")\n''', encoding="utf-8")
        env = {k:v for k,v in os.environ.items() if not k.upper().startswith(("PAPERPLANE_", "CASHFREE_", "SMTP_", "RESEND_", "OPENAI_", "OPENROUTER_", "BLUESMINDS_", "ANTHROPIC_", "GEMINI_", "DEEPSEEK_", "GOOGLE_API_", "AI_", "ADMIN_")) and k not in {"TESTING", "SESSION_SECRET_KEY"}}
        env.update({"PAPERPLANE_SKIP_DOTENV":"1", "PAPERPLANE_ENV":"development", "PAPERPLANE_DATA_DIR":str(data), "PAPERPLANE_PORT":str(port), "PAPERPLANE_ADMIN_KEY":secrets.token_urlsafe(48), "PAPERPLANE_ADMIN_CODE":secrets.token_urlsafe(32), "PAPERPLANE_SESSION_SECRET":secrets.token_urlsafe(48), "PAPERPLANE_SECURE_COOKIES":"false", "PAPERPLANE_TEST_MAIL_SINK":str(sink), "PYTHONPATH":str(ROOT)})
        app = subprocess.Popen([sys.executable, str(runner)], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2): break
                except OSError: time.sleep(.2)
            else: raise RuntimeError("Controlled local server did not start")
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width":1280,"height":900})
                page.on("pageerror", lambda e:evidence["page_errors"].append(str(e)))
                page.on("console", lambda m:(evidence["expected_rejection_console"].append(m.text) if m.type == "error" and "400 (Bad Request)" in m.text else evidence["console_errors"].append(m.text)) if m.type == "error" else None)
                page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
                page.evaluate("window.openAuthModal('', 'register')")
                email = f"id60-{round_no}-{secrets.token_hex(4)}@example.test"
                page.locator("#auth-email").fill(email)
                page.locator("#auth-password").fill("SecurePass!23456")
                page.locator("#auth-confirm-password").fill("SecurePass!23456")
                with page.expect_response(lambda r:r.url.endswith("/api/auth/register")) as signup_event:
                    page.locator("#auth-submit-btn").click()
                signup = signup_event.value
                assert signup.status == 200 and signup.json().get("status") == "otp_required"
                page.locator("#auth-otp-pane").wait_for(state="visible")
                original = json.loads(sink.read_text(encoding="utf-8"))["code"]
                page.locator("#btn-resend-otp").evaluate("el => el.style.display = ''")
                with page.expect_response(lambda r:r.url.endswith("/api/auth/resend-otp")) as resend_event:
                    page.locator("#btn-resend-otp").click()
                resend = resend_event.value
                body = resend.json()
                assert resend.status == 200 and "Any previous code is now invalid" in body.get("message", "")
                replacement = json.loads(sink.read_text(encoding="utf-8"))["code"]
                assert replacement != original and len(replacement) == 6
                toast = page.locator(".toast-notice").inner_text() if page.locator(".toast-notice").count() else ""
                assert "Any previous code is now invalid" in toast, toast
                page.locator("#auth-otp-code").fill(original)
                with page.expect_response(lambda r:r.url.endswith("/api/auth/verify-signup-otp")) as old_event:
                    page.locator("#auth-otp-submit-btn").click()
                old_resp = old_event.value
                assert old_resp.status == 400, old_resp.status
                assert page.locator("#auth-otp-pane").is_visible()
                page.locator("#auth-otp-code").fill(replacement)
                with page.expect_response(lambda r:r.url.endswith("/api/auth/verify-signup-otp")) as new_event:
                    page.locator("#auth-otp-submit-btn").click()
                new_resp = new_event.value
                assert new_resp.status == 200 and new_resp.json().get("status") == "success"
                assert page.locator("#auth-modal").is_hidden()
                assert not evidence["page_errors"] and not evidence["console_errors"], evidence
                evidence.update({"signup_otp_required":True,"resend_status":resend.status,"resend_notice_visible":True,"previous_code_rejected_status":old_resp.status,"latest_code_accepted_status":new_resp.status,"authenticated_only_after_latest_code":True,"expected_old_code_rejection_console_count":len(evidence["expected_rejection_console"]),"real_email_provider_used":False,"result":"passed"})
                browser.close()
        finally:
            app.terminate()
            try: app.wait(timeout=5)
            except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
    return evidence

def main():
    result = {"rounds":[run_round(1), run_round(2)], "result":"passed"}
    (OUT / "browser-id60-signup-resend.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))

if __name__ == "__main__": main()


