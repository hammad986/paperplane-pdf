"""Probe Studio's 69-page count, lower-page scroll reachability, and idle tool stability."""
from __future__ import annotations

import base64
import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/launch-audit-v24/browser-id174-studio-69page-layout.json"
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main():
    with TemporaryDirectory(prefix="paperplane-id174-") as temp_name:
        temp = Path(temp_name)
        source = temp / "id174-69-pages.pdf"
        with fitz.open() as document:
            for number in range(1, 70):
                page = document.new_page(width=612, height=792)
                page.insert_text((72, 100), f"ID174 page marker {number}")
            document.save(source)
        app, base, _identities = helper.start_server(temp / "data")
        evidence = {"page_errors": [], "console_errors": []}
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Local Paperplane server exited before startup")
                    time.sleep(0.15)
            else:
                raise RuntimeError("Local Paperplane server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1920, "height": 999})
                page.set_default_timeout(30000)
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error).splitlines()[0][:200]))
                page.on("console", lambda message: evidence["console_errors"].append(message.text[:200]) if message.type == "error" else None)
                page.goto(base + "/rotate-pdf", wait_until="domcontentloaded")
                source_b64 = base64.b64encode(source.read_bytes()).decode("ascii")
                page.evaluate("""b64 => {
                  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
                  const blob = new Blob([bytes], {type: 'application/pdf'});
                  window.showDownloadResult({output_name: 'id174-fixture.pdf', output_size: blob.size, page_count: 69}, URL.createObjectURL(blob), {blob});
                }""", source_b64)
                page.locator("#result-view-studio-btn").click()
                page.wait_for_function("state.studio.pdfDoc && state.studio.totalCount === 69")
                page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered === 'true'")
                evidence["initial"] = page.evaluate("""() => ({
                  studio_page_count: document.querySelector('#studio-page-count')?.textContent,
                  total_pages_indicator: document.querySelector('#page-total-indicator')?.textContent,
                  page_stack_slots: document.querySelectorAll('#studio-page-stack .studio-page-sheet').length,
                  first_loading_placeholder: (() => {const el=document.querySelector('#studio-page-stack .studio-page-sheet[data-page="1"] .studio-page-loading');return el ? {text:el.textContent, hidden:el.hidden, visible:!el.hidden && getComputedStyle(el).display!=='none'} : null;})(),
                  first_canvas_rendered: document.querySelector('#pdf-canvas')?.dataset.rendered,
                  page_status: document.querySelector('#studio-status')?.textContent || null,
                  active_tool: window.PaperplaneEditor?._activeTool || null,
                  selected_tool_buttons: [...document.querySelectorAll('.studio-tool-btn.active, .studio-mode-btn.active')].map(x => x.id || x.dataset.tool || x.textContent.trim())
                })""")
                page.wait_for_timeout(1200)
                evidence["after_idle"] = page.evaluate("""() => ({
                  active_tool: window.PaperplaneEditor?._activeTool || null,
                  selected_tool_buttons: [...document.querySelectorAll('.studio-tool-btn.active, .studio-mode-btn.active')].map(x => x.id || x.dataset.tool || x.textContent.trim())
                })""")
                page.evaluate("""() => { const area=document.querySelector('#studio-canvas-area'); area.scrollTop=area.scrollHeight; area.dispatchEvent(new Event('scroll', {bubbles:true})); }""")
                page.wait_for_function("document.querySelector('#studio-page-stack .studio-page-sheet[data-page=\"69\"]')?.getBoundingClientRect().top < innerHeight")
                page.wait_for_timeout(500)
                evidence["lower_section"] = page.evaluate("""() => {
                  const area=document.querySelector('#studio-canvas-area');
                  const slot=document.querySelector('#studio-page-stack .studio-page-sheet[data-page="69"]');
                  return {area_scroll_top:area.scrollTop, area_scroll_height:area.scrollHeight, area_client_height:area.clientHeight,
                    page69_top:slot.getBoundingClientRect().top, page69_canvas_rendered:slot.querySelector('canvas')?.dataset.rendered || null,
                    page_stack_page_count:document.querySelectorAll('#studio-page-stack .studio-page-sheet').length};
                }""")
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=5)
        initial = evidence.get("initial", {})
        idle = evidence.get("after_idle", {})
        lower = evidence.get("lower_section", {})
        evidence["overall"] = "passed" if (
            initial.get("studio_page_count") == "69"
            and initial.get("total_pages_indicator") == "69"
            and initial.get("page_stack_slots") == 69
            and initial.get("first_canvas_rendered") == "true"
            and initial.get("first_loading_placeholder", {}).get("visible") is False
            and initial.get("active_tool") == idle.get("active_tool")
            and initial.get("selected_tool_buttons") == idle.get("selected_tool_buttons")
            and lower.get("area_scroll_top", 0) > 0
            and lower.get("page_stack_page_count") == 69
            and not evidence["page_errors"] and not evidence["console_errors"]
        ) else "failed"
        OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
        if evidence["overall"] != "passed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
