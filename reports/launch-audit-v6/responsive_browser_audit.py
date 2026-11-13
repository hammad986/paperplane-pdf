from __future__ import annotations

import json
import time
from pathlib import Path

import fitz
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8501"
NOTES = ROOT / "runtime_data_codex_audit" / "notes_69pages_audit.pdf"
WIDTHS = [360, 375, 414, 768, 1104, 1280, 1366, 1920]


def metrics(page, selector_map: dict[str, str]) -> dict:
    return page.evaluate(
        """selectors => {
          const box = selector => {
            const element = document.querySelector(selector);
            if (!element) return null;
            const rect = element.getBoundingClientRect();
            const style = getComputedStyle(element);
            return {
              x: Math.round(rect.x), y: Math.round(rect.y),
              width: Math.round(rect.width), height: Math.round(rect.height),
              right: Math.round(rect.right), bottom: Math.round(rect.bottom),
              visible: style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0
            };
          };
          const boxes = Object.fromEntries(Object.entries(selectors).map(([name, selector]) => [name, box(selector)]));
          return {
            viewport: { width: innerWidth, height: innerHeight },
            documentWidth: document.documentElement.scrollWidth,
            bodyWidth: document.body.scrollWidth,
            theme: document.body.classList.contains('dark-mode') ? 'dark' : 'light',
            boxes,
            gridColumns: getComputedStyle(document.querySelector('.ai-studio-container')).gridTemplateColumns,
            uploadHidden: document.querySelector('#ai-upload-inline-btn')?.hidden ?? null,
            uploadVisible: box('#ai-upload-inline-btn')?.visible ?? false,
            badgeText: document.querySelector('#trigger-summary-btn')?.closest('.ai-chat-card')?.querySelector('.view-header-badge')?.textContent?.trim() || null
          };
        }""",
        selector_map,
    )


def wait_for(page, predicate, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.1)
    return bool(predicate())


