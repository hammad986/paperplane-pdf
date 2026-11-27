"""Ensure signature-looking ordinary page text never becomes a verified signature."""
import json, socket, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"reports"/"launch-audit-v24"
with TemporaryDirectory(prefix="paperplane-id117-") as tmp:
    temp=Path(tmp);source=temp/"unsigned.pdf"
    fake="Unsigned fixture /ByteRange [0 10 20 30] /Contents <3006020101> fake signature-looking text"
    with fitz.open() as doc:
        doc.new_page().insert_text((72,72),fake)
        doc.save(source)
    with socket.socket() as sock:sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
    sys.path.insert(0,str(ROOT/"reports"/"launch-audit-v14"))
    import browser_acceptance_v14 as helper
    app,base,_=helper.start_server(temp/"data")
    try:
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1",port),timeout=.2):break
            except OSError:time.sleep(.2)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel="chrome",headless=True);page=browser.new_page(viewport={"width":1366,"height":900});errors=[]
            page.on("pageerror",lambda e:errors.append(str(e)))
            page.goto(base+"/studio",wait_until="domcontentloaded")
            page.locator("#studio-file-input").set_input_files(str(source))
            page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent==='1' && document.querySelector('#studio-loading-overlay')?.hidden===true",timeout=20000)
            page.locator("#btn-more-tools-trigger").click();page.locator("#studio-sign-btn").click()
            page.wait_for_function("document.querySelector('#digital-sign-modal')?.hidden===false")
            page.locator("#sign-tab-verify").click()
            page.wait_for_function("document.querySelector('#verify-report-container')?.textContent.includes('No Digital Signatures Found')",timeout=15000)
            report=page.locator("#verify-report-container").inner_text()
            assert "TAMPERING DETECTED" not in report and "CRYPTOGRAPHICALLY VALID" not in report,report
            assert not errors,errors
            evidence={"fixture_contains_fake_byte_range_and_contents_text":True,"rendered_report":report,"reported_signature_count":0,"false_tampering_claim":False,"page_errors":errors,"result":"passed"}
            (OUT/"browser-id117-fake-signature-text.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
            print(json.dumps(evidence,indent=2));browser.close()
    finally:app.terminate();app.wait(timeout=5)
