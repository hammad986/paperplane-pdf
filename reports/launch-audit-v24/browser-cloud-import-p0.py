"""Content-check public direct PDF imports and Drive URL flow in local Chrome."""
from __future__ import annotations
import json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
CASES = [
    ("w3c_testfiles", "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf", "dummy.pdf"),
    ("arxiv_direct", "https://arxiv.org/pdf/1706.03762", "1706.03762"),
    ("public_drive_view", "https://drive.google.com/file/d/1d1JfUBhXbuGnQEEjnzPClMkvfdb8DVXS/view?usp=sharing", "Spirit Week Flyers"),
]

def main():
    evidence = {"cases": [], "page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-cloud-p0-") as name:
        temp=Path(name); data=temp/"data"; data.mkdir()
        with socket.socket() as s: s.bind(("127.0.0.1",0)); port=s.getsockname()[1]
        env={k:v for k,v in os.environ.items() if not k.upper().startswith(("PAPERPLANE_","CASHFREE_","SMTP_","RESEND_","OPENAI_","OPENROUTER_","BLUESMINDS_","ANTHROPIC_","GEMINI_","DEEPSEEK_","GOOGLE_API_","AI_","ADMIN_")) and k not in {"TESTING","SESSION_SECRET_KEY"}}
        env.update({"PAPERPLANE_SKIP_DOTENV":"1","PAPERPLANE_ENV":"development","PAPERPLANE_DATA_DIR":str(data),"PAPERPLANE_PORT":str(port),"PAPERPLANE_ADMIN_KEY":secrets.token_urlsafe(48),"PAPERPLANE_ADMIN_CODE":secrets.token_urlsafe(32),"PAPERPLANE_SESSION_SECRET":secrets.token_urlsafe(48),"PAPERPLANE_SECURE_COOKIES":"false","PYTHONPATH":str(ROOT)})
        app=subprocess.Popen([sys.executable,"app.py"],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1",port),timeout=.2): break
                except OSError: time.sleep(.2)
            else: raise RuntimeError("Local Paperplane server did not start")
            with sync_playwright() as p:
                browser=p.chromium.launch(channel="chrome",headless=True)
                page=browser.new_page(viewport={"width":1366,"height":900})
                page.on("pageerror",lambda e:evidence["page_errors"].append(str(e)))
                page.on("console",lambda m:evidence["console_errors"].append(m.text) if m.type=="error" else None)
                assert page.goto(f"http://127.0.0.1:{port}/merge-pdf",wait_until="domcontentloaded").status==200
                for case,url,marker in CASES:
                    page.locator("#topbar-cloud-btn").click()
                    page.locator("#cloud-url").fill(url)
                    page.locator("#cloud-submit-btn").click()
                    page.locator("#cloud-submit-btn").wait_for(state="visible")
                    page.wait_for_function("document.querySelector('#cloud-submit-btn').disabled === false", timeout=90000)
                    error=page.locator("#cloud-error")
                    error_text=error.inner_text().strip() if error.is_visible() else ""
                    body=page.locator("body").inner_text()
                    matched=marker.lower() in body.lower()
                    # API response is checked independently for actual PDF signature/page count.
                    request=page.request.post(f"http://127.0.0.1:{port}/api/cloud/sync",multipart={"file_url":url},timeout=90000)
                    payload=request.json() if request.ok else {}
                    item={"case":case,"ui_error":error_text,"ui_filename_visible":matched,"api_status":request.status}
                    if request.ok:
                        import base64, fitz
                        raw=base64.b64decode(payload["data_url"].split(",",1)[1])
                        doc=fitz.open(stream=raw,filetype="pdf")
                        item.update({"filename":payload.get("filename"),"bytes":len(raw),"signature":raw[:5].decode("ascii","replace"),"page_count":doc.page_count,"content_marker":doc[0].get_text()[:220]})
                        doc.close()
                        assert raw.startswith(b"%PDF-") and item["page_count"]>0
                    evidence["cases"].append(item)
                    if page.locator("#cloud-modal").is_visible():
                        page.locator("#close-cloud-modal").click()
                    if request.ok:
                        assert item["page_count"]>0
                assert not evidence["page_errors"],evidence
                # Browser may report neither network failures nor JS console errors for successful imports.
                assert not evidence["console_errors"],evidence
                evidence["result"]="passed" if all(x["api_status"]==200 for x in evidence["cases"]) else "partial"
                browser.close()
        finally:
            app.terminate()
            try: app.wait(timeout=5)
            except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
    (OUT/"browser-cloud-import-p0.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    print(json.dumps(evidence,indent=2))
if __name__=="__main__": main()
