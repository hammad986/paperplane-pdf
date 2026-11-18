"""Check SEO heading synchronization during sequential and raced tool changes."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import socket
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


with TemporaryDirectory(prefix="paperplane-id110-seo-matrix-") as temp:
    app, base, _ = helper.start_server(Path(temp) / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            if app.poll() is not None:
                raise RuntimeError(f"app exited with {app.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.15)

        rounds = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for round_number in (1, 2):
                context = browser.new_context(viewport={"width": 1366, "height": 900})
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                response = page.goto(base + "/merge-pdf", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.locator(".seo-content").wait_for(state="visible")
                operations = page.evaluate("Object.keys(state.operations).filter(key => TOOL_SLUGS[key])")
                assert len(operations) >= 41, len(operations)
                checked = []
                for operation in operations:
                    expected = page.evaluate("async operation => {const r=await fetch('/api/seo/'+encodeURIComponent(operation));if(!r.ok)throw Error('SEO endpoint '+r.status);return r.json()}", operation)
                    page.evaluate("operation => selectOperation(operation, false)", operation)
                    page.wait_for_function("operation => {const s=document.querySelector('.seo-content');return s?.dataset.operation===operation && !s.hasAttribute('aria-busy')}", arg=operation, timeout=10000)
                    actual = page.evaluate("() => ({operation:document.querySelector('.seo-content')?.dataset.operation,heading:document.querySelector('#seo-page-heading')?.textContent,toolHeading:document.querySelector('#tool-title')?.textContent,faqCount:document.querySelectorAll('.seo-faq-item').length})")
                    assert actual["operation"] == operation and actual["heading"] == expected["heading"], {"operation": operation, "expected": expected["heading"], "actual": actual}
                    assert actual["toolHeading"] == page.evaluate("operation => state.operations[operation]?.label", operation), actual
                    checked.append({"operation": operation, "heading": actual["heading"], "faq_count": actual["faqCount"]})

                # Stress the stale-response guard by starting several SEO loads before earlier ones settle.
                sequence = operations[:12]
                page.evaluate("sequence => sequence.forEach(operation => selectOperation(operation, false))", sequence)
                final_operation = sequence[-1]
                page.wait_for_function("operation => document.querySelector('.seo-content')?.dataset.operation===operation && !document.querySelector('.seo-content')?.hasAttribute('aria-busy')", arg=final_operation, timeout=10000)
                race = page.evaluate("() => ({selected:state.operation,seoOperation:document.querySelector('.seo-content')?.dataset.operation,heading:document.querySelector('#seo-page-heading')?.textContent,toolHeading:document.querySelector('#tool-title')?.textContent})")
                assert race["selected"] == final_operation and race["seoOperation"] == final_operation, race
                expected_final = page.evaluate("operation => state.operations[operation].label", final_operation)
                expected_context = page.evaluate("async operation => (await fetch('/api/seo/'+encodeURIComponent(operation)).then(r=>r.json())).heading", final_operation)
                assert race["toolHeading"] == expected_final and race["heading"] == expected_context, race
                assert not errors, errors
                page.screenshot(path=str(OUT / f"id110-seo-transition-round{round_number}.png"), full_page=True)
                rounds.append({"round": round_number, "operation_count": len(checked), "sequential_checks": checked, "rapid_change_sequence": sequence, "rapid_change_final": race, "page_errors": errors})
                context.close()
            browser.close()
        result = {"rounds": rounds}
        (OUT / "browser-id110-seo-transition-matrix.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({"rounds": [{"round": r["round"], "operation_count": r["operation_count"], "rapid_change_final": r["rapid_change_final"], "page_errors": r["page_errors"]} for r in rounds]}, indent=2))
    finally:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(app.pid), "/T", "/F"], capture_output=True, text=True)
        if app.poll() is None:
            app.terminate()
        app.wait(timeout=5)
