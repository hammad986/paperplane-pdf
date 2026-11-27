"""Verify server and browser PDF-to-Word claims against downloaded DOCX content."""
from __future__ import annotations
import io, json, os, secrets, socket, subprocess, sys, time, zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from docx import Document
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent

def fixture():
    doc=fitz.open()
    page=doc.new_page(width=612,height=792)
    page.insert_textbox(fitz.Rect(40,35,280,150),"LEFT COLUMN REPORT\nQuarterly operations summary\nRevenue was stable.",fontsize=11)
    page.insert_textbox(fitz.Rect(330,35,570,150),"RIGHT COLUMN REPORT\nRisk review\nCosts fell in the second quarter.",fontsize=11)
    for x in (70,210,350): page.draw_line((x,220),(x,300),color=(0,0,0),width=1)
    for y in (220,247,274,300): page.draw_line((70,y),(350,y),color=(0,0,0),width=1)
    for x,text in ((75,"Metric"),(215,"Value"),(355,"Revenue"),(75,"Cost"),(215,"12%"),(355,"$900")):
        page.insert_text((x,y:=235 if text in ("Metric","Value","Revenue") else 263),text,fontsize=10)
    image=Image.new("RGB",(120,60),"white"); ImageDraw.Draw(image).rectangle((8,8,112,52),outline="blue",width=4)
    png=io.BytesIO(); image.save(png,format="PNG")
    page.insert_image(fitz.Rect(380,230,500,290),stream=png.getvalue())
    second=doc.new_page(); second.insert_text((72,72),"SECOND PAGE CHECK — retain this text")
    return doc.tobytes()

def main():
    pdf=fixture(); evidence={"runs":[],"page_errors":[],"console_errors":[]}
    with TemporaryDirectory(prefix="paperplane-v24-word-fidelity-") as name:
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
                for mode in ("server","browser"):
                    context=browser.new_context(accept_downloads=True,viewport={"width":1280,"height":900})
                    context.add_init_script("localStorage.setItem('paperplane-pdf-processing-mode', '"+mode+"')")
                    page=context.new_page(); page.on("pageerror",lambda e:evidence["page_errors"].append(str(e))); page.on("console",lambda m:evidence["console_errors"].append(m.text) if m.type=="error" else None)
                    response=page.goto(f"http://127.0.0.1:{port}/pdf-to-word",wait_until="domcontentloaded"); assert response and response.status==200
                    mode_copy=page.locator("#options .option-help").first
                    mode_copy.wait_for(state="visible")
                    if mode=="server": assert "detected tables" in mode_copy.inner_text() and "pagination can change" in mode_copy.inner_text()
                    else: assert "text-first DOCX" in mode_copy.inner_text() and "does not retain images" in mode_copy.inner_text()
                    original_copy=mode_copy.inner_text()
                    page.locator("label.toggle-switch-sm:has(#client-privacy-toggle)").click()
                    if mode=="server":
                        assert "text-first DOCX" in mode_copy.inner_text()
                    else:
                        assert "Server mode rebuilds editable text" in mode_copy.inner_text()
                    page.locator("label.toggle-switch-sm:has(#client-privacy-toggle)").click()
                    assert mode_copy.inner_text()==original_copy
                    page.locator("input[type=file]").first.set_input_files({"name":"two-column-layout.pdf","mimeType":"application/pdf","buffer":pdf})
                    page.locator("#run-button").wait_for(state="visible")
                    page.wait_for_function("!document.querySelector('#run-button').disabled", timeout=15000)
                    assert page.locator("#client-privacy-toggle").is_checked() is (mode=="browser")
                    page.locator("#run-button").click()
                    page.get_by_text("Your document is ready!", exact=True).wait_for(state="visible",timeout=120000)
                    with page.expect_download(timeout=30000) as info:
                        page.locator("#result-download-link").click()
                    download=info.value; path=Path(download.path()); raw=path.read_bytes(); assert raw[:2]==b"PK" and zipfile.is_zipfile(path)
                    document=Document(path)
                    text="\n".join(paragraph.text for paragraph in document.paragraphs)
                    table_text=" ".join(cell.text for table in document.tables for row in table.rows for cell in row.cells)
                    all_text=text+"\n"+table_text
                    assert "LEFT COLUMN REPORT" in all_text and "RIGHT COLUMN REPORT" in all_text and "SECOND PAGE CHECK" in all_text
                    if mode=="server":
                        assert len(document.tables)>=1, f"server converter did not detect fixture table: {len(document.tables)}"
                        assert len(document.inline_shapes)>=1, f"server converter did not retain fixture image: {len(document.inline_shapes)}"
                        assert "server reconstruction" in page.locator("#result-meta").inner_text().lower()
                    else:
                        assert len(document.tables)==0 and len(document.inline_shapes)==0
                        assert "text-first editable DOCX" in page.locator("#result-meta").inner_text()
                        assert "server reconstruction" not in page.locator("#result-meta").inner_text().lower()
                    evidence["runs"].append({"mode":mode,"download_name":download.suggested_filename,"bytes":len(raw),"paragraphs":len(document.paragraphs),"tables":len(document.tables),"images":len(document.inline_shapes),"contains_both_columns_and_second_page":True,"mode_toggle_updates_disclosure_and_restores_it":True,"result_capability_disclosure":page.locator("#result-meta").inner_text()})
                    context.close()
                assert not evidence["page_errors"],evidence; assert not evidence["console_errors"],evidence
                evidence["result"]="passed"; browser.close()
        finally:
            app.terminate()
            try: app.wait(timeout=5)
            except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
    (OUT/"browser-pdf-to-word-capability-disclosure.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    print(json.dumps(evidence,indent=2))
if __name__=="__main__": main()
