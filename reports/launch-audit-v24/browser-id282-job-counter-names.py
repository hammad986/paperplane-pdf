"""Check that internal upload/job IDs never leak into document names or diff text."""
from __future__ import annotations
import json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
def make_pdf(text, title=""):
    doc=fitz.open(); page=doc.new_page(); page.insert_text((72,72),text)
    if title: doc.set_metadata({"title":title})
    return doc.tobytes()
def main():
    evidence={"cases":{},"page_errors":[],"console_errors":[]}
    with TemporaryDirectory(prefix="paperplane-v24-id282-") as tmp:
        temp=Path(tmp); data=temp/"data"; data.mkdir(); outputs=temp/"outputs"; outputs.mkdir()
        with socket.socket() as sock: sock.bind(("127.0.0.1",0)); port=sock.getsockname()[1]
        env={k:v for k,v in os.environ.items() if not k.upper().startswith(("PAPERPLANE_","CASHFREE_","SMTP_","RESEND_","OPENAI_","OPENROUTER_","BLUESMINDS_","ANTHROPIC_","GEMINI_","DEEPSEEK_","GOOGLE_API_","AI_","ADMIN_")) and k not in {"TESTING","SESSION_SECRET_KEY"}}
        env.update({"PAPERPLANE_SKIP_DOTENV":"1","PAPERPLANE_ENV":"development","PAPERPLANE_DATA_DIR":str(data),"PAPERPLANE_PORT":str(port),"PAPERPLANE_ADMIN_KEY":secrets.token_urlsafe(48),"PAPERPLANE_ADMIN_CODE":secrets.token_urlsafe(32),"PAPERPLANE_SESSION_SECRET":secrets.token_urlsafe(48),"PAPERPLANE_SECURE_COOKIES":"false","PYTHONPATH":str(ROOT)})
        app=subprocess.Popen([sys.executable,"app.py"],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1",port),timeout=.2): break
                except OSError: time.sleep(.2)
            else: raise RuntimeError("local app did not start")
            with sync_playwright() as p:
                browser=p.chromium.launch(channel="chrome",headless=True); page=browser.new_page(viewport={"width":1280,"height":900},accept_downloads=True)
                page.add_init_script("localStorage.setItem('paperplane-pdf-processing-mode','server')")
                page.on("pageerror",lambda e:evidence["page_errors"].append(str(e)))
                page.on("console",lambda m:evidence["console_errors"].append(m.text) if m.type=="error" else None)
                base=f"http://127.0.0.1:{port}"
                source=outputs/"21-original.pdf"; source.write_bytes(make_pdf("Numbered source filename marker", "Customer Technical Report"))
                page.goto(base+"/compress-pdf",wait_until="domcontentloaded")
                page.locator("#file-input").set_input_files(str(source)); page.wait_for_function("state.files?.length===1")
                visible_upload=page.locator("#file-list").inner_text()
                assert "21-original.pdf" in visible_upload,visible_upload
                page.locator("#run-button").click(); link=page.locator("#result-download-link"); link.wait_for(state="visible",timeout=60000)
                page.wait_for_function("(()=>{let r=document.querySelector('#result-download-link')?.getBoundingClientRect();return r&&r.width>0})()",timeout=10000)
                with page.expect_download(timeout=30000) as info: link.click()
                download=info.value; target=outputs/download.suggested_filename; download.save_as(target)
                with fitz.open(target) as output: compressed_valid=output.page_count==1 and "Numbered source" in output[0].get_text()
                assert download.suggested_filename=="21-original_compress.pdf",download.suggested_filename
                evidence["cases"]["upload_and_compress_name"]={"upload_chip":visible_upload,"download_name":download.suggested_filename,"pdf_content_checked":compressed_valid}

                page.goto(base+"/compare-pdf",wait_until="domcontentloaded")
                page.locator("#file-input").set_input_files([
                    {"name":"19-before.pdf","mimeType":"application/pdf","buffer":make_pdf("Original text line")},
                    {"name":"20-after.pdf","mimeType":"application/pdf","buffer":make_pdf("Revised text line")},
                ])
                page.wait_for_function("state.files?.length===2")
                page.locator("#run-button").click(); link=page.locator("#result-download-link"); link.wait_for(state="visible",timeout=60000)
                page.wait_for_function("(()=>{let r=document.querySelector('#result-download-link')?.getBoundingClientRect();return r&&r.width>0})()",timeout=10000)
                with page.expect_download(timeout=30000) as info: link.click()
                dl=info.value; diff=outputs/dl.suggested_filename; dl.save_as(diff); diff_text=diff.read_text(encoding="utf-8")
                assert "--- 19-before.pdf" in diff_text and "+++ 20-after.pdf" in diff_text,diff_text
                assert not any(line.startswith(("--- ","+++ ")) and "_19-before" in line or "_20-after" in line for line in diff_text.splitlines())
                evidence["cases"]["compare_diff_names"]={"download_name":dl.suggested_filename,"input_headers":[line for line in diff_text.splitlines() if line.startswith(("--- ","+++ "))],"job_prefix_leaked":False}

                page.goto(base+"/pdf-to-markdown",wait_until="domcontentloaded")
                md_source=outputs/"21-original.pdf"
                with fitz.open() as source_doc:
                    markdown_page=source_doc.new_page()
                    markdown_page.insert_text((72,72),"Report body sentence one.",fontsize=12)
                    markdown_page.insert_text((72,96),"Report body sentence two.",fontsize=12)
                    markdown_page.insert_text((72,140),"Findings",fontsize=14)
                    source_doc.set_metadata({"title":""})
                    source_doc.save(md_source)
                page.locator("#file-input").set_input_files(str(md_source)); page.wait_for_function("state.files?.length===1")
                page.locator("#run-button").click(); link=page.locator("#result-download-link"); link.wait_for(state="visible",timeout=60000)
                page.wait_for_function("(()=>{let r=document.querySelector('#result-download-link')?.getBoundingClientRect();return r&&r.width>0})()",timeout=10000)
                with page.expect_download(timeout=30000) as info: link.click()
                dl=info.value; md=outputs/dl.suggested_filename; dl.save_as(md); markdown=md.read_text(encoding="utf-8")
                assert markdown.startswith("# 21-original\n"),markdown[:200]
                assert "Report body sentence one." in markdown and "Report body sentence two." in markdown
                assert "## Report body sentence" not in markdown
                assert "## Findings" in markdown
                assert not any(line.startswith("# ") and "job" in line.lower() for line in markdown.splitlines())
                evidence["cases"]["markdown_title_and_heading_semantics"]={"download_name":dl.suggested_filename,"h1":markdown.splitlines()[0],"body_paragraphs_are_headings":False,"real_heading_is_h2":"## Findings" in markdown,"job_id_leaked":False}
                assert not evidence["page_errors"],evidence["page_errors"]
                assert not evidence["console_errors"],evidence["console_errors"]
                browser.close()
        finally:
            app.terminate()
            try: app.wait(timeout=5)
            except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
    evidence["result"]="passed"
    (OUT/"browser-id282-job-counter-names.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    print(json.dumps(evidence,indent=2))
if __name__=="__main__": main()
