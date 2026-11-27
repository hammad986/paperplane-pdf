"""Render the public 15-page arXiv sample in local Studio and capture visual evidence."""
from __future__ import annotations
import json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PDF = ROOT / "tmp/pdfs/arxiv-1706.03762-v7.pdf"

def main():
    evidence = {"page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-arxiv-") as tmp:
        data = Path(tmp) / "data"; data.mkdir()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
        env = {k:v for k,v in os.environ.items() if not k.upper().startswith(("PAPERPLANE_","CASHFREE_","SMTP_","RESEND_","OPENAI_","OPENROUTER_","BLUESMINDS_","ANTHROPIC_","GEMINI_","DEEPSEEK_","GOOGLE_API_","AI_","ADMIN_")) and k not in {"TESTING","SESSION_SECRET_KEY"}}
        env.update({"PAPERPLANE_SKIP_DOTENV":"1","PAPERPLANE_ENV":"development","PAPERPLANE_DATA_DIR":str(data),"PAPERPLANE_PORT":str(port),"PAPERPLANE_ADMIN_KEY":secrets.token_urlsafe(48),"PAPERPLANE_ADMIN_CODE":secrets.token_urlsafe(32),"PAPERPLANE_SESSION_SECRET":secrets.token_urlsafe(48),"PAPERPLANE_SECURE_COOKIES":"false","PYTHONPATH":str(ROOT)})
        app = subprocess.Popen([sys.executable,"app.py"],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1",port),timeout=.2): break
                except OSError: time.sleep(.2)
            else: raise RuntimeError("Local server failed to start")
            with sync_playwright() as p:
                browser=p.chromium.launch(channel="chrome",headless=True)
                page=browser.new_page(viewport={"width":1366,"height":1000},device_scale_factor=1)
                page.on("pageerror",lambda e:evidence["page_errors"].append(str(e)))
                page.on("console",lambda m:evidence["console_errors"].append(m.text) if m.type=="error" else None)
                response=page.goto(f"http://127.0.0.1:{port}/studio",wait_until="domcontentloaded"); assert response and response.status==200
                page.locator("#studio-file-input").set_input_files(str(PDF))
                page.wait_for_function("state.studio.pdfDoc && state.studio.totalCount === 15",timeout=30000)
                page.wait_for_function("document.querySelector('#studio-page-stack .studio-page-sheet[data-page=\"1\"] .pdf-page-canvas')?.dataset.rendered === 'true'",timeout=30000)
                page.locator("#studio-page-stack .studio-page-sheet[data-page='1'] .pdf-page-canvas").screenshot(path=str(OUT/"arxiv-studio-page1.png"))
                evidence["browser_render"] = page.evaluate("""() => ({pages:state.studio.totalCount,workerDisabled:state.studio.renderWorkerDisabled,workerFailure:state.studio.renderWorkerFailure,canvas:[document.querySelector('#pdf-canvas').width,document.querySelector('#pdf-canvas').height],canvasCss:[document.querySelector('#pdf-canvas').style.width,document.querySelector('#pdf-canvas').style.height],canvasText:document.querySelector('#pdf-canvas').getAttribute('aria-label')})""")
                evidence["source_text"] = "Attention Is All You Need"
                assert evidence["browser_render"]["pages"]==15
                assert not evidence["page_errors"],evidence
                assert not evidence["console_errors"],evidence
                evidence["result"]="rendered"
                browser.close()
        finally:
            app.terminate()
            try: app.wait(timeout=5)
            except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
    (OUT/"browser-arxiv-studio-render.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    print(json.dumps(evidence,indent=2))

if __name__=="__main__": main()
