"""Browser-test OTP delivery success/failure with a local fake mail sender."""
from __future__ import annotations
import json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent

def main():
  evidence={"delivery_failure":{},"delivery_success":{},"page_errors":[],"console_errors":[],"expected_error_console":[]}
  with TemporaryDirectory(prefix="paperplane-v24-otp-mail-") as name:
    temp=Path(name); data=temp/"data"; data.mkdir(); sink=temp/"mail-sink.json"
    with socket.socket() as sock: sock.bind(("127.0.0.1",0)); port=sock.getsockname()[1]
    runner=temp/"controlled_server.py"
    runner.write_text('''import json, os, uvicorn\nfrom pathlib import Path\nimport server\ndef fake_send(to_email, code, purpose):\n    if to_email.startswith("unavailable-"): return False\n    Path(os.environ["PAPERPLANE_TEST_MAIL_SINK"]).write_text(json.dumps({"code":code,"purpose":purpose}), encoding="utf-8")\n    return True\nserver.send_otp_email = fake_send\nuvicorn.run(server.app, host="127.0.0.1", port=int(os.environ["PAPERPLANE_PORT"]), log_level="error")\n''',encoding="utf-8")
    env={k:v for k,v in os.environ.items() if not k.upper().startswith(("PAPERPLANE_","CASHFREE_","SMTP_","RESEND_","OPENAI_","OPENROUTER_","BLUESMINDS_","ANTHROPIC_","GEMINI_","DEEPSEEK_","GOOGLE_API_","AI_","ADMIN_")) and k not in {"TESTING","SESSION_SECRET_KEY"}}
    env.update({"PAPERPLANE_SKIP_DOTENV":"1","PAPERPLANE_ENV":"development","PAPERPLANE_DATA_DIR":str(data),"PAPERPLANE_PORT":str(port),"PAPERPLANE_ADMIN_KEY":secrets.token_urlsafe(48),"PAPERPLANE_ADMIN_CODE":secrets.token_urlsafe(32),"PAPERPLANE_SESSION_SECRET":secrets.token_urlsafe(48),"PAPERPLANE_SECURE_COOKIES":"false","PAPERPLANE_TEST_MAIL_SINK":str(sink),"PYTHONPATH":str(ROOT)})
    app=subprocess.Popen([sys.executable,str(runner)],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
      for _ in range(120):
        try:
          with socket.create_connection(("127.0.0.1",port),timeout=.2): break
        except OSError: time.sleep(.2)
      else: raise RuntimeError("Local test server did not start")
      with sync_playwright() as p:
        browser=p.chromium.launch(channel="chrome",headless=True); page=browser.new_page(viewport={"width":1280,"height":900})
        page.on("pageerror",lambda e:evidence["page_errors"].append(str(e))); page.on("console",lambda m:(evidence["expected_error_console"].append(m.text) if m.type=="error" and "503 (Service Unavailable)" in m.text else evidence["console_errors"].append(m.text)) if m.type=="error" else None)
        page.goto(f"http://127.0.0.1:{port}/",wait_until="domcontentloaded")
        page.evaluate("window.openAuthModal('', 'register')")
        failure_email=f"unavailable-{secrets.token_hex(4)}@example.test"
        page.locator("#auth-email").fill(failure_email); page.locator("#auth-password").fill("SecurePass!23456"); page.locator("#auth-confirm-password").fill("SecurePass!23456")
        with page.expect_response(lambda r:r.url.endswith("/api/auth/register")) as failure_event: page.locator("#auth-submit-btn").click()
        failure_response=failure_event.value; failure_body=failure_response.json()
        assert failure_response.status==503 and failure_body.get("detail")=="Email delivery is unavailable. Please try again later or contact support."
        assert page.locator("#auth-otp-pane").is_hidden() and page.locator("#auth-error").is_visible()
        assert not page.evaluate("localStorage.getItem('paperplane_token')") and not sink.exists()
        evidence["delivery_failure"]={"http_status":503,"message":"Email delivery is unavailable. Please try again later or contact support.","otp_step_hidden":True,"guest_session_retained":True,"code_not_exposed":True}
        page.evaluate("window.openAuthModal('', 'register')")
        success_email=f"delivered-{secrets.token_hex(4)}@example.test"
        page.locator("#auth-email").fill(success_email); page.locator("#auth-password").fill("SecurePass!23456"); page.locator("#auth-confirm-password").fill("SecurePass!23456")
        with page.expect_response(lambda r:r.url.endswith("/api/auth/register")) as success_event: page.locator("#auth-submit-btn").click()
        success_response=success_event.value; success_body=success_response.json()
        assert success_response.status==200 and success_body.get("status")=="otp_required" and "dev_otp" not in success_body
        page.locator("#auth-otp-pane").wait_for(state="visible")
        sent=json.loads(sink.read_text(encoding="utf-8")); assert sent["purpose"]=="signup" and len(sent["code"])==6
        page.locator("#auth-otp-code").fill(sent["code"])
        with page.expect_response(lambda r:r.url.endswith("/api/auth/verify-signup-otp")) as verify_event: page.locator("#auth-otp-submit-btn").click()
        verify=verify_event.value; verify_body=verify.json()
        assert verify.status==200 and verify_body.get("status")=="success" and verify_body.get("email")==success_email
        auth_me=page.evaluate("fetch('/api/auth/me').then(r=>r.json())")
        assert page.locator("#auth-modal").is_hidden() and auth_me.get("authenticated") is True, auth_me
        evidence["delivery_success"]={"register_status":200,"otp_required_without_dev_code":True,"verification_status":200,"authenticated_after_verified_code":True,"code_omitted_from_evidence":True}
        assert not evidence["page_errors"],evidence; assert not evidence["console_errors"],evidence
        evidence["result"]="passed"; browser.close()
    finally:
      app.terminate()
      try: app.wait(timeout=5)
      except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
  (OUT/"browser-otp-controlled-delivery.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
  print(json.dumps(evidence,indent=2))
if __name__=="__main__": main()
