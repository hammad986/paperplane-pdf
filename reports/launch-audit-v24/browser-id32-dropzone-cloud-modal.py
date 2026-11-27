"""Ensure file drops on tool upload surfaces never open Cloud Import implicitly."""
from __future__ import annotations
import base64, json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent/"browser-id32-dropzone-cloud-modal.json"

with TemporaryDirectory(prefix="paperplane-v24-id32-") as name:
    tmp=Path(name); data=tmp/"data"; data.mkdir(); pdf=tmp/"drop-test.pdf"
    with fitz.open() as doc:
        p=doc.new_page(); p.insert_text((72,72),"Tool dropzone regression marker")
        doc.save(pdf)
    with socket.socket() as sock: sock.bind(("127.0.0.1",0)); port=sock.getsockname()[1]
    env={k:v for k,v in os.environ.items() if not k.upper().startswith(("PAPERPLANE_","CASHFREE_","SMTP_","RESEND_","OPENAI_","OPENROUTER_","BLUESMINDS_","ANTHROPIC_","GEMINI_","DEEPSEEK_","GOOGLE_API_","AI_","ADMIN_")) and k not in {"TESTING","SESSION_SECRET_KEY"}}
    env.update({"PAPERPLANE_SKIP_DOTENV":"1","PAPERPLANE_ENV":"development","PAPERPLANE_DATA_DIR":str(data),"PAPERPLANE_PORT":str(port),"PAPERPLANE_ADMIN_KEY":secrets.token_urlsafe(48),"PAPERPLANE_ADMIN_CODE":secrets.token_urlsafe(32),"PAPERPLANE_SESSION_SECRET":secrets.token_urlsafe(48),"PAPERPLANE_SECURE_COOKIES":"false","PYTHONPATH":str(ROOT)})
    app=subprocess.Popen([sys.executable,"app.py"],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    evidence={"routes":[],"page_errors":[],"console_errors":[]}
    try:
        for _ in range(120):
            try:
                with socket.create_connection(("127.0.0.1",port),timeout=.2): break
            except OSError: time.sleep(.2)
        else: raise RuntimeError("local app did not start")
        with sync_playwright() as p:
            browser=p.chromium.launch(channel="chrome",headless=True)
            page=browser.new_page(viewport={"width":1366,"height":900})
            page.on("pageerror",lambda e:evidence["page_errors"].append(str(e)))
            page.on("console",lambda m:evidence["console_errors"].append(m.text) if m.type=="error" else None)
            for route in ("/summarize-pdf","/compare-pdf","/edit-pdf"):
                response=page.goto(f"http://127.0.0.1:{port}{route}",wait_until="domcontentloaded")
                assert response and response.status==200,(route,response.status if response else None)
                page.wait_for_function("!!document.querySelector('#dropzone') && state.operation")
                assert page.locator("#cloud-modal").is_hidden()
                page.evaluate("""(encoded) => {
                  const binary=atob(encoded), bytes=new Uint8Array(binary.length);
                  for(let i=0;i<binary.length;i++) bytes[i]=binary.charCodeAt(i);
                  const file=new File([bytes],'drop-test.pdf',{type:'application/pdf'});
                  const dt=new DataTransfer();dt.items.add(file);
                  document.querySelector('#dropzone').dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:dt}));
                }""",base64.b64encode(pdf.read_bytes()).decode("ascii"))
                page.wait_for_timeout(300)
                modal_visible=not page.locator("#cloud-modal").is_hidden()
                assert not modal_visible,{"route":route,"body":page.locator("body").inner_text()[:300]}
                evidence["routes"].append({"route":route,"cloud_modal_opened":modal_visible,"file_list":page.locator("#file-list").inner_text() if page.locator("#file-list").count() else "not shown"})
            assert not evidence["page_errors"] and not evidence["console_errors"],evidence
            browser.close()
        evidence["result"]="passed"
    finally:
        app.terminate()
        try: app.wait(timeout=5)
        except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
OUT.write_text(json.dumps(evidence,indent=2),encoding="utf-8")
print(json.dumps(evidence,indent=2))
