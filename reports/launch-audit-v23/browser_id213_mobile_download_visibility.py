from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as harness

with TemporaryDirectory(prefix="paperplane-id213-mobile-") as temp_name:
    temp_dir = Path(temp_name)
    source, encrypted = temp_dir / "mobile-download-source.pdf", temp_dir / "mobile-download-locked.pdf"
    with fitz.open() as document:
        document.new_page().insert_text((72, 72), "Mobile result download visibility source.")
        document.save(source)
    with fitz.open(source) as document:
        document.save(encrypted, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="test-pass", owner_pw="owner-pass")

    rounds = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        for round_number in (1, 2):
            app, base, _ = harness.start_server(temp_dir / f"db-{round_number}")
            try:
                for _ in range(100):
                    try:
                        with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=0.2):
                            break
                    except OSError:
                        time.sleep(0.15)
                else:
                    raise RuntimeError("Local Paperplane server did not start")

                context = browser.new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                tools = [
                    ("protect", "/protect-pdf", source, "mobile-protect-pass", "protected"),
                    ("unlock", "/unlock-pdf", encrypted, "test-pass", "unlocked"),
                    ("sign", "/sign-pdf", source, "Ada Example", "signed"),
                ]
                results = []
                for operation, route, input_pdf, value, expected in tools:
                    response = page.goto(base + route, wait_until="domcontentloaded")
                    assert response.status == 200
                    page.locator("#file-input").set_input_files(str(input_pdf))
                    if operation == "protect":
                        page.locator("#password").fill(value)
                    elif operation == "unlock":
                        page.locator("#password").fill(value)
                    else:
                        page.locator("#signature").fill(value)
                    page.locator("#run-button").click()
                    page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=25000)
                    page.wait_for_function("""() => {
                      const link=document.querySelector('#result-download-link');
                      const rect=link.getBoundingClientRect();
                      return rect.y>=0&&rect.bottom<=innerHeight;
                    }""", timeout=10000)
                    geometry = page.locator("#result-download-link").evaluate("""element => {
                      const rect=element.getBoundingClientRect();
                      return {x:rect.x,y:rect.y,width:rect.width,height:rect.height,
                        viewportHeight:innerHeight,withinViewport:rect.y>=0&&rect.bottom<=innerHeight};
                    }""")
                    assert geometry["withinViewport"], {"operation": operation, "geometry": geometry}
                    with page.expect_download(timeout=15000) as download_event:
                        page.locator("#result-download-link").click()
                    output = temp_dir / f"{operation}-round{round_number}.pdf"
                    download_event.value.save_as(output)
                    with fitz.open(output) as result:
                        assert len(result) == 1
                        if operation == "protect":
                            assert result.is_encrypted
                        elif operation == "unlock":
                            assert not result.is_encrypted
                            assert "Mobile result download visibility source." in result[0].get_text()
                        else:
                            assert "Ada Example" in result[0].get_text()
                    page.wait_for_function("document.querySelector('.toast-notice')?.innerText.includes('Download complete')",timeout=5000)
                    toast_geometry=page.evaluate("""()=>{const t=document.querySelector('.toast-notice'),a=document.querySelector('#result .result-actions');if(!t||!a)return null;const r=e=>{const x=e.getBoundingClientRect();return {left:x.left,right:x.right,top:x.top,bottom:x.bottom}};const x=r(t),y=r(a);return {toast:x,actions:y,overlap:x.left<y.right&&x.right>y.left&&x.top<y.bottom&&x.bottom>y.top,viewport:{width:innerWidth,height:innerHeight}}}""")
                    assert toast_geometry and not toast_geometry['overlap'],{'operation':operation,'geometry':toast_geometry}
                    results.append({"operation": operation, "status": response.status,
                                    "download_filename": download_event.value.suggested_filename,
                                    "download_control": geometry, "output_bytes": output.stat().st_size,
                                    "content_checked": True,"download_toast_geometry":toast_geometry})
                assert not errors, errors
                page.screenshot(path=str(OUT / f"id213-mobile-download-round{round_number}.png"))
                rounds.append({"round": round_number, "viewport": [390, 844], "results": results,
                               "page_errors": errors})
                context.close()
            finally:
                app.terminate()
                app.wait(timeout=5)
        browser.close()
    evidence = {"rounds": rounds}
    (OUT / "browser-id213-mobile-download-visibility.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