evidence: dict = {"base": BASE, "fixture_pages": fitz.open(NOTES).page_count, "ai": {}, "studio": {}, "directory": {}, "page_errors": [], "console_errors": []}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 375, "height": 812}, is_mobile=True, has_touch=True, accept_downloads=True)
    page = context.new_page()
    page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
    page.on("console", lambda message: evidence["console_errors"].append(message.text) if message.type == "error" else None)
    page.goto(f"{BASE}/tool-desk", wait_until="domcontentloaded")
    page.locator("#view-tool-desk-directory").wait_for(state="visible")
    wait_for(page, lambda: page.locator("#tool-desk-tools-catalog .home-tool-card").count() == 41, 30)
    evidence["directory"] = page.evaluate("""() => ({
      pathname: location.pathname,
      duplicateHomeTabCount: document.querySelectorAll('#tab-home-view').length,
      toolCount: document.querySelectorAll('#tool-desk-tools-catalog .home-tool-card').length,
      sectionCount: document.querySelectorAll('#tool-desk-tools-catalog .home-cat-section').length,
      heading: document.querySelector('#view-tool-desk-directory h1')?.textContent?.trim() || null
    })""")

    page.evaluate("window.switchWorkspaceView('ai', null, false)")
    page.locator("#view-ai-studio").wait_for(state="visible")
    ai_boxes = {
        "wrapper": ".ai-studio-wrapper",
        "topbar": ".ai-studio-topbar",
        "ephemeral": ".ephemeral-work-notice",
        "engine": ".ai-engine-notice-bar",
        "grid": ".ai-studio-container",
        "chat": ".ai-chat-card",
        "form": "#chat-form",
        "nav": ".mobile-workspace-bar",
        "doc": "#ai-active-doc-bar",
        "metadata": "#trigger-extract-btn",
        "summary": "#summary-display",
        "header": ".topbar",
        "account": "#topbar-auth-user",
        "badge": ".view-header-badge"
    }
    for theme in ("dark", "light"):
        page.evaluate("theme => { document.body.classList.toggle('dark-mode', theme === 'dark'); document.body.classList.toggle('light-mode', theme === 'light'); localStorage.setItem('paperplane_theme', theme); }", theme)
        for width in WIDTHS:
            page.set_viewport_size({"width": width, "height": 860 if width >= 768 else 812})
            page.wait_for_timeout(120)
            item = metrics(page, ai_boxes)
            form_box, nav_box = item["boxes"]["form"], item["boxes"]["nav"]
            item["formClearOfNav"] = not form_box or not nav_box or form_box["bottom"] <= nav_box["y"] + 1 or width > 900
            item["horizontalOverflow"] = item["documentWidth"] > width or item["bodyWidth"] > width
            evidence["ai"].setdefault(theme, {})[f"empty-{width}"] = item
            if width in (375, 768, 1104, 1280, 1366, 1920):
                page.evaluate("window.scrollTo(0, 0)")
                page.screenshot(path=str(OUT / f"after-ai-empty-{theme}-{width}.png"))

    # Test all required conversational greetings without a PDF.
    page.set_viewport_size({"width": 375, "height": 812})
    page.evaluate("document.body.classList.add('dark-mode'); document.body.classList.remove('light-mode')")
    def ask(question: str) -> dict:
        page.locator("#chat-input").fill(question)
        page.locator("#chat-send-btn").click()
        def finished() -> bool:
            bubbles = page.locator("#chat-messages .chat-bubble.ai")
            if bubbles.count() == 0:
                return False
            last = bubbles.last
            stage = last.locator(".ai-stage-line span:last-child")
            if stage.count():
                return stage.inner_text().strip() in ("Complete", "Connection interrupted")
            return bool(last.inner_text().strip())
        completed = wait_for(page, finished, 45)
        last = page.locator("#chat-messages .chat-bubble.ai").last
        answer_node = last.locator(".ai-stream-text, .chat-markdown")
        answer = answer_node.inner_text().strip() if answer_node.count() else last.inner_text().strip()
        return {"completed": completed, "answer": answer, "citations": last.locator(".ai-citation-tag").all_inner_texts()}

    evidence["ai"]["greetingsNoDocument"] = {question: ask(question) for question in ("hey", "hello", "how are you")}

    page.locator("#ai-file-input").set_input_files(str(NOTES))
    page.locator("#ai-active-doc-bar").wait_for(state="visible", timeout=60_000)
    evidence["ai"]["greetingsWithDocument"] = {question: ask(question) for question in ("hey", "hello", "how are you")}
    evidence["ai"]["documentQuestionWithPdf"] = ask("What is on page 1?")
    page.locator("#chat-messages").evaluate("element => element.scrollTop = 0")
    loaded_states = {}
    for theme in ("dark", "light"):
        page.evaluate("theme => { document.body.classList.toggle('dark-mode', theme === 'dark'); document.body.classList.toggle('light-mode', theme === 'light'); localStorage.setItem('paperplane_theme', theme); }", theme)
        for width in WIDTHS:
            page.set_viewport_size({"width": width, "height": 860 if width >= 768 else 812})
            page.wait_for_timeout(120)
            item = metrics(page, ai_boxes)
            form_box, nav_box = item["boxes"]["form"], item["boxes"]["nav"]
            item["formClearOfNav"] = not form_box or not nav_box or form_box["bottom"] <= nav_box["y"] + 1 or width > 900
            item["horizontalOverflow"] = item["documentWidth"] > width or item["bodyWidth"] > width
            loaded_states[f"{theme}-{width}"] = item
            if width in (375, 768, 1104, 1280, 1366, 1920):
                page.evaluate("window.scrollTo(0, 0)")
                page.screenshot(path=str(OUT / f"after-ai-loaded-{theme}-{width}.png"))
    evidence["ai"]["loaded"] = loaded_states
    # The app's provider is deliberately unconfigured in this environment. Inject
    # a synthetic long result only to verify that content cannot resize the grid.
    brief_layout = {}
    for theme in ("dark", "light"):
        page.evaluate("theme => { document.body.classList.toggle('dark-mode', theme === 'dark'); document.body.classList.toggle('light-mode', theme === 'light'); localStorage.setItem('paperplane_theme', theme); }", theme)
        for width in (375, 768, 1104, 1280, 1366, 1920):
            page.set_viewport_size({"width": width, "height": 860 if width >= 768 else 812})
            before = metrics(page, ai_boxes)
            page.evaluate("""() => {
              const out = document.querySelector('#summary-display');
              out.textContent = ('Synthetic layout-only brief sentence. ').repeat(90);
              out.style.minHeight = '140px';
            }""")
            page.wait_for_timeout(120)
            after = metrics(page, ai_boxes)
            brief_layout[f"{theme}-{width}"] = {
              "beforeChat": before["boxes"]["chat"], "afterChat": after["boxes"]["chat"],
              "beforeMetadata": before["boxes"]["metadata"], "afterMetadata": after["boxes"]["metadata"],
              "beforeSummary": before["boxes"]["summary"], "afterSummary": after["boxes"]["summary"],
              "horizontalOverflow": after["documentWidth"] > width or after["bodyWidth"] > width,
            }
            page.screenshot(path=str(OUT / f"after-ai-synthetic-brief-{theme}-{width}.png"))
            page.evaluate("document.querySelector('#summary-display').textContent = 'Summary will appear here after generation…'")
    evidence["ai"]["syntheticBriefLayoutOnly"] = brief_layout

    # Exercise the no-document gate after clearing the attachment.
    page.set_viewport_size({"width": 375, "height": 812})
    page.locator("#ai-clear-doc-btn").click()
    page.locator("#ai-active-doc-bar").wait_for(state="hidden")
    page.locator("#chat-input").fill("Find important keywords from the older PDF I uploaded")
    page.locator("#chat-send-btn").click()
    gate_visible = wait_for(page, lambda: page.locator("#chat-messages .ai-document-required").count() > 0, 5)
    evidence["ai"]["documentQuestionWithoutPdf"] = {
        "gateShown": gate_visible,
        "message": page.locator("#chat-messages .ai-document-required").last.inner_text().strip() if gate_visible else None,
    }
    page.evaluate("window.scrollTo(0, 0)")
    page.screenshot(path=str(OUT / "after-ai-no-document-guidance-375.png"))
    context.close()

    # Studio mobile-first canvas and slide-over controls. Load a real 69-page PDF.
    context = browser.new_context(viewport={"width": 375, "height": 812}, is_mobile=True, has_touch=True, accept_downloads=True)
    page = context.new_page()
    page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
    page.on("console", lambda message: evidence["console_errors"].append(message.text) if message.type == "error" else None)
    page.goto(f"{BASE}/studio", wait_until="domcontentloaded")
    page.locator("#studio-file-input").set_input_files(str(NOTES))
    if not wait_for(page, lambda: page.locator("#studio-page-count").inner_text().strip() == "69", 90):
        raise RuntimeError("Studio did not load all 69 pages")
    page.locator("#studio-page-stack .studio-page-sheet.is-current canvas[data-rendered=true]").wait_for(timeout=45_000)
    page.locator(".toast-notice").wait_for(state="detached", timeout=8_000)
    mobile_widths = {}
    for theme in ("dark", "light"):
      page.evaluate("theme => { document.body.classList.toggle('dark-mode', theme === 'dark'); document.body.classList.toggle('light-mode', theme === 'light'); localStorage.setItem('paperplane_theme', theme); }", theme)
      for width in (360, 375, 414, 768, 1104, 1280, 1366, 1920):
        page.set_viewport_size({"width": width, "height": 860 if width >= 768 else 812})
        page.locator("#studio-page-stack .studio-page-sheet.is-current canvas[data-rendered=true]").wait_for(timeout=30_000)
        page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
        page.wait_for_timeout(700)
        state = page.evaluate("""() => {
          const rect = selector => { const e = document.querySelector(selector); if (!e) return null; const r = e.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),right:Math.round(r.right),bottom:Math.round(r.bottom),width:Math.round(r.width),height:Math.round(r.height)}; };
          const primary = document.querySelector('.studio-primary-ribbon');
          const secondary = document.querySelector('.studio-sub-ribbon');
          const canvas = document.querySelector('#studio-page-stack .studio-page-sheet.is-current canvas[data-rendered=true]');
          return {viewport:{width:innerWidth,height:innerHeight},documentWidth:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth,
            pageCount:document.querySelector('#studio-page-count')?.textContent,canvasRendered:!!canvas,
             activePageRenderState:[...document.querySelectorAll('#studio-page-stack .studio-page-sheet.is-current')].map(slot=>({page:slot.dataset.page,canvas:[...slot.querySelectorAll('canvas')].map(node=>({id:node.id,rendered:node.dataset.rendered||null,width:node.width,height:node.height,rect:Math.round(node.getBoundingClientRect().width)}))})),
            toolbar:rect('.studio-toolbar'),primary:rect('.studio-primary-ribbon'),secondary:rect('.studio-sub-ribbon'),
            dock:rect('#studio-mobile-dock'),nav:rect('.mobile-workspace-bar'),notice:rect('.studio-ephemeral-notice'),
            primaryScroll:primary?{width:primary.scrollWidth,clientWidth:primary.clientWidth}:null,
            secondaryScroll:secondary?{width:secondary.scrollWidth,clientWidth:secondary.clientWidth}:null,
            duplicateLabels:[...document.querySelectorAll('.studio-toolbar button')].map(b=>b.innerText.trim()).filter(t=>t && /Add Page Add page|Dup Duplicate/i.test(t)),
            runButton:rect('#save-studio-btn')};
        }""")
        mobile_widths[f"{theme}-{width}"] = state
        if width in (375, 768, 1104, 1280, 1366, 1920):
            page.screenshot(path=str(OUT / f"after-studio-loaded-{theme}-{width}.png"))
    page.evaluate("document.body.classList.add('dark-mode'); document.body.classList.remove('light-mode'); localStorage.setItem('paperplane_theme', 'dark')")
    page.set_viewport_size({"width": 375, "height": 812})
    page.locator("#studio-mobile-pages-btn").click()
    page.locator("#studio-thumbnails-bar").wait_for(state="visible")
    thumbnail_samples = []
    for sample_page in (1, 35, 69):
        card = page.locator(f"#studio-thumbnails-container .organizer-thumb-card[data-page='{sample_page}']")
        card.scroll_into_view_if_needed(timeout=20_000)
        preview = card.locator(".thumb-rendered-img, .thumb-rendered-canvas")
        preview.wait_for(state="visible", timeout=30_000)
        has_pixels = preview.evaluate("el => el.tagName === 'IMG' ? el.complete && el.naturalWidth > 0 : el.width > 0 && el.height > 0")
        assert has_pixels, f"Thumbnail {sample_page} has no rendered content"
        thumbnail_samples.append({"page": sample_page, "rendered": True})
    page.locator("#studio-thumbnails-container").evaluate("el => el.scrollTop = 0")
    drawer = page.evaluate("""() => ({
      drawer:(() => {const r=document.querySelector('#studio-thumbnails-bar').getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),right:Math.round(r.right),bottom:Math.round(r.bottom)}})(),
      toolbarBottom:Math.round(document.querySelector('.studio-toolbar').getBoundingClientRect().bottom),
      dockTop:Math.round(document.querySelector('#studio-mobile-dock').getBoundingClientRect().top),
      renderedThumbnails:document.querySelectorAll('#studio-thumbnails-container .thumb-rendered-canvas, #studio-thumbnails-container .thumb-rendered-img').length
    })""")
    drawer["sampledThumbnails"] = thumbnail_samples
    page.screenshot(path=str(OUT / "after-studio-pages-375.png"))
    page.locator("#studio-mobile-pages-close").click()
    page.locator("#mobile-menu-btn").click()
    page.locator("#sidebar.mobile-open").wait_for(state="visible")
    page.screenshot(path=str(OUT / "after-studio-sidebar-375.png"))
    with page.expect_download(timeout=45_000) as download_event:
        page.locator("#save-studio-btn").click()
    export = download_event.value
    export_path = OUT / "after-studio-sidebar-export.pdf"
    export.save_as(str(export_path))
    exported = fitz.open(export_path)
    sidebar_export = {"pages": exported.page_count, "firstPageText": exported[0].get_text()[:250], "filename": export.suggested_filename}
    exported.close()
    page.locator("#mobile-backdrop").click(position={"x": 370, "y": 400})
    page.locator("#studio-mobile-properties-btn").click()
    properties = page.locator("#studio-mobile-properties-panel").is_visible()
    page.screenshot(path=str(OUT / "after-studio-properties-375.png"))
    page.locator("#studio-mobile-properties-close").click()
    # Jump rendering is timed from Go to page commit until the visible canvas is usable.
    jumps = []
    for target in (69, 1, 35):
        started = time.monotonic()
        page.locator("#page-jump-input").fill(str(target))
        page.locator("#page-jump-input").press("Enter")
        page.locator(f"#studio-page-stack .studio-page-sheet.is-current[data-page='{target}'] canvas[data-rendered=true]").wait_for(timeout=30_000)
        jumps.append({"page": target, "renderSeconds": round(time.monotonic() - started, 3), "counter": page.locator("#page-jump-input").input_value()})
    page.locator("#btn-mode-organize").click()
    page.locator("#studio-thumbnails-bar").wait_for(state="visible")
    assert page.locator("#studio-mobile-pages-btn").get_attribute("aria-expanded") == "true"
    # Interact with the visible label in the pages drawer, then assert state.
    page.locator("#organizer-grid .organizer-thumb-card[data-page='69'] .thumb-checkbox-label").click()
    assert page.locator("#organizer-grid .organizer-thumb-card[data-page='69'] .thumb-checkbox").is_checked()
    assert page.locator("#organizer-batch-bar").evaluate("el => el.parentElement.id") == "studio-mobile-batch-slot"
    page.screenshot(path=str(OUT / "after-studio-organize-selected-375.png"))
    page.locator("#batch-delete-btn").click()
    confirm = page.locator("dialog.app-confirm-dialog[open]")
    confirm.wait_for(state="visible")
    confirm_text = confirm.inner_text()
    assert "undo this for 10 seconds" in confirm_text
    confirm.locator(".app-confirm-accept").click()
    wait_for(page, lambda: page.locator("#studio-page-count").inner_text().strip() == "68", 60)
    after_delete_position = page.locator("#page-jump-input").input_value()
    assert after_delete_position == "35", after_delete_position
    retained = []
    for reload_number in (1, 2):
        page.reload(wait_until="domcontentloaded")
        wait_for(page, lambda: page.locator("#studio-page-count").count() > 0 and page.locator("#studio-page-count").inner_text().strip() == "68", 90)
        restored_page = page.locator("#page-jump-input").input_value()
        assert restored_page == "35", {"reload": reload_number, "page": restored_page}
        retained.append({"reload": reload_number, "pageCount": page.locator("#studio-page-count").inner_text().strip(), "page": restored_page})
    page.screenshot(path=str(OUT / "after-studio-deletion-retained-375.png"))
    evidence["studio"] = {"widths": mobile_widths, "pagesDrawer": drawer, "propertiesOpenClose": properties, "sidebarExport": sidebar_export, "pageJumps": jumps, "deleteRetention": retained, "positionAfterDelete": after_delete_position, "deleteConfirmation": confirm_text}
    context.close()

    browser.close()

