"""Verify the browser Executive Brief preserves an explicit INR amount."""
from __future__ import annotations
import json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

def main():
    evidence = {"page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-inr-") as tmp:
        temp = Path(tmp); data = temp / "data"; data.mkdir()
        pdf_path = temp / "inr-budget.pdf"
        with fitz.open() as pdf:
            pdf.new_page().insert_text((72,72), "Budget cap: INR 900,000. No spending is authorized.")
            pdf.save(pdf_path)
        bootstrap = temp / "sitecustomize.py"
        bootstrap.write_text(
            "import sys\n"
            f"sys.path.insert(0, {str(ROOT)!r})\n"
            "import ai_engine\n"
            "ai_engine.call_llm = lambda *args, **kwargs: '### Executive Summary\\nThe budget is 900,000 (currency unspecified). No spending is authorized. [Page 1]'\n",
            encoding="utf-8",
        )
        with socket.socket() as sock:
            sock.bind(("127.0.0.1",0)); port=sock.getsockname()[1]
        env={k:v for k,v in os.environ.items() if not k.upper().startswith(("PAPERPLANE_","CASHFREE_","SMTP_","RESEND_","OPENAI_","OPENROUTER_","BLUESMINDS_","ANTHROPIC_","GEMINI_","DEEPSEEK_","GOOGLE_API_","AI_","ADMIN_")) and k not in {"TESTING","SESSION_SECRET_KEY"}}
        env.update({"PAPERPLANE_SKIP_DOTENV":"1","PAPERPLANE_ENV":"development","PAPERPLANE_DATA_DIR":str(data),"PAPERPLANE_PORT":str(port),"PAPERPLANE_ADMIN_KEY":secrets.token_urlsafe(48),"PAPERPLANE_ADMIN_CODE":secrets.token_urlsafe(32),"PAPERPLANE_SESSION_SECRET":secrets.token_urlsafe(48),"PAPERPLANE_SECURE_COOKIES":"false","PYTHONPATH":str(temp)+os.pathsep+str(ROOT),"PYTHONIOENCODING":"utf-8"})
        seed = "import json; from persistence import init_db,create_user,create_session,set_user_tier; init_db(); e='inr-summary@example.invalid'; p='Synthetic-Inr-Summary-318!'; u=create_user(e,p); set_user_tier(u,'developer'); print(json.dumps({'token':create_session(e,p)['token']}))"
        identity=json.loads(subprocess.run([sys.executable,"-c",seed],cwd=ROOT,env=env,capture_output=True,text=True,check=True,timeout=30).stdout)
        app=subprocess.Popen([sys.executable,"app.py"],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1",port),timeout=.2): break
                except OSError: time.sleep(.2)
            else: raise RuntimeError("Local server failed to start")
            with sync_playwright() as p:
                browser=p.chromium.launch(channel="chrome",headless=True)
                context=browser.new_context(viewport={"width":1280,"height":900})
                context.add_cookies([{"name":"paperplane_token","value":identity["token"],"url":f"http://127.0.0.1:{port}","httpOnly":True,"secure":False,"sameSite":"Lax"}])
                page=context.new_page()
                page.on("pageerror",lambda e:evidence["page_errors"].append(str(e)))
                page.on("console",lambda m:evidence["console_errors"].append(m.text) if m.type=="error" else None)
                def local_capability_stub(route):
                    response=route.fetch(); payload=response.json(); payload["executive_brief_available"]=True
                    route.fulfill(response=response,json=payload)
                page.route("**/api/ai/capabilities",local_capability_stub)
                response=page.goto(f"http://127.0.0.1:{port}/ai-intelligence",wait_until="domcontentloaded"); assert response and response.status==200
                page.locator("#ai-file-input").set_input_files(str(pdf_path))
                page.wait_for_function("state.files.length === 1")
                page.locator("#trigger-summary-btn").click()
                page.wait_for_function("document.querySelector('#summary-display')?.textContent.includes('INR 900,000')",timeout=20000)
                visible=page.locator("#summary-display").inner_text()
                assert "currency unspecified" not in visible.lower(),visible
                assert "No spending is authorized." in visible,visible
                evidence.update({"visible_summary":visible,"request_mode":page.locator("#summary-mode-badge").inner_text(),"result":"passed","server_side_provider":"controlled local stub","production_endpoints_contacted":False})
                assert not evidence["page_errors"],evidence
                assert not evidence["console_errors"],evidence
                browser.close()
        finally:
            app.terminate()
            try: app.wait(timeout=5)
            except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
    (OUT/"browser-summary-inr-currency.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    print(json.dumps(evidence,indent=2))

if __name__=="__main__": main()
