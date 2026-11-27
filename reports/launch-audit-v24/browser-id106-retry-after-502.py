"""Inject one transient gateway failure into a real server-backed browser PDF job."""
import json, socket, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"reports"/"launch-audit-v24"
with TemporaryDirectory(prefix="paperplane-id106-") as tmp:
    temp=Path(tmp);source=temp/"retry-fixture.pdf"
    with fitz.open() as doc:
        doc.new_page().insert_text((72,72),"ID106 transient gateway retry marker RETRY-502-ONCE")
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
            browser=p.chromium.launch(channel="chrome",headless=True)
            context=browser.new_context(viewport={"width":1366,"height":900},accept_downloads=True)
            page=context.new_page();page_errors=[];console_errors=[];injected_gateway_console=[];attempts=[];failed=[False]
            page.on("pageerror",lambda e:page_errors.append(str(e)))
            page.on("console",lambda m:(injected_gateway_console if "status of 502" in m.text else console_errors).append(m.text) if m.type=="error" else None)
            def transient_once(route):
                req=route.request
                attempts.append({"method":req.method,"idempotency_key":req.headers.get("idempotency-key")})
                if req.method=="POST" and not failed[0]:
                    failed[0]=True
                    route.fulfill(status=502,content_type="text/html",body="<html><body>502 Bad Gateway</body></html>")
                else:route.continue_()
            page.route("**/api/jobs",transient_once)
            page.goto(base+"/protect-pdf",wait_until="domcontentloaded")
            page.locator("#file-input").set_input_files(str(source))
            page.wait_for_function("state.files.length===1")
            page.locator("#password").fill("Retry-Flow-Password!24")
            page.locator("#run-button").click()
            page.wait_for_function("document.querySelector('#result')?.hidden===false",timeout=120000)
            with page.expect_download(timeout=30000) as download_info:
                page.locator("#result-download-link").click()
            download=download_info.value;output=temp/"retried-protected.pdf";download.save_as(output)
            with fitz.open(output) as protected:
                encrypted=protected.is_encrypted
                unlocked=protected.authenticate("Retry-Flow-Password!24") if encrypted else 0
                text="\n".join(pg.get_text() for pg in protected) if unlocked else ""
                page_count=protected.page_count
            assert len(attempts)==2,attempts
            assert attempts[0]["idempotency_key"] and attempts[0]["idempotency_key"]==attempts[1]["idempotency_key"],attempts
            assert encrypted and unlocked and "RETRY-502-ONCE" in text,(encrypted,unlocked,text)
            assert not page_errors,page_errors
            assert not console_errors,console_errors
            evidence={"operation":"protect","first_attempt":"controlled 502 Bad Gateway","attempt_count":len(attempts),"same_idempotency_key_reused":attempts[0]["idempotency_key"]==attempts[1]["idempotency_key"],"download_bytes":output.stat().st_size,"pages":page_count,"encrypted":encrypted,"password_authenticated":bool(unlocked),"source_marker_after_unlock":"RETRY-502-ONCE" in text,"page_errors":page_errors,"unexpected_console_errors":console_errors,"expected_console_messages_from_injected_502":injected_gateway_console,"production_endpoints_contacted":False,"result":"passed"}
            (OUT/"browser-id106-retry-after-502.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
            print(json.dumps(evidence,indent=2));browser.close()
    finally:app.terminate();app.wait(timeout=5)
