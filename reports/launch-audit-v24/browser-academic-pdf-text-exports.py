"""Run local Chrome PDF-to-Markdown and DOCX exports on arXiv 1706.03762v7."""
from __future__ import annotations
import json, os, secrets, socket, subprocess, sys, time, zipfile
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
PDF=ROOT/"tmp/pdfs/arxiv-1706.03762-v7.pdf"

def export(page, base, route, ext, output_dir):
    page.goto(base+route,wait_until="domcontentloaded")
    internal_upload_name="a5e7074e4bb844cdb8a39a50783e06b5_browser-download-1706.03762v7.pdf"
    upload={"name":internal_upload_name,"mimeType":"application/pdf","buffer":PDF.read_bytes()} if ext==".md" else str(PDF)
    page.locator("#file-input").set_input_files(upload)
    page.locator("#run-button").click()
    link=page.locator("#result-download-link")
    link.wait_for(state="visible",timeout=120000)
    page.wait_for_function("document.querySelector('#result-meta')?.innerText.includes('math/custom-font glyphs were replaced')",timeout=120000)
    warning=page.locator("#result-meta").inner_text()
    with page.expect_download(timeout=60000) as info: link.click()
    download=info.value; target=output_dir/download.suggested_filename; download.save_as(target)
    if ext==".md":
        content=target.read_text(encoding="utf-8")
        assert "Attention Is All You Need" in content
        leaked = re.search(r"^#\s+[^\n]*a5e7074e4bb844cdb8a39a50783e06b5", content, re.I | re.M)
        if leaked:
            (OUT / "browser-academic-debug.md").write_text(content, encoding="utf-8")
            raise AssertionError(f"Internal UUID heading leaked: {leaked.group(0)!r}; top={content[:500]!r}")
        assert "[math/custom glyph]" in content
        normalized=re.sub(r"\s+"," ",content)
        spacing_phrases=(
            "performing models also connect the encoder and decoder through an attention mechanism.",
            "We propose a new simple network architecture, the Transformer,",
        )
        joined_patterns=("performingmodels", "mechanism.We", "architecture,the")
        assert all(phrase in normalized for phrase in spacing_phrases), normalized[:3000]
        assert not any(pattern in normalized for pattern in joined_patterns), normalized[:3000]
        checked={"kind":"markdown","bytes":len(content.encode()),"paper_title_text_present":True,"internal_uuid_heading_absent":True,"fallback_marker_count":content.count("[math/custom glyph]"),"spacing_phrases_preserved":list(spacing_phrases),"joined_word_patterns_found":[]}
    else:
        assert zipfile.is_zipfile(target)
        with zipfile.ZipFile(target) as archive:
            assert archive.testzip() is None
            xml=archive.read("word/document.xml").decode("utf-8")
        assert "Attention Is All You Need" in xml
        assert "[math/custom glyph]" in xml
        checked={"kind":"docx","bytes":target.stat().st_size,"zip_integrity":"passed","title_present":True,"fallback_marker_count":xml.count("[math/custom glyph]")}
    checked["warning_shown"]="math/custom-font glyphs were replaced" in warning
    assert checked["warning_shown"],warning
    return checked

def main():
    if not PDF.exists(): raise FileNotFoundError(PDF)
    evidence={"source_pdf":str(PDF),"source_bytes":PDF.stat().st_size,"cases":{},"page_errors":[],"console_errors":[]}
    with TemporaryDirectory(prefix="paperplane-v24-academic-") as name:
        temp=Path(name); data=temp/"data"; data.mkdir(); outputs=temp/"outputs"; outputs.mkdir()
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
                browser=p.chromium.launch(channel="chrome",headless=True); page=browser.new_page(viewport={"width":1366,"height":900},accept_downloads=True)
                page.on("pageerror",lambda e:evidence["page_errors"].append(str(e)))
                page.on("console",lambda m:evidence["console_errors"].append(m.text) if m.type=="error" else None)
                base=f"http://127.0.0.1:{port}"
                evidence["cases"]["pdf_to_markdown"]=export(page,base,"/pdf-to-markdown",".md",outputs)
                evidence["cases"]["pdf_to_word"]=export(page,base,"/pdf-to-word",".docx",outputs)
                assert not evidence["page_errors"],evidence; assert not evidence["console_errors"],evidence
                evidence["result"]="passed"; browser.close()
        finally:
            app.terminate()
            try: app.wait(timeout=5)
            except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
    (OUT/"browser-academic-pdf-text-exports.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    print(json.dumps(evidence,indent=2))
if __name__=="__main__":main()
