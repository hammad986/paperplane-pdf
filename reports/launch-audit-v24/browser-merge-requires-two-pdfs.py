"""Check Merge requires two files and content-check its actual two-page output."""
from __future__ import annotations
import json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent

def make_pdf(text):
    doc=fitz.open(); doc.new_page().insert_text((72,72),text); data=doc.tobytes(); doc.close(); return data

def main():
    first=make_pdf("MERGE SOURCE ONE"); second=make_pdf("MERGE SOURCE TWO")
    evidence={"page_errors":[],"console_errors":[]}
    with TemporaryDirectory(prefix="paperplane-v24-merge-") as name:
        temp=Path(name); data=temp/"data"; data.mkdir(); out=temp/"out"; out.mkdir()
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
                browser=p.chromium.launch(channel="chrome",headless=True); page=browser.new_page(viewport={"width":1280,"height":900},accept_downloads=True)
                page.on("pageerror",lambda e:evidence["page_errors"].append(str(e)))
                page.on("console",lambda m:evidence["console_errors"].append(m.text) if m.type=="error" else None)
                base=f"http://127.0.0.1:{port}/merge-pdf"
                response=page.goto(base,wait_until="domcontentloaded"); assert response and response.status==200
                page.locator("#file-input").set_input_files({"name":"one.pdf","mimeType":"application/pdf","buffer":first})
                page.wait_for_function("window.state?.files?.length===1")
                button=page.locator("#run-button")
                assert button.is_disabled()
                assert "at least two pdfs" in button.inner_text().lower(),button.inner_text()
                hint=page.locator("#file-hint").inner_text()
                assert "Select 2–" in hint,hint
                evidence["one_file"]={"run_disabled":True,"button":button.inner_text(),"hint":hint}

                page.goto(base,wait_until="domcontentloaded")
                page.locator("#file-input").set_input_files([
                    {"name":"one.pdf","mimeType":"application/pdf","buffer":first},
                    {"name":"two.pdf","mimeType":"application/pdf","buffer":second},
                ])
                page.wait_for_function("window.state?.files?.length===2")
                assert not button.is_disabled()
                button.click()
                link=page.locator("#result-download-link"); link.wait_for(state="visible",timeout=60000)
                with page.expect_download(timeout=30000) as info: link.click()
                download=info.value; path=out/download.suggested_filename; download.save_as(path)
                with fitz.open(path) as merged:
                    texts=[p.get_text().strip() for p in merged]
                assert len(texts)==2 and "MERGE SOURCE ONE" in texts[0] and "MERGE SOURCE TWO" in texts[1],texts
                evidence["two_files"]={"run_enabled":True,"download":download.suggested_filename,"bytes":path.stat().st_size,"pages":len(texts),"page_text":texts,"content_checked":True}
                assert not evidence["page_errors"],evidence; assert not evidence["console_errors"],evidence
                evidence["result"]="passed"; browser.close()
        finally:
            app.terminate()
            try: app.wait(timeout=5)
            except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
    (OUT/"browser-merge-requires-two-pdfs.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    print(json.dumps(evidence,indent=2))
if __name__=="__main__":main()
