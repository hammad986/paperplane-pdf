from __future__ import annotations

import json
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


OUT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8501"
WIDTHS = (375, 768, 1104, 1280, 1366, 1920)
SCREENSHOT_WIDTHS = (375, 768, 1104, 1366, 1920)
SELECTED = {"merge", "compress", "translate"}


def safe_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


result = {"tools": [], "pageErrors": [], "consoleErrors": [], "screenshots": []}
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 375, "height": 900}, is_mobile=True, has_touch=True)
    page = context.new_page()
    page.on("pageerror", lambda error: result["pageErrors"].append(str(error)))
    page.on("console", lambda message: result["consoleErrors"].append(message.text) if message.type == "error" else None)
    page.goto(f"{BASE}/tool-desk", wait_until="domcontentloaded")
    page.locator("#tool-desk-tools-catalog .home-tool-card").first.wait_for(state="visible")
    deadline = time.monotonic() + 30
    while page.locator("#tool-desk-tools-catalog .home-tool-card").count() != 41 and time.monotonic() < deadline:
        page.wait_for_timeout(100)
    tools = page.locator("#tool-desk-tools-catalog .home-tool-card").evaluate_all(
        "nodes => nodes.map(node => ({id: node.dataset.selectOperation, label: node.querySelector('.home-tool-title')?.textContent.trim() || ''}))"
    )
    assert len(tools) == 41, f"Expected 41 directory entries, found {len(tools)}"
    result["directory"] = {"tools": len(tools), "sections": page.locator("#tool-desk-tools-catalog .home-cat-section").count()}

    local_mode_results = []
    expected_local_tools = {"merge", "split", "remove", "rotate"}
    for tool in tools:
        actual = page.evaluate("""operation => {
          window.selectOperation(operation, false);
          const toggle = document.querySelector('#client-privacy-toggle');
          const supported = ['merge', 'split', 'remove', 'rotate'].includes(operation);
          const initiallyDisabled = toggle.disabled;
          let accepted = false;
          let refused = false;
          let message = '';
          if (supported) {
            window.setClientSideMode(true);
            accepted = state.clientSideMode && toggle.checked;
            window.setClientSideMode(false);
            refused = !accepted;
          } else {
            window.setClientSideMode(true);
            refused = !state.clientSideMode;
            message = document.querySelector('.toast-notice')?.textContent.trim() || '';
          }
          return {operation, supported, initiallyDisabled, accepted, refused, message,
            helper: document.querySelector('#privacy-mode-support')?.textContent.trim() || ''};
        }""", tool["id"])
        assert actual["supported"] == (tool["id"] in expected_local_tools), actual
        assert actual["initiallyDisabled"] == (tool["id"] not in expected_local_tools), actual
        assert actual["refused"] == (tool["id"] not in expected_local_tools), actual
        if actual["supported"]:
            assert actual["accepted"], actual
        else:
            assert "uses server processing" in actual["message"].lower(), actual
            assert actual["helper"] == "This tool runs on the server", actual
        local_mode_results.append(actual)
    result["localProcessing"] = local_mode_results

    for tool in tools:
        page.set_viewport_size({"width": 375, "height": 900})
        page.locator(f"#tool-desk-tools-catalog .home-tool-card[data-select-operation='{tool['id']}']").click()
        page.locator("#view-tool-desk").wait_for(state="visible")
        page.locator("#tool-title").wait_for(state="visible")
        entry = {"id": tool["id"], "catalogLabel": tool["label"], "route": page.evaluate("location.pathname"), "widths": {}}
        is_selected = tool["id"] in SELECTED

        for theme in (("dark", "light") if is_selected else ("dark",)):
            page.evaluate(
                "theme => { document.body.classList.toggle('dark-mode', theme === 'dark'); document.body.classList.toggle('light-mode', theme === 'light'); localStorage.setItem('paperplane_theme', theme); }",
                theme,
            )
            for width in WIDTHS:
                page.set_viewport_size({"width": width, "height": 900})
                page.wait_for_timeout(50)
                metrics = page.evaluate("""() => {
                  const rect = selector => { const el = document.querySelector(selector); if (!el) return null; const r = el.getBoundingClientRect(); return {x: Math.round(r.x), right: Math.round(r.right), y: Math.round(r.y), bottom: Math.round(r.bottom), width: Math.round(r.width), height: Math.round(r.height)}; };
                  const button = document.querySelector('#run-button');
                  const buttonLabel = button?.querySelector('span');
                  const buttonText = buttonLabel?.textContent.trim() || '';
                  const fontSize = buttonLabel ? parseFloat(getComputedStyle(buttonLabel).fontSize) : 0;
                  const lineHeight = buttonLabel ? (parseFloat(getComputedStyle(buttonLabel).lineHeight) || fontSize * 1.2) : 0;
                  const visibleControls = [...document.querySelectorAll('#job-form input, #job-form select, #job-form textarea')].filter(el => {
                    const style = getComputedStyle(el); const r = el.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && r.width > 0 && r.height > 0;
                  });
                  const unlabelledControls = visibleControls.filter(el => !el.labels?.length && !el.getAttribute('aria-label') && !el.getAttribute('aria-labelledby')).map(el => ({id: el.id, type: el.type || el.tagName.toLowerCase()}));
                  const howto = [...document.querySelectorAll('.seo-howto-step')].map(step => ({heading: step.querySelector('h3')?.textContent.trim() || '', paragraphs: [...step.querySelectorAll('p')].map(p => p.textContent.trim())}));
                  return {viewport: innerWidth, documentWidth: document.documentElement.scrollWidth, bodyWidth: document.body.scrollWidth,
                    title: document.querySelector('#tool-title')?.textContent.trim() || null, hero: rect('.tool-hero-card'), dropzone: rect('#dropzone'),
                    runButton: rect('#run-button'), runLabel: buttonText, runButtonLineHeight: lineHeight,
                    runButtonWrapped: !!buttonLabel && lineHeight > 0 && buttonLabel.getBoundingClientRect().height > lineHeight * 1.65,
                    unlabelledControls, duplicatedHowToSteps: howto.filter(step => step.paragraphs.includes(step.heading)).length,
                    toolHeadingCount: document.querySelectorAll('#tool-title').length};
                }""")
                metrics["horizontalOverflow"] = metrics["documentWidth"] > width or metrics["bodyWidth"] > width
                entry["widths"].setdefault(theme, {})[str(width)] = metrics

                if is_selected and width in SCREENSHOT_WIDTHS:
                    page.evaluate("window.scrollTo(0, 0)")
                    path = OUT / f"tool-{safe_name(tool['label'])}-{theme}-{width}.png"
                    page.screenshot(path=str(path))
                    result["screenshots"].append(path.name)

        result["tools"].append(entry)
        page.evaluate("window.switchWorkspaceView('tool-desk', null, false)")
        page.locator("#tool-desk-tools-catalog .home-tool-card").first.wait_for(state="visible")

    context.close()
    browser.close()

