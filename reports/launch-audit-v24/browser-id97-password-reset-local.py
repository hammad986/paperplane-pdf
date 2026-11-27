"""Verify the full password-reset interface using the development-only reset link."""
from __future__ import annotations
import json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

def main():
    with TemporaryDirectory(prefix="paperplane-v24-id97-") as tmp:
        temp = Path(tmp); data = temp / "data"
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
        env = {k:v for k,v in os.environ.items() if not k.upper().startswith(("PAPERPLANE_","CASHFREE_","SMTP_","RESEND_","OPENAI_","OPENROUTER_","BLUESMINDS_","ANTHROPIC_","GEMINI_","DEEPSEEK_","GOOGLE_API_","AI_","ADMIN_")) and k not in {"TESTING","SESSION_SECRET_KEY"}}
        env.update({"PAPERPLANE_SKIP_DOTENV":"1","PAPERPLANE_ENV":"development","PAPERPLANE_DATA_DIR":str(data),"PAPERPLANE_PORT":str(port),"PAPERPLANE_ADMIN_KEY":secrets.token_urlsafe(48),"PAPERPLANE_ADMIN_CODE":secrets.token_urlsafe(32),"PAPERPLANE_SESSION_SECRET":secrets.token_urlsafe(48),"PAPERPLANE_SECURE_COOKIES":"false","PYTHONPATH":str(ROOT),"PYTHONIOENCODING":"utf-8"})
        email = "id97-reset@example.invalid"
        seed = "from persistence import init_db,create_user; init_db(); create_user(" + repr(email) + ",'Old-Synthetic-Password!23')"
        subprocess.run([sys.executable,"-c",seed],cwd=ROOT,env=env,capture_output=True,text=True,check=True,timeout=30)
        app = subprocess.Popen([sys.executable,"app.py"],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        evidence = {"production_endpoints_contacted":False,"real_email_sent":False,"page_errors":[],"console_errors":[]}
        try:
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1",port),timeout=.2): break
                except OSError: time.sleep(.2)
            else: raise RuntimeError("local server did not start")
            base=f"http://127.0.0.1:{port}"
            with sync_playwright() as p:
                browser=p.chromium.launch(channel="chrome",headless=True)
                page=browser.new_page(viewport={"width":1280,"height":900})
                page.on("pageerror",lambda e:evidence["page_errors"].append(str(e)))
                page.on("console",lambda m:evidence["console_errors"].append(m.text) if m.type=="error" else None)
                page.goto(base+"/",wait_until="domcontentloaded")
                page.locator("#topbar-signin-btn").click()
                page.locator("#link-forgot-password").click()
                page.locator("#forgot-email").fill(email)
                with page.expect_response(lambda r:r.url.endswith("/api/auth/forgot-password")) as request:
                    page.locator("#forgot-submit-btn").click()
                response=request.value; assert response.status==200
                payload=response.json(); reset_url=payload.get("dev_reset_url")
                assert reset_url and reset_url.startswith(base+"/?reset_token="),payload
                page.locator("#forgot-message").get_by_role("link",name="[Dev Mode] Click here to open reset password link").click()
                page.wait_for_function("document.querySelector('#reset-password-modal')?.hidden===false")
                token=page.locator("#reset-token").input_value(); assert token
                new_password="New-Synthetic-Password!24"
                page.locator("#reset-new-password").fill(new_password)
                page.locator("#reset-confirm-password").fill(new_password)
                with page.expect_response(lambda r:r.url.endswith("/api/auth/reset-password")) as reset_request:
                    page.locator("#reset-submit-btn").click()
                reset_response=reset_request.value; assert reset_response.status==200,reset_response.status
                assert page.locator("#reset-password-modal").is_hidden()
                replay=page.request.post(base+"/api/auth/reset-password",data={"token":token,"new_password":"Replay-Attempt!25"})
                assert replay.status==400,replay.status
                evidence.update({"request_status":response.status,"generic_recovery_message":payload.get("message"),"dev_only_reset_link_rendered":True,"reset_status":reset_response.status,"single_use_replay_status":replay.status,"result":"passed"})
                assert not evidence["page_errors"],evidence
                assert not evidence["console_errors"],evidence
                browser.close()
        finally:
            app.terminate()
            try: app.wait(timeout=5)
            except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
    (OUT/"browser-id97-password-reset-local.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    print(json.dumps(evidence,indent=2))

if __name__=="__main__": main()
