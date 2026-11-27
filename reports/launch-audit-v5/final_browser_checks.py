from __future__ import annotations

import json
import time
from pathlib import Path

import fitz
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "launch-audit-v5"
BASE = "http://127.0.0.1:8501"
PDF = ROOT / "runtime_data_codex_audit" / "notes_69pages_audit.pdf"
DRIVE_URL = "https://drive.google.com/file/d/1lAdtz5YIxTAOzaNDTbiOvRyon_AAj2Mq/view?usp=drive_link"


def wait_for_text(page, selector: str, value: str, timeout: float = 90) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if page.locator(selector).inner_text().strip() == value:
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


def wait_canvas(page, page_number: int, timeout: float = 15) -> bool:
    deadline = time.monotonic() + timeout
    selector = f"#studio-page-stack .studio-page-sheet[data-page='{page_number}'] canvas[data-rendered='true']"
    while time.monotonic() < deadline:
        if page.locator(selector).count():
            return True
        time.sleep(0.1)
    return False


def wait_eval(page, expression: str, timeout: float = 30) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if page.evaluate(f"() => Boolean({expression})"):
            return True
        time.sleep(0.05)
    return False


def canvas_pixels(page, page_number: int) -> dict[str, int | bool]:
    return page.evaluate(
        """(pageNumber) => {
          const canvas=document.querySelector(`#studio-page-stack .studio-page-sheet[data-page='${pageNumber}'] canvas`);
          if (!canvas || canvas.width<1 || canvas.height<1) return {rendered:false,width:canvas?.width||0,height:canvas?.height||0,nonWhiteSamples:0};
          const ctx=canvas.getContext('2d');
          const image=ctx.getImageData(0,0,canvas.width,canvas.height).data;
          let nonWhiteSamples=0;
          const step=Math.max(4,Math.floor(image.length/50000/4)*4);
          for(let i=0;i<image.length;i+=step){if(image[i]<242||image[i+1]<242||image[i+2]<242)nonWhiteSamples++;}
          return {rendered:canvas.dataset.rendered==='true',width:canvas.width,height:canvas.height,nonWhiteSamples};
        }""",
        page_number,
    )


def open_fixture(page) -> None:
    page.goto(f"{BASE}/studio", wait_until="domcontentloaded")
    page.locator("#studio-file-input").set_input_files(str(PDF))
    if not wait_for_text(page, "#studio-page-count", "69"):
        raise RuntimeError(f"69-page fixture did not load: {page.locator('#studio-page-count').inner_text()!r}")
    if not wait_canvas(page, 1):
        raise RuntimeError("Studio did not render page 1")


def run_extract(browser, width: int, pages: list[int]) -> dict[str, object]:
    context = browser.new_context(
        accept_downloads=True,
        viewport={"width": width, "height": 900 if width > 900 else 812},
        is_mobile=width <= 900,
        has_touch=width <= 900,
    )
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    open_fixture(page)
    page.locator("#btn-mode-organize").click()
    for number in pages:
        page.locator(f"#organizer-grid .organizer-thumb-card[data-page='{number}'] .thumb-checkbox").check()
    started = time.monotonic()
    filename = ""
    saved_path = OUT / f"extract-{width}-pages-{'-'.join(map(str, pages))}.pdf"
    with page.expect_download(timeout=45000) as download_event:
        page.locator("#batch-extract-btn").click()
    download = download_event.value
    download.save_as(str(saved_path))
    document = fitz.open(saved_path)
    text = "\n".join(pg.get_text() for pg in document)
    result = {
        "viewport": width,
        "selected_pages": pages,
        "download": True,
        "filename": download.suggested_filename,
        "bytes": saved_path.stat().st_size,
        "opened_by_pymupdf": True,
        "page_count": document.page_count,
        "text_chars": len(text),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "errors": errors,
        "output_path": str(saved_path),
    }
    document.close()
    page.screenshot(path=str(OUT / f"extract-{width}-pages-{'-'.join(map(str, pages))}.png"), full_page=False)
    context.close()
    return result