result["issueSummary"] = {
    "overflow": [{"tool": item["id"], "theme": theme, "width": width} for item in result["tools"] for theme, widths in item["widths"].items() for width, metric in widths.items() if metric["horizontalOverflow"]],
    "wrappedRunButtons": [{"tool": item["id"], "theme": theme, "width": width, "label": metric["runLabel"]} for item in result["tools"] for theme, widths in item["widths"].items() for width, metric in widths.items() if metric["runButtonWrapped"]],
    "unlabelledControls": [{"tool": item["id"], "theme": theme, "width": width, "controls": metric["unlabelledControls"]} for item in result["tools"] for theme, widths in item["widths"].items() for width, metric in widths.items() if metric["unlabelledControls"]],
    "duplicatedHowToSteps": [{"tool": item["id"], "theme": theme, "width": width, "count": metric["duplicatedHowToSteps"]} for item in result["tools"] for theme, widths in item["widths"].items() for width, metric in widths.items() if metric["duplicatedHowToSteps"]],
}
(OUT / "tool-pages-responsive-scan.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps({"directory": result["directory"], "toolCount": len(result["tools"]), "selectedScreenshots": len(result["screenshots"]), "issues": result["issueSummary"], "pageErrors": result["pageErrors"], "consoleErrors": result["consoleErrors"], "evidence": str(OUT / "tool-pages-responsive-scan.json")}, indent=2, ensure_ascii=False))
