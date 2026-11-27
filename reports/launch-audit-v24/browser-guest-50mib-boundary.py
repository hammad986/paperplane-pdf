"""Exercise the guest 50 MiB file-selection boundary in real local Chrome."""
import json, socket, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
with TemporaryDirectory(prefix="paperplane-guest-50mib-") as td:
    temp=Path(td); base_pdf=temp/"tiny.pdf"
    with fitz.open() as d: d.new_page(); d.save(base_pdf)
    pdf_bytes=base_pdf.read_bytes(); exact=temp/"exact-50MiB.pdf"; over=temp/"over-50MiB.pdf"
    max_bytes=50*1024*1024
    exact.write_bytes(pdf_bytes+b" "*(max_bytes-len(pdf_bytes)))
    over.write_bytes(pdf_bytes+b" "*(max_bytes+1-len(pdf_bytes)))
    sys.path.insert(0,str(ROOT/"reports"/"launch-audit-v14")); import browser_acceptance_v14 as helper
    app,base,_=helper.start_server(temp/"data")
    try:
        port=int(base.rsplit(":",1)[1])
        for _ in range(120):
            try:
                with socket.create_connection(("127.0.0.1",port),timeout=.2): break
            except OSError: time.sleep(.2)
        else: raise RuntimeError("server did not start")
        with sync_playwright() as p:
            browser=p.chromium.launch(channel="chrome",headless=True); page=browser.new_page(viewport={"width":390,"height":844},accept_downloads=True)
            page.add_init_script("localStorage.setItem('paperplane-pdf-processing-mode','server')")
            page_errors=[]; console_errors=[]
            page.on("pageerror",lambda e:page_errors.append(str(e)))
            page.on("console",lambda m:console_errors.append(m.text) if m.type=="error" else None)
            response=page.goto(base+"/protect-pdf",wait_until="domcontentloaded")
            page.locator("#file-input").set_input_files(str(exact))
            page.wait_for_function("state.files?.length===1",timeout=20000)
            exact_state=page.evaluate("({count:state.files.length,size:state.files[0].size,copy:document.querySelector('#file-list')?.innerText||''})")
            assert exact_state["size"]==max_bytes and "50.00 MB" in exact_state["copy"],exact_state
            page.locator("#password").fill("Guest-50MiB-Boundary!24")
            page.locator("#run-button").click()
            page.wait_for_function("document.querySelector('#result')?.hidden===false",timeout=120000)
            with page.expect_download(timeout=30000) as info: page.locator("#result-download-link").click()
            download=info.value; output=temp/download.suggested_filename; download.save_as(output)
            with fitz.open(output) as protected:
                output_ok=protected.is_encrypted and bool(protected.authenticate("Guest-50MiB-Boundary!24")) and protected.page_count==1
            assert output_ok,output_ok
            page.reload(wait_until="domcontentloaded")
            page.locator("#file-input").set_input_files(str(over))
            page.wait_for_timeout(500)
            over_state=page.evaluate("({count:state.files?.length||0,copy:document.querySelector('#file-list')?.innerText||'',toast:document.querySelector('.toast-notice')?.innerText||''})")
            assert over_state["count"]==0,over_state
            assert "50 MB" in (over_state["copy"]+over_state["toast"]),over_state
            assert not page_errors,page_errors
            assert not console_errors,console_errors
            evidence={"route_status":response.status if response else None,"guest_no_session":True,"exact_limit_bytes":max_bytes,"exact_limit_mib":50,"exact_limit_accepted":True,"exact_limit_ui":exact_state["copy"],"exact_limit_server_job":"chunked Protect completed; encrypted output opened with supplied password","output_name":download.suggested_filename,"output_bytes":output.stat().st_size,"output_page_count":1,"one_byte_over_rejected":True,"over_limit_ui":over_state,"page_errors":page_errors,"console_errors":console_errors,"result":"passed"}
            (OUT/"browser-guest-50mib-boundary.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
            print(json.dumps(evidence,indent=2));browser.close()
    finally: app.terminate(); app.wait(timeout=5)