def run_render_and_reload(browser) -> dict[str, object]:
    context = browser.new_context(accept_downloads=True, viewport={"width": 375, "height": 812}, is_mobile=True, has_touch=True)
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

    page.goto(f"{BASE}/studio", wait_until="domcontentloaded")
    started = time.monotonic()
    page.locator("#studio-file-input").set_input_files(str(PDF))
    render_samples = []
    for second in (0, 5, 15, 30):
        wait_until = started + second
        while time.monotonic() < wait_until:
            time.sleep(0.05)
        render_samples.append({"target_seconds": second, "elapsed_seconds": round(time.monotonic() - started, 3), "page_count": page.locator("#studio-page-count").inner_text().strip(), "canvas": canvas_pixels(page, 1)})
    if not wait_for_text(page, "#studio-page-count", "69", timeout=2):
        raise RuntimeError("Studio did not load the 69-page file within the render timing run")
    render_samples[-1]["page_count"] = page.locator("#studio-page-count").inner_text().strip()
    page.screenshot(path=str(OUT / "studio-page1-375-after.png"), full_page=False)

    jumps = []
    for number in (69, 1, 35):
        jump_started = time.monotonic()
        page.locator("#page-jump-input").fill(str(number))
        page.locator("#page-jump-input").press("Enter")
        # Capture at the first Playwright round-trip after Enter, before
        # waiting for PDF.js to paint the destination page.
        input_after_enter = page.locator("#page-jump-input").input_value()
        slot_after_enter = page.locator("#studio-page-stack .studio-page-sheet.is-current").get_attribute("data-page")
        rendered = wait_canvas(page, number, timeout=15)
        jumps.append({
            "target": number,
            "input_after_enter_before_waiting_for_render": input_after_enter,
            "slot_after_enter_before_waiting_for_render": slot_after_enter,
            "counter_after_render": page.locator("#page-jump-input").input_value(),
            "current_slot_after_render": page.locator("#studio-page-stack .studio-page-sheet.is-current").get_attribute("data-page"),
            "rendered": rendered,
            "canvas": canvas_pixels(page, number),
            "elapsed_seconds": round(time.monotonic() - jump_started, 3),
        })

    # Protect a non-current page after selecting its thumbnail, then verify the
    # viewer page and deletion both survive two full reloads.
    page.locator("#page-jump-input").fill("5")
    page.locator("#page-jump-input").press("Enter")
    wait_canvas(page, 5)
    page.wait_for_timeout(1000)
    pre_delete_page = page.locator("#page-jump-input").input_value()
    page.locator("#btn-mode-organize").click()
    page.locator("#studio-thumbnails-container").evaluate("panel => panel.scrollTop = panel.scrollHeight")
    page.wait_for_timeout(300)
    page.locator("#organizer-grid .organizer-thumb-card[data-page='69'] .thumb-checkbox-label").click()
    page.locator("#batch-delete-btn").click()
    page.locator("dialog.app-confirm-dialog[open] .app-confirm-accept").click()
    if not wait_for_text(page, "#studio-page-count", "68", timeout=60):
        raise RuntimeError("Delete page 69 did not complete")
    page.wait_for_timeout(1000)
    after_delete = {"page_count": page.locator("#studio-page-count").inner_text().strip(), "page": page.locator("#page-jump-input").input_value(), "toast": page.locator(".toast-notice").inner_text() if page.locator(".toast-notice").count() else None}
    page.screenshot(path=str(OUT / "studio-delete-375-after.png"), full_page=False)

    reloads = []
    for iteration in (1, 2):
        page.reload(wait_until="domcontentloaded")
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline and page.locator("#studio-page-count").inner_text().strip() != "68":
            time.sleep(0.1)
        page.wait_for_timeout(400)
        reloads.append({
            "iteration": iteration,
            "url": page.url,
            "page_count": page.locator("#studio-page-count").inner_text().strip(),
            "page": page.locator("#page-jump-input").input_value(),
            "toast": page.locator(".toast-notice").inner_text() if page.locator(".toast-notice").count() else None,
        })

    # Explicit tap-test with the mobile drawer open. The editor toolbar sits
    # above the drawer so Export remains reachable and works on a real click.
    page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
    page.locator("#mobile-menu-btn").click()
    page.wait_for_timeout(300)
    layout = page.evaluate("""() => ({
      drawerOpen:document.querySelector('#sidebar')?.classList.contains('mobile-open'),
      sidebarZ:getComputedStyle(document.querySelector('#sidebar')).zIndex,
      toolbarZ:getComputedStyle(document.querySelector('.studio-main-toolbar')||document.querySelector('.studio-toolbar')||document.querySelector('#studio-toolbar')).zIndex,
      saveButton: (()=>{const r=document.querySelector('#save-studio-btn').getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height}})(),
      viewport:innerWidth
    })""")
    export = {"tapped": False}
    try:
        with page.expect_download(timeout=45000) as export_event:
            page.locator("#save-studio-btn").click(timeout=10000)
        export_download = export_event.value
        export_path = OUT / "studio-export-375-after-sidebar-open.pdf"
        export_download.save_as(str(export_path))
        exported = fitz.open(export_path)
        export.update({"tapped": True, "filename": export_download.suggested_filename, "bytes": export_path.stat().st_size, "page_count": exported.page_count})
        exported.close()
    except PlaywrightTimeout as error:
        export["error"] = str(error).splitlines()[0]

    evidence = {
        "viewport": 375,
        "render_samples": render_samples,
        "page_jumps": jumps,
        "deletion_before_reload": {"page_before_delete": pre_delete_page, **after_delete},
        "reloads": reloads,
        "sidebar_open_layout": layout,
        "sidebar_open_export": export,
        "console_or_page_errors": errors,
        "screenshots": [str(OUT / "studio-page1-375-after.png"), str(OUT / "studio-delete-375-after.png")],
    }
    page.screenshot(path=str(OUT / "studio-sidebar-open-375-after.png"), full_page=False)
    context.close()
    return evidence


