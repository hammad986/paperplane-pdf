"""Download and content-check local Compare PDF verdict outputs in Chrome."""
from __future__ import annotations
import json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent

def pdf(text):
    doc=fitz.open(); page=doc.new_page(); page.insert_text((72,72),text); data=doc.tobytes(); doc.close(); return data

def run_case(page, left, right, expected):
    page.locator("#file-input").set_input_files([
        {"name":"left.pdf","mimeType":"application/pdf","buffer":left},
        {"name":"right.pdf","mimeType":"application/pdf","buffer":right},
    ])
    page.locator("#run-button").click()
    link=page.locator("#result-download-link")
    link.wait_for(state="visible",timeout=30000)
    with page.expect_download(timeout=20000) as info: link.click()
    download=info.value
    temp=Path(TemporaryDirectory(prefix="paperplane-compare-output-").name)
    temp.mkdir(parents=True,exist_ok=True)
    path=temp/download.suggested_filename
    download.save_as(path)
    text=path.read_text(encoding="utf-8")
    assert text.startswith("Verdict: "), text[:300]
    assert expected in text.splitlines()[0], text.splitlines()[0]
    path.unlink(); temp.rmdir()
    return {"filename":download.suggested_filename,"bytes":len(text.encode()),"verdict":text.splitlines()[0],"content_checked":True}

def main():
    evidence={"cases":{},"page_errors":[],"console_errors":[]}
    with TemporaryDirectory(prefix="paperplane-v24-compare-") as temp_name:
        temp=Path(temp_name); data=temp/"data"; data.mkdir()
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
                response=page.goto(f"http://127.0.0.1:{port}/compare-pdf",wait_until="domcontentloaded"); assert response and response.status==200
                same=pdf("Same comparison content")
                evidence["cases"]["identical"]=run_case(page,same,same,"Files are identical in selectable text — no differences found.")
                page.reload(wait_until="domcontentloaded")
                evidence["cases"]["different"]=run_case(page,pdf("Original comparison line"),pdf("Updated comparison line"),"differences found.")
                assert not evidence["page_errors"],evidence; assert not evidence["console_errors"],evidence
                evidence["result"]="passed"; browser.close()
        finally:
            app.terminate()
            try: app.wait(timeout=5)
            except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
    (OUT/"browser-compare-verdict.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    print(json.dumps(evidence,indent=2))

if __name__=="__main__": main()
