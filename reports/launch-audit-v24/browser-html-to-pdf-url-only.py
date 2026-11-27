"""Verify the URL-only HTML converter has no file-upload controls."""
from __future__ import annotations
import json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent

def main():
    evidence={"viewports":[],"page_errors":[],"console_errors":[]}
    with TemporaryDirectory(prefix="paperplane-v24-html-url-") as name:
        temp=Path(name); data=temp/"data"; data.mkdir()
        with socket.socket() as s: s.bind(("127.0.0.1",0)); port=s.getsockname()[1]
        env={k:v for k,v in os.environ.items() if not k.upper().startswith(("PAPERPLANE_","CASHFREE_","SMTP_","RESEND_","OPENAI_","OPENROUTER_","BLUESMINDS_","ANTHROPIC_","GEMINI_","DEEPSEEK_","GOOGLE_API_","AI_","ADMIN_")) and k not in {"TESTING","SESSION_SECRET_KEY"}}
        env.update({"PAPERPLANE_SKIP_DOTENV":"1","PAPERPLANE_ENV":"development","PAPERPLANE_DATA_DIR":str(data),"PAPERPLANE_PORT":str(port),"PAPERPLANE_ADMIN_KEY":secrets.token_urlsafe(48),"PAPERPLANE_ADMIN_CODE":secrets.token_urlsafe(32),"PAPERPLANE_SESSION_SECRET":secrets.token_urlsafe(48),"PAPERPLANE_SECURE_COOKIES":"false","PYTHONPATH":str(ROOT)})
        app=subprocess.Popen([sys.executable,"app.py"],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1",port),timeout=.2): break
                except OSError: time.sleep(.2)
            else: raise RuntimeError("Local server did not start")
            with sync_playwright() as p:
                browser=p.chromium.launch(channel="chrome",headless=True)
                for width in (1366,390):
                    page=browser.new_page(viewport={"width":width,"height":900})
                    page.on("pageerror",lambda e:evidence["page_errors"].append(str(e)))
                    page.on("console",lambda m:evidence["console_errors"].append(m.text) if m.type=="error" else None)
                    response=page.goto(f"http://127.0.0.1:{port}/html-to-pdf",wait_until="domcontentloaded"); assert response and response.status==200
                    assert page.locator("#dropzone").is_hidden()
                    assert page.locator("#browse").is_hidden()
                    assert page.locator("#cloud-drop-btn").is_hidden()
                    url=page.locator("#url"); assert url.is_visible()
                    helper=page.get_by_text("This tool does not accept PDF or document uploads.")
                    assert helper.is_visible()
                    initial=page.locator("#run-button").inner_text()
                    url.fill("invalid-url"); invalid=page.locator("#run-button")
                    assert invalid.is_disabled()
                    url.fill("https://example.com/annual-report")
                    assert not invalid.is_disabled()
                    assert "Convert URL to PDF" in invalid.inner_text()
                    evidence["viewports"].append({"width":width,"upload_zone_hidden":True,"url_field_visible":True,"upload_prohibited_copy":helper.inner_text(),"invalid_url_disables_run":True,"public_url_enables_url_cta":True,"initial_cta":initial})
                    assert page.locator("#dropzone").is_hidden()
                    page.close()
                assert not evidence["page_errors"],evidence; assert not evidence["console_errors"],evidence
                evidence["result"]="passed"; browser.close()
        finally:
            app.terminate()
            try: app.wait(timeout=5)
            except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
    (OUT/"browser-html-to-pdf-url-only.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    print(json.dumps(evidence,indent=2))
if __name__=="__main__":main()