def run_cloud_import(browser) -> dict[str, object]:
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    errors: list[str] = []
    api_responses: list[dict[str, object]] = []
    csp_violations: list[dict[str, str]] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.on("response", lambda response: api_responses.append({"status": response.status, "url": response.url}) if "/api/cloud/sync" in response.url else None)
    page.add_init_script("""(() => {
      window.__cspViolations = [];
      window.addEventListener('securitypolicyviolation', event => window.__cspViolations.push({
        directive: event.violatedDirective, blockedURI: event.blockedURI, sourceFile: event.sourceFile
      }));
      const nativeFetch = window.fetch.bind(window);
      window.__operationsBlocked = false;
      window.fetch = (resource, init) => {
        if (String(resource).includes('/api/operations')) {
          window.__operationsBlocked = true;
          return new Promise((resolve, reject) => {
            window.__releaseOperationsFetch = () => nativeFetch(resource, init).then(resolve, reject);
          });
        }
        return nativeFetch(resource, init);
      };
    })();""")
    page.goto(f"{BASE}/studio", wait_until="domcontentloaded")
    if not wait_eval(page, "window.__operationsBlocked === true", timeout=30):
        raise RuntimeError("Cloud startup-race harness did not intercept /api/operations")
    page.locator("#topbar-cloud-btn").click()
    page.locator("#cloud-modal").wait_for(state="visible", timeout=3000)
    page.locator("#cloud-url").fill(DRIVE_URL)
    before_route_resolution = {
        "modal_open": not page.locator("#cloud-modal").is_hidden(),
        "retained_url": page.locator("#cloud-url").input_value(),
    }
    page.evaluate("window.__releaseOperationsFetch()")
    if not wait_eval(page, "!document.querySelector('#view-pdf-studio')?.hidden", timeout=30):
        raise RuntimeError("Studio did not finish initial route setup")
    page.wait_for_timeout(400)
    after_route_resolution = {
        "modal_open": not page.locator("#cloud-modal").is_hidden(),
        "retained_url": page.locator("#cloud-url").input_value(),
    }
    started = time.monotonic()
    click_error = None
    try:
        page.locator("#cloud-submit-btn").click(timeout=5000)
        if not wait_eval(page, "document.querySelector('#cloud-modal').hidden || (!document.querySelector('#cloud-error').hidden && document.querySelector('#cloud-error').textContent.trim())", timeout=120):
            click_error = "Cloud import did not complete within 120 seconds"
    except PlaywrightTimeout as error:
        click_error = str(error).splitlines()[0]
    csp_violations = page.evaluate("() => window.__cspViolations || []")
    error_text = page.locator("#cloud-error").inner_text().strip() if not page.locator("#cloud-error").is_hidden() else None
    result = {
        "source": "owner-provided Google Drive share link",
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "before_route_resolution": before_route_resolution,
        "after_route_resolution": after_route_resolution,
        "modal_open": not page.locator("#cloud-modal").is_hidden(),
        "error": error_text,
        "page_count": page.locator("#studio-page-count").inner_text().strip(),
        "toast": page.locator(".toast-notice").inner_text() if page.locator(".toast-notice").count() else None,
        "loaded_filename": page.locator("#studio-file-name").inner_text().strip() if page.locator("#studio-file-name").count() else None,
        "api_responses": api_responses,
        "click_error": click_error,
        "csp_violations": csp_violations,
        "errors": errors,
    }
    page.screenshot(path=str(OUT / "cloud-import-drive-1280-after.png"), full_page=False)
    context.close()
    return result


def main() -> None:
    results: dict[str, object] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        results["extract"] = [run_extract(browser, width, pages) for width in (1366, 375) for pages in ([1], [1, 2])]
        (OUT / "final-browser-checks.partial.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        results["studio_render_and_reload"] = run_render_and_reload(browser)
        (OUT / "final-browser-checks.partial.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            results["cloud_import"] = run_cloud_import(browser)
        except Exception as error:
            results["cloud_import"] = {"harness_error": str(error)}
        browser.close()
    (OUT / "final-browser-checks.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "extract": results["extract"],
        "render_samples": results["studio_render_and_reload"]["render_samples"],
        "page_jumps": results["studio_render_and_reload"]["page_jumps"],
        "reloads": results["studio_render_and_reload"]["reloads"],
        "sidebar_open_export": results["studio_render_and_reload"]["sidebar_open_export"],
        "cloud_import": results["cloud_import"],
        "report": str(OUT / "final-browser-checks.json"),
    }, indent=2))


if __name__ == "__main__":
    main()
