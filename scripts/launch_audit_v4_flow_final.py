from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8501"
REPORT_DIR = ROOT / "reports" / "launch-audit-v4"
PDF_69 = ROOT / "runtime_data_codex_audit" / "notes_69pages_audit.pdf"
WIDTHS = [333, 360, 375, 390, 414, 768, 1024, 1280, 1366, 1920]


def wait_for_count(page, selector: str, expected: int, timeout: float = 90) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if page.locator(selector).count() == expected:
            return True
        page.wait_for_timeout(100)
    return page.locator(selector).count() == expected


def wait_for_text(page, selector: str, expected: str, timeout: float = 60) -> bool:
    end = time.monotonic() + timeout
    locator = page.locator(selector)
    while time.monotonic() < end:
        if locator.count() and locator.first.inner_text().strip() == expected:
            return True
        page.wait_for_timeout(100)
    return locator.count() > 0 and locator.first.inner_text().strip() == expected


def add_result(results: list[dict[str, object]], name: str, passed: bool, **details: object) -> None:
    results.append({"check": name, "status": "PASS" if passed else "FAIL", **details})


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    general_ai: dict[str, object] = {"requestSeen": False, "answer": "", "httpStatuses": []}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True,
        )

        # Mobile navigation: drawer remains above the dimmer and the backdrop closes it.
        page = browser.new_page(viewport={"width": 375, "height": 812}, color_scheme="light")
        page.on("pageerror", lambda error: errors.append({"url": page.url, "message": str(error)}))
        page.goto(BASE_URL + "/", wait_until="domcontentloaded")
        page.locator("#mobile-menu-btn").click()
        drawer_open = page.locator("#sidebar").evaluate("el => el.classList.contains('mobile-open')")
        backdrop_visible = page.locator("#mobile-backdrop").is_visible()
        sidebar_z = page.locator("#sidebar").evaluate("el => Number(getComputedStyle(el).zIndex) || 0")
        backdrop_z = page.locator("#mobile-backdrop").evaluate("el => Number(getComputedStyle(el).zIndex) || 0")
        add_result(results, "mobile sidebar drawer opens above backdrop", drawer_open and backdrop_visible and sidebar_z > backdrop_z,
                   drawerOpen=drawer_open, backdropVisible=backdrop_visible, sidebarZ=sidebar_z, backdropZ=backdrop_z)
        page.mouse.click(350, 400)
        drawer_closed = not page.locator("#sidebar").evaluate("el => el.classList.contains('mobile-open')")
        add_result(results, "mobile sidebar backdrop closes drawer", drawer_closed, drawerClosed=drawer_closed)
        page.close()

        # AI no-document gate, saved guidance rendering, PDF persistence and clear.
        ai = browser.new_page(viewport={"width": 375, "height": 812}, color_scheme="light")
        ai.on("pageerror", lambda error: errors.append({"url": ai.url, "message": str(error)}))
        ai.on("request", lambda request: general_ai.__setitem__("requestSeen", True) if "/api/ai/chat/stream" in request.url else None)
        ai.on("response", lambda response: general_ai["httpStatuses"].append(response.status) if "/api/ai/chat/stream" in response.url else None)
        ai.goto(BASE_URL + "/", wait_until="domcontentloaded")
        ai.evaluate("window.switchWorkspaceView('ai', null, false)")
        ai.locator("#chat-input").fill("ok find me some important keyword from olden pdf uploaded")
        ai.locator("#chat-send-btn").click()
        ai.locator("#chat-messages .ai-document-required").wait_for(state="visible", timeout=10000)
        request_not_sent = not general_ai["requestSeen"]
        add_result(results, "document question without PDF gets upload guidance without API request", request_not_sent,
                   requestSeen=general_ai["requestSeen"], guidance=ai.locator("#chat-messages .ai-document-required").inner_text())
        ai.screenshot(path=str(REPORT_DIR / "post-ai-document-gate-375.png"), full_page=True)
        ai.reload(wait_until="domcontentloaded")
        ai.evaluate("window.switchWorkspaceView('ai', null, false)")
        restored_gate = ai.locator("#chat-messages .ai-document-required").is_visible()
        restored_question = "olden pdf uploaded" in ai.locator("#chat-messages").inner_text().lower()
        add_result(results, "AI document guidance and chat restore with its styled state", restored_gate and restored_question,
                   guidanceClassRestored=restored_gate, questionRestored=restored_question)

        # A general question is allowed through; local configuration is reported exactly.
        ai.locator("#chat-input").fill("Can you write a poem?")
        ai.locator("#chat-send-btn").click()
        ai.wait_for_timeout(9000)
        general_ai["answer"] = ai.locator("#chat-messages").inner_text()[-1200:]
        general_ai_pass = bool(general_ai["requestSeen"])
        ai_provider_configured = "AI provider is not configured" not in general_ai["answer"]
        add_result(results, "general AI question reaches the chat API", general_ai_pass,
                   requestSeen=general_ai["requestSeen"], httpStatuses=general_ai["httpStatuses"])
        results.append({
            "check": "general AI provider returns a usable answer",
            "status": "PASS" if ai_provider_configured else "BLOCKED",
            "providerConfigured": ai_provider_configured,
            "reason": "AI provider is not configured in this local environment" if not ai_provider_configured else "Provider returned a response",
            "answerTail": general_ai["answer"],
        })

        # Return to an isolated clean context for persistence so the failed general
        # response above does not influence the reload test.
        ai.close()
        ai = browser.new_page(viewport={"width": 375, "height": 812}, color_scheme="light")
        ai.on("pageerror", lambda error: errors.append({"url": ai.url, "message": str(error)}))
        ai.goto(BASE_URL + "/", wait_until="domcontentloaded")
        ai.evaluate("window.switchWorkspaceView('ai', null, false)")
        ai.locator("#ai-file-input").set_input_files(str(PDF_69))
        ai.locator("#ai-active-doc-bar").wait_for(state="visible", timeout=10000)
        ai.wait_for_timeout(350)
        upload_name = ai.locator("#ai-doc-name").inner_text()
        loaded_placeholder = ai.locator("#chat-input").get_attribute("placeholder")
        add_result(results, "AI PDF composer uses a short phone placeholder", loaded_placeholder == "Ask about this PDF…",
                   placeholder=loaded_placeholder)
        ai.screenshot(path=str(REPORT_DIR / "post-ai-loaded-375-final.png"), full_page=True)
        ai.reload(wait_until="domcontentloaded")
        ai.evaluate("window.switchWorkspaceView('ai', null, false)")
        ai.locator("#ai-active-doc-bar").wait_for(state="visible", timeout=15000)
        upload_restored = ai.locator("#ai-doc-name").inner_text() == upload_name
        add_result(results, "AI source PDF restores after reload", upload_restored, filename=upload_name)
        ai.locator("#ai-clear-work-btn").click()
        ai.locator("#ai-empty-state").wait_for(state="visible", timeout=10000)
        ai.reload(wait_until="domcontentloaded")
        ai.evaluate("window.switchWorkspaceView('ai', null, false)")
        ai.wait_for_timeout(300)
        ai_cleared = ai.locator("#ai-active-doc-bar").is_hidden() and ai.locator("#ai-empty-state").is_visible()
        add_result(results, "AI clear saved work removes PDF and restores empty state after reload", ai_cleared,
                   activeDocumentVisible=ai.locator("#ai-active-doc-bar").is_visible(), emptyStateVisible=ai.locator("#ai-empty-state").is_visible())
        empty_placeholder = ai.locator("#chat-input").get_attribute("placeholder")
        add_result(results, "Empty AI composer keeps a short phone placeholder", empty_placeholder == "Ask anything…",
                   placeholder=empty_placeholder)

        # AI mobile sizing + CSS zoom simulation across widths and both themes.
        ai_layout: list[dict[str, object]] = []
        for theme in ("light", "dark"):
            ai.evaluate("theme => window.applyTheme(theme)", theme)
            for width in WIDTHS:
                ai.set_viewport_size({"width": width, "height": 812 if width < 900 else 900})
                ai.wait_for_timeout(80)
                metric = ai.evaluate("""() => ({
                  width: innerWidth,
                  bodyWidth: document.body.scrollWidth,
                  documentWidth: document.documentElement.scrollWidth,
                  emptyVisible: !document.querySelector('#ai-empty-state').hidden,
                  composer: (() => {const r=document.querySelector('#chat-form').getBoundingClientRect();return {top:r.top,bottom:r.bottom,height:r.height}})(),
                  bottomNav: (() => {const e=document.querySelector('.mobile-workspace-bar'),r=e.getBoundingClientRect();return {top:r.top,bottom:r.bottom,height:r.height,display:getComputedStyle(e).display}})()
                })""")
                metric["theme"] = theme
                ai_layout.append(metric)
                if width in (375, 1366) and theme == "dark":
                    ai.screenshot(path=str(REPORT_DIR / f"post-ai-empty-{width}-final.png"), full_page=True)
        ai_overflows = [item for item in ai_layout if item["bodyWidth"] > item["width"] or item["documentWidth"] > item["width"]]
        add_result(results, "AI workspace has no horizontal overflow across 10 widths in light and dark themes", not ai_overflows,
                   checks=len(ai_layout), overflows=ai_overflows)
        phone_sizes = [item for item in ai_layout if item["theme"] == "light" and item["width"] <= 414]
        composer_overlaps = [item for item in phone_sizes if item["composer"]["bottom"] > item["bottomNav"]["top"]]
        add_result(results, "AI composer stays above fixed navigation at five phone widths", not composer_overlaps,
                   checks=len(phone_sizes), overlaps=composer_overlaps)
        ai.set_viewport_size({"width": 375, "height": 812})
        ai.wait_for_timeout(80)
        resized_placeholder = ai.locator("#chat-input").get_attribute("placeholder")
        add_result(results, "AI composer placeholder shortens when resizing back to phone width", resized_placeholder == "Ask anything…",
                   placeholder=resized_placeholder)
        ai_zoom: list[dict[str, object]] = []
        for width in (375, 1366):
            ai.set_viewport_size({"width": width, "height": 900})
            for zoom in (0.8, 1, 1.25, 1.5):
                ai.evaluate("scale => { document.body.style.zoom = String(scale); }", zoom)
                ai.wait_for_timeout(60)
                ai_zoom.append(ai.evaluate("""() => ({viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth,zoom:document.body.style.zoom})"""))
        ai.evaluate("document.body.style.zoom = ''")
        results.append({"check": "CSS zoom simulation only; native browser zoom is not verified", "status": "INFO",
                        "note": "CSS zoom simulation is not equivalent to browser zoom; native 80%, 100%, 125%, and 150% zoom remain untested.",
                        "measurements": ai_zoom})
        ai.close()

        # Studio: load a 69-page PDF, navigate, persist position, reload, and clear.
        studio = browser.new_page(viewport={"width": 375, "height": 812}, color_scheme="light")
        studio.on("pageerror", lambda error: errors.append({"url": studio.url, "message": str(error)}))
        studio.goto(BASE_URL + "/", wait_until="domcontentloaded")
        studio.evaluate("window.switchWorkspaceView('studio', null, false)")
        studio.locator("#studio-file-input").set_input_files(str(PDF_69))
        pages_loaded = wait_for_text(studio, "#studio-page-count", "69", timeout=90)
        sheet_count = studio.locator("#studio-page-stack .studio-page-sheet").count()
        add_result(results, "Studio loads the 69-page PDF and builds page slots", pages_loaded and sheet_count == 69,
                   pageCount=studio.locator("#studio-page-count").inner_text(), sheetCount=sheet_count)
        studio.locator("#page-jump-input").fill("5")
        studio.locator("#page-jump-input").press("Enter")
        studio.wait_for_timeout(600)
        page_five_before = studio.locator("#page-jump-input").input_value() == "5" and studio.locator("#studio-page-stack .studio-page-sheet.is-current[data-page='5']").count() == 1
        page_five_rendered_before = studio.locator("#studio-page-stack .studio-page-sheet[data-page='5'] .pdf-page-canvas[data-rendered='true']").count() == 1
        if not page_five_rendered_before:
            try:
                studio.locator("#studio-page-stack .studio-page-sheet[data-page='5'] .pdf-page-canvas[data-rendered='true']").wait_for(state="attached", timeout=12000)
                page_five_rendered_before = True
            except Exception:
                page_five_rendered_before = False
        studio.screenshot(path=str(REPORT_DIR / "post-studio-page-5-375-final.png"))
        add_result(results, "Studio page jump activates page 5", page_five_before,
                   currentPageInput=studio.locator("#page-jump-input").input_value(), pageFiveCurrent=studio.locator("#studio-page-stack .studio-page-sheet.is-current[data-page='5']").count() == 1)
        add_result(results, "Studio page 5 canvas renders after page jump", page_five_rendered_before,
                   rendered=page_five_rendered_before)
        studio.wait_for_timeout(500)
        studio.reload(wait_until="domcontentloaded")
        studio.evaluate("window.switchWorkspaceView('studio', null, false)")
        restored_69 = wait_for_text(studio, "#studio-page-count", "69", timeout=90)
        restored_page_five = False
        if restored_69:
            end = time.monotonic() + 60
            while time.monotonic() < end:
                if studio.locator("#page-jump-input").input_value() == "5" and studio.locator("#studio-page-stack .studio-page-sheet.is-current[data-page='5']").count() == 1:
                    restored_page_five = True
                    break
                studio.wait_for_timeout(120)
        restored_page_five_rendered = studio.locator("#studio-page-stack .studio-page-sheet[data-page='5'] .pdf-page-canvas[data-rendered='true']").count() == 1 if restored_69 else False
        if restored_69 and not restored_page_five_rendered:
            try:
                studio.locator("#studio-page-stack .studio-page-sheet[data-page='5'] .pdf-page-canvas[data-rendered='true']").wait_for(state="attached", timeout=12000)
                restored_page_five_rendered = True
            except Exception:
                restored_page_five_rendered = False
        add_result(results, "Studio source PDF and page 5 restore after reload", restored_69 and restored_page_five,
                   pageCountRestored=restored_69, pageFiveRestored=restored_page_five,
                   currentPageInput=studio.locator("#page-jump-input").input_value())
        add_result(results, "Studio restored page 5 canvas renders", restored_page_five_rendered,
                   rendered=restored_page_five_rendered)
        studio.screenshot(path=str(REPORT_DIR / "post-studio-restored-375-final.png"))
        studio.evaluate("window.showToast('Studio notification placement check', 'success', 5000)")
        studio.locator(".toast-notice").wait_for(state="visible", timeout=3000)
        toast_layout = studio.locator(".toast-notice").evaluate("""el => {
          const r=el.getBoundingClientRect(), nav=document.querySelector('.mobile-workspace-bar'), nr=nav.getBoundingClientRect();
          return {toastBottom:r.bottom,navTop:nr.top,toastZ:Number(getComputedStyle(el).zIndex)||0,navZ:Number(getComputedStyle(nav).zIndex)||0};
        }""")
        toast_visible = toast_layout["toastBottom"] <= toast_layout["navTop"] and toast_layout["toastZ"] > toast_layout["navZ"]
        add_result(results, "Mobile Studio toast stays above fixed navigation", toast_visible, **toast_layout)

        # Responsive Studio layout: report visible dimensions rather than assuming
        # a toolbar's scrollWidth means page overflow (tool groups can wrap).
        studio_layout: list[dict[str, object]] = []
        for theme in ("light", "dark"):
            studio.evaluate("theme => window.applyTheme(theme)", theme)
            for width in WIDTHS:
                studio.set_viewport_size({"width": width, "height": 900 if width >= 768 else 812})
                studio.wait_for_timeout(90)
                render_after_resize = studio.locator("#studio-page-stack .studio-page-sheet.is-current .pdf-page-canvas[data-rendered='true']").count() == 1
                if not render_after_resize:
                    try:
                        studio.locator("#studio-page-stack .studio-page-sheet.is-current .pdf-page-canvas[data-rendered='true']").wait_for(state="attached", timeout=12000)
                        render_after_resize = True
                    except Exception:
                        render_after_resize = False
                metric = studio.evaluate("""() => ({
                  width: innerWidth,
                  bodyWidth: document.body.scrollWidth,
                  documentWidth: document.documentElement.scrollWidth,
                  toolbar: (() => {const e=document.querySelector('#studio-toolbar'),r=e.getBoundingClientRect();return {left:r.left,right:r.right,width:r.width,scrollWidth:e.scrollWidth}})(),
                  canvas: (() => {const e=document.querySelector('#studio-canvas-area'),r=e.getBoundingClientRect();return {left:r.left,right:r.right,width:r.width,height:r.height}})(),
                  page: (() => {const e=document.querySelector('#studio-page-stack .studio-page-sheet.is-current'),r=e?.getBoundingClientRect();return r?{left:r.left,right:r.right,width:r.width}:null})(),
                  topbarTop:document.querySelector('.topbar').getBoundingClientRect().top
                })""")
                metric["theme"] = theme
                metric["currentCanvasRendered"] = render_after_resize
                studio_layout.append(metric)
                if width in (333, 375, 414, 768, 1366):
                    studio.screenshot(path=str(REPORT_DIR / f"post-studio-loaded-{width}-{theme}-final.png"))
        studio_overflows = [item for item in studio_layout if item["bodyWidth"] > item["width"] or item["documentWidth"] > item["width"]]
        studio_render_failures = [item for item in studio_layout if not item["currentCanvasRendered"]]
        add_result(results, "Studio has no horizontal page overflow across 10 responsive widths and 2 themes", not studio_overflows,
                   checks=len(studio_layout), overflows=studio_overflows)
        add_result(results, "Studio current page rerenders after viewport and theme changes", not studio_render_failures,
                   checks=len(studio_layout), failures=studio_render_failures)

        studio.locator("#studio-clear-work-btn").click()
        dialog_open = studio.locator("dialog.app-confirm-dialog[open]").is_visible()
        add_result(results, "Studio clear saved work requests explicit confirmation", dialog_open)
        if dialog_open:
            studio.locator("dialog.app-confirm-dialog .app-confirm-accept").click()
        cleared = wait_for_text(studio, "#studio-page-count", "0", timeout=20)
        add_result(results, "Studio clear confirmation removes loaded work", cleared and studio.locator("#studio-page-stack .studio-page-sheet").count() == 0,
                   pageCount=studio.locator("#studio-page-count").inner_text(), sheetCount=studio.locator("#studio-page-stack .studio-page-sheet").count())
        studio.reload(wait_until="domcontentloaded")
        studio.evaluate("window.switchWorkspaceView('studio', null, false)")
        studio.wait_for_timeout(700)
        empty_after_reload = studio.locator("#studio-page-count").inner_text() == "0"
        add_result(results, "Cleared Studio PDF does not return after reload", empty_after_reload,
                   pageCount=studio.locator("#studio-page-count").inner_text())
        studio.close()

        browser.close()

    report = {
        "testCount": len(results),
        "passed": sum(result["status"] == "PASS" for result in results),
        "failed": sum(result["status"] == "FAIL" for result in results),
        "pageErrors": errors,
        "generalAiService": general_ai,
        "results": results,
    }
    output = REPORT_DIR / "responsive-and-reload-flow-results.json"
    report["blocked"] = sum(result["status"] == "BLOCKED" for result in results)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(output), "testCount": report["testCount"], "passed": report["passed"], "failed": report["failed"], "blocked": report["blocked"], "pageErrors": len(errors), "generalAIRequestSeen": general_ai["requestSeen"], "generalAIStatuses": general_ai["httpStatuses"]}, indent=2))


if __name__ == "__main__":
    main()
