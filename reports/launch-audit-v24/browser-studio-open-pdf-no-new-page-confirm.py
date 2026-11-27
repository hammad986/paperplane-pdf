"""Verify Studio Open PDF opens the file picker without a blank-page confirm."""
from __future__ import annotations
import json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent

def make_pdf(path,text):
    doc=fitz.open(); doc.new_page().insert_text((72,72),text); doc.save(path); doc.close()

def main():
    evidence={"viewports":[],"page_errors":[],"console_errors":[]}
    with TemporaryDirectory(prefix="paperplane-v24-open-pdf-") as name:
        temp=Path(name); data=temp/"data"; data.mkdir(); source=temp/"source.pdf"; replacement=temp/"replacement.pdf"
        make_pdf(source,"Original Studio document"); make_pdf(replacement,"Replacement Studio document")
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
                for width in (1366,820,390):
                    page=browser.new_page(viewport={"width":width,"height":900})
                    page.on("pageerror",lambda e:evidence["page_errors"].append(str(e)))
                    page.on("console",lambda m:evidence["console_errors"].append(m.text) if m.type=="error" else None)
                    page.goto(f"http://127.0.0.1:{port}/studio",wait_until="domcontentloaded")
                    page.locator("#studio-file-input").set_input_files(str(source))
                    page.wait_for_function("window.state?.studio?.pdfDoc && window.state.studio.totalCount===1",timeout=20000)
                    button=page.get_by_role("button",name="Open PDF from device")
                    button.scroll_into_view_if_needed()
                    box=button.bounding_box(); assert box and box["width"]>0 and box["height"]>0,(width,box)
                    new_page_box=page.locator("#studio-close-doc-btn").bounding_box()
                    intersection=(max(0,min(box["x"]+box["width"],new_page_box["x"]+new_page_box["width"])-max(box["x"],new_page_box["x"]))
                                 * max(0,min(box["y"]+box["height"],new_page_box["y"]+new_page_box["height"])-max(box["y"],new_page_box["y"]))) if new_page_box else 0
                    hit=page.evaluate("({x,y}) => document.elementFromPoint(x,y)?.closest('#studio-upload-btn')?.id || null",{"x":box["x"]+box["width"]/2,"y":box["y"]+box["height"]/2})
                    assert hit=="studio-upload-btn",{"width":width,"button":box,"hit":hit}
                    opened=0
                    last_file=source
                    for attempt in range(5):
                        next_file=replacement if last_file==source else source
                        with page.expect_file_chooser(timeout=10000) as chooser_info:
                            button.click()
                        chooser_info.value.set_files(str(next_file))
                        expected_name=next_file.name
                        page.wait_for_function("name => window.state?.studio?.pdfDoc && window.state.studio.srcFile?.name===name",arg=expected_name,timeout=20000)
                        assert page.locator(".app-confirm-dialog").count()==0
                        last_file=next_file
                        opened+=1
                    evidence["viewports"].append({"width":width,"open_button_hit":"studio-upload-btn","new_page_button_box":new_page_box,"button_intersection_area":intersection,"file_chooser_opens":opened,"replacement_loaded_each_time":True,"blank_page_confirmation":False})
                    page.close()
                assert not evidence["page_errors"],evidence; assert not evidence["console_errors"],evidence
                evidence["result"]="passed"; browser.close()
        finally:
            app.terminate()
            try: app.wait(timeout=5)
            except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
    (OUT/"browser-studio-open-pdf-no-new-page-confirm.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    print(json.dumps(evidence,indent=2))
if __name__=="__main__":main()