(OUT / "responsive-browser-audit.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
summary = {
    "results": str(OUT / "responsive-browser-audit.json"),
    "directory": evidence["directory"],
    "greetingsNoDocument": evidence["ai"].get("greetingsNoDocument"),
    "greetingsWithDocument": evidence["ai"].get("greetingsWithDocument"),
    "documentQuestionWithPdf": evidence["ai"].get("documentQuestionWithPdf"),
    "documentQuestionWithoutPdf": evidence["ai"].get("documentQuestionWithoutPdf"),
    "loadedAI": {
        key: {field: value.get(field) for field in ("horizontalOverflow", "formClearOfNav", "uploadHidden", "badgeText")}
        for key, value in evidence["ai"]["loaded"].items() if key in {"dark-360", "dark-375", "dark-414", "light-375"}
    },
    "studio": {
        "widths": {width: {field: value.get(field) for field in ("documentWidth", "bodyWidth", "canvasRendered", "activePageRenderState", "primaryScroll", "secondaryScroll")} for width, value in evidence["studio"]["widths"].items()},
        "pagesDrawer": evidence["studio"].get("pagesDrawer"),
        "propertiesOpenClose": evidence["studio"].get("propertiesOpenClose"),
        "sidebarExport": evidence["studio"].get("sidebarExport"),
        "pageJumps": evidence["studio"].get("pageJumps"),
        "positionAfterDelete": evidence["studio"].get("positionAfterDelete"),
        "deleteConfirmation": evidence["studio"].get("deleteConfirmation"),
        "deleteRetention": evidence["studio"].get("deleteRetention"),
    },
    "page_errors": evidence["page_errors"],
    "console_errors": evidence["console_errors"],
}
print(json.dumps(summary, indent=2, ensure_ascii=False))
