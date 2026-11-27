"""Check Edit PDF suite naming and Flatten breadcrumb in local Chrome."""
from __future__ import annotations
import json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent

def main():
    evidence={"page_errors":[],"console_errors":[]}
    with TemporaryDirectory(prefix="paperplane-v24-naming-") as name:
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
                browser=p.chromium.launch(channel="chrome",headless=True); page=browser.new_page(viewport={"width":1280,"height":900})
                page.on("pageerror",lambda e:evidence["page_errors"].append(str(e)))
                page.on("console",lambda m:evidence["console_errors"].append(m.text) if m.type=="error" else None)
                response=page.goto(f"http://127.0.0.1:{port}/flatten-pdf",wait_until="domcontentloaded"); assert response and response.status==200
                nav=page.locator('[data-category="Edit"]')
                evidence["sidebar"]={"text":nav.locator("span").nth(1).inner_text(),"aria_label":nav.get_attribute("aria-label"),"title":nav.get_attribute("title")}
                evidence["breadcrumb"]=page.locator("#crumb-category").inner_text()
                assert evidence["sidebar"]=={"text":"Edit PDF","aria_label":"Edit PDF tools","title":"Edit PDF tools"}
                assert evidence["breadcrumb"]=="Edit PDF",evidence
                assert not evidence["page_errors"],evidence; assert not evidence["console_errors"],evidence
                evidence["result"]="passed"; browser.close()
        finally:
            app.terminate()
            try: app.wait(timeout=5)
            except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
    (OUT/"browser-edit-suite-naming.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    print(json.dumps(evidence,indent=2))
if __name__=="__main__":main()
