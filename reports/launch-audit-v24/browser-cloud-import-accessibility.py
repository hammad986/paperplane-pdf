"""Exercise Cloud Import dialog focus management in real local Chrome."""
from __future__ import annotations
import json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent

def main():
    evidence={"viewports":[],"page_errors":[],"console_errors":[]}
    with TemporaryDirectory(prefix="paperplane-v24-cloud-a11y-") as name:
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
            else: raise RuntimeError("Local Paperplane server did not start")
            with sync_playwright() as p:
                browser=p.chromium.launch(channel="chrome",headless=True)
                for width in (1366,390):
                    page=browser.new_page(viewport={"width":width,"height":900})
                    page.on("pageerror",lambda e:evidence["page_errors"].append(str(e)))
                    page.on("console",lambda m:evidence["console_errors"].append(m.text) if m.type=="error" else None)
                    response=page.goto(f"http://127.0.0.1:{port}/ai-intelligence",wait_until="domcontentloaded"); assert response and response.status==200
                    opener=page.locator("#topbar-cloud-btn"); opener.wait_for(state="visible"); opener.click()
                    dialog=page.get_by_role("dialog",name="Cloud Document Import"); assert dialog.is_visible()
                    close=page.get_by_role("button",name="Close Cloud Import dialog")
                    url=page.locator("#cloud-url"); submit=page.locator("#cloud-submit-btn")
                    assert page.evaluate("document.activeElement.id") == "cloud-url"
                    page.keyboard.press("Shift+Tab"); assert page.evaluate("document.activeElement.id") == "close-cloud-modal"
                    page.keyboard.press("Tab"); assert page.evaluate("document.activeElement.id") == "cloud-url"
                    page.keyboard.press("Shift+Tab"); assert page.evaluate("document.activeElement.id") == "close-cloud-modal"
                    page.keyboard.press("Tab"); page.keyboard.press("Tab"); assert page.evaluate("document.activeElement.id") == "cloud-submit-btn"
                    page.keyboard.press("Tab"); assert page.evaluate("document.activeElement.id") == "close-cloud-modal"
                    page.keyboard.press("Escape"); assert dialog.is_hidden()
                    assert page.evaluate("document.activeElement.id") == "topbar-cloud-btn"
                    opener.click(); close.click(); assert dialog.is_hidden()
                    assert page.evaluate("document.activeElement.id") == "topbar-cloud-btn"
                    evidence["viewports"].append({"width":width,"named_dialog":True,"initial_focus":"cloud-url","shift_tab_wraps_to_close":True,"tab_wraps_to_close":True,"escape_closes_and_restores_focus":True,"close_button_restores_focus":True})
                    page.close()
                assert not evidence["page_errors"],evidence; assert not evidence["console_errors"],evidence
                evidence["result"]="passed"; browser.close()
        finally:
            app.terminate()
            try: app.wait(timeout=5)
            except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
    (OUT/"browser-cloud-import-accessibility.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    print(json.dumps(evidence,indent=2))
if __name__=="__main__": main()
