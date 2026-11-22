from __future__ import annotations

import json
import tempfile
from pathlib import Path

import fitz
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports"
SCREENSHOT_DIR = REPORT_DIR / "screenshots"
BASE_URL = "http://127.0.0.1:8501"


def main() -> None:
    REPORT_DIR.mkdir(exist_ok=True)
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    fixture_path = Path(tempfile.gettempdir()) / "paperplane-browser-fixture.pdf"
    fixture_doc = fitz.open()
    fixture_page = fixture_doc.new_page()
    fixture_page.insert_text((72, 72), "Paperplane browser verification fixture")
    fixture_doc.save(str(fixture_path))
    fixture_doc.close()
    findings: list[dict[str, object]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True,
        )
        page = browser.new_page(viewport={"width": 1440, "height": 980}, color_scheme="light")
        console_messages: list[str] = []
        page_errors: list[str] = []
        failed_requests: list[str] = []
        page.on("console", lambda msg: console_messages.append(f"{msg.type}: {msg.text}") if msg.type in {"error", "warning"} else None)
        page.on("pageerror", lambda err: page_errors.append(str(err)))
        page.on("requestfailed", lambda req: failed_requests.append(f"{req.method} {req.url} :: {req.failure}"))

        page.goto(BASE_URL + "/", wait_until="networkidle")
        page.screenshot(path=str(SCREENSHOT_DIR / "home-light.png"), full_page=True)

        def set_theme(theme: str) -> None:
            page.evaluate("theme => window.applyTheme(theme)", theme)

        def show_modal(modal_id: str) -> None:
            page.evaluate(
                "id => { const modal = document.getElementById(id); if (modal) modal.hidden = false; }",
                modal_id,
            )

        def hide_modal(modal_id: str) -> None:
            page.evaluate(
                "id => { const modal = document.getElementById(id); if (modal) modal.hidden = true; }",
                modal_id,
            )

        page.locator("#topbar-signin-btn").click()
        findings.append({
            "check": "topbar sign-in opens auth modal",
            "pass": page.locator("#auth-modal").is_visible() and page.locator("#tab-login").evaluate("el => el.classList.contains('active')"),
        })
        page.locator("#tab-register").click()
        findings.append({
            "check": "auth register tab is direct and visible",
            "pass": page.locator("#tab-register").evaluate("el => el.classList.contains('active')") and page.locator("#auth-modal-title").inner_text() == "Create an Account",
        })
        page.locator("#close-auth-modal").click()

        page.locator("#sidebar-settings-gear-btn").click()
        settings = page.locator("#settings-modal")
        geometry = settings.locator(".settings-modal-card").evaluate("el => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return { width: r.width, height: r.height, cssWidth: cs.width, viewport: window.innerWidth, flexBasis: cs.flexBasis }; }")
        settings_bg = settings.locator(".settings-modal-card").evaluate("el => getComputedStyle(el).backgroundColor")
        page.screenshot(path=str(SCREENSHOT_DIR / "settings-light.png"), full_page=True)
        findings.append({
            "check": "settings is spacious and light-theme adaptive",
            "pass": settings.is_visible() and geometry["cssWidth"] == "1020px" and geometry["height"] >= 580 and settings_bg in {"rgb(255, 255, 255)", "rgba(255, 255, 255, 1)"},
            "geometry": geometry,
            "background": settings_bg,
        })
        tab_layout = settings.locator(".settings-tab-btn").evaluate_all(
            "buttons => buttons.map(button => { const icon = button.querySelector(':scope > span:first-child').getBoundingClientRect(); const title = button.querySelector(':scope > span:last-child strong').getBoundingClientRect(); const overlap = Math.max(0, Math.min(icon.right, title.right) - Math.max(icon.left, title.left)) * Math.max(0, Math.min(icon.bottom, title.bottom) - Math.max(icon.top, title.top)); return { overlap, iconWidth: icon.width, iconHeight: icon.height }; })"
        )
        findings.append({
            "check": "settings tab icons are contained and do not overlap labels",
            "pass": all(item["overlap"] == 0 and 25.5 <= item["iconWidth"] <= 26.5 and 25.5 <= item["iconHeight"] <= 26.5 for item in tab_layout),
            "layout": tab_layout,
        })
        contrast = page.locator("#settings-register-btn").evaluate(
            "button => { const parse = value => { const m = value.match(/rgba?\\(([^)]+)\\)/); if (!m) return null; const p = m[1].split(',').map(v => parseFloat(v.trim())); return { rgb: p.slice(0, 3), alpha: p.length > 3 ? p[3] : 1 }; }; const lum = rgb => { const s = rgb.map(v => v / 255).map(v => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)); return 0.2126 * s[0] + 0.7152 * s[1] + 0.0722 * s[2]; }; const style = getComputedStyle(button); const fg = parse(style.color); const bg = parse(style.backgroundColor); let node = button.parentElement; let parentBg = null; while (node && !parentBg) { const candidate = parse(getComputedStyle(node).backgroundColor); if (candidate && candidate.alpha > 0) parentBg = candidate; node = node.parentElement; } const modalBg = parse(getComputedStyle(document.querySelector('#settings-modal .settings-modal-card')).backgroundColor); parentBg = parentBg || modalBg; const ratio = (a, b) => { const l1 = lum(a.rgb || a); const l2 = lum(b.rgb || b); return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05); }; return { textVsButton: ratio(fg, bg), text: style.color, buttonBackground: style.backgroundColor, effectiveParentBackground: parentBg, textVsParent: ratio(fg, parentBg) }; }"
        )
        findings.append({
            "check": "secondary buttons meet WCAG AA contrast in light mode",
            "pass": contrast["textVsButton"] >= 4.5 and contrast["textVsParent"] >= 4.5,
            "contrast": contrast,
        })
        page.locator("#settings-tab-btn-privacy").click()
        findings.append({"check": "storage and privacy settings tab exists", "pass": page.locator("#pane-privacy").is_visible()})
        page.locator("#settings-tab-btn-appearance").click()
        page.locator("#theme-dark-btn").click()
        dark_bg = settings.locator(".settings-modal-card").evaluate("el => getComputedStyle(el).backgroundColor")
        page.screenshot(path=str(SCREENSHOT_DIR / "settings-dark.png"), full_page=True)
        findings.append({"check": "settings dark mode remains explicit", "pass": dark_bg in {"rgb(17, 24, 39)", "rgba(17, 24, 39, 1)"}, "background": dark_bg})
        page.locator("#close-settings-modal").click()

        set_theme("light")
        page.locator("#topbar-signin-btn").click()
        auth_light_style = page.locator("#auth-modal .modal-card").evaluate("el => ({ background: getComputedStyle(el).backgroundColor, color: getComputedStyle(el).color })")
        page.screenshot(path=str(SCREENSHOT_DIR / "auth-light.png"), full_page=True)
        hide_modal("auth-modal")
        set_theme("dark")
        show_modal("auth-modal")
        auth_dark_style = page.locator("#auth-modal .modal-card").evaluate("el => ({ background: getComputedStyle(el).backgroundColor, color: getComputedStyle(el).color })")
        page.screenshot(path=str(SCREENSHOT_DIR / "auth-dark.png"), full_page=True)
        hide_modal("auth-modal")

        set_theme("light")
        page.locator("#topbar-upgrade-btn").click()
        pricing_light_style = page.locator("#upgrade-modal .modal-card").evaluate("el => ({ background: getComputedStyle(el).backgroundColor, color: getComputedStyle(el).color })")
        page.screenshot(path=str(SCREENSHOT_DIR / "pricing-light.png"), full_page=True)
        hide_modal("upgrade-modal")
        set_theme("dark")
        show_modal("upgrade-modal")
        pricing_dark_style = page.locator("#upgrade-modal .modal-card").evaluate("el => ({ background: getComputedStyle(el).backgroundColor, color: getComputedStyle(el).color })")
        page.screenshot(path=str(SCREENSHOT_DIR / "pricing-dark.png"), full_page=True)
        hide_modal("upgrade-modal")

        modal_theme_results: dict[str, dict[str, str]] = {}
        for theme in ("light", "dark"):
            set_theme(theme)
            show_modal("compress-modal")
            modal_theme_results[f"compress-{theme}"] = page.locator("#compress-modal .modal-card").evaluate("el => ({ background: getComputedStyle(el).backgroundColor, color: getComputedStyle(el).color })")
            page.screenshot(path=str(SCREENSHOT_DIR / f"compress-{theme}.png"), full_page=True)
            hide_modal("compress-modal")

        findings.append({
            "check": "auth, pricing, and compression modals open in both themes",
            "pass": all(style["background"] == "rgb(255, 255, 255)" for style in (auth_light_style, pricing_light_style, modal_theme_results["compress-light"])) and all(style["background"] == "rgb(17, 24, 39)" for style in (auth_dark_style, pricing_dark_style, modal_theme_results["compress-dark"])),
            "modalStyles": {"auth-light": auth_light_style, "auth-dark": auth_dark_style, "pricing-light": pricing_light_style, "pricing-dark": pricing_dark_style, **modal_theme_results},
            "screenshots": [
                "auth-light.png", "auth-dark.png", "pricing-light.png", "pricing-dark.png",
                "compress-light.png", "compress-dark.png",
            ],
        })

        set_theme("light")

        page.locator("#tab-desk-view").click()
        page.evaluate("window.selectOperation('pdf_to_word', false)")
        options = page.locator("#options")
        findings.append({"check": "empty options panel is hidden", "pass": not options.is_visible()})
        page.evaluate("window.selectOperation('ai_chat', false)")
        findings.append({"check": "AI chat has a contextual question field", "pass": page.locator("#question").is_visible() and page.locator("#question").get_attribute("placeholder") is not None})
        page.evaluate("window.selectOperation('ocr', false)")
        findings.append({"check": "OCR exposes language options", "pass": page.locator("#language").is_visible() and page.locator("#language option").count() >= 5})
        page.evaluate("window.selectOperation('repair', false)")
        findings.append({"check": "repair exposes recovery modes", "pass": page.locator("#mode").is_visible() and page.locator("#mode option").count() == 2})
        page.evaluate("window.selectOperation('word_to_pdf', false)")
        findings.append({"check": "Office engine badge is visible", "pass": page.locator(".option-engine-badge").is_visible() and "LibreOffice" in page.locator(".option-engine-badge").inner_text()})
        page.evaluate("window.selectOperation('powerpoint_to_pdf', false)")
        findings.append({"check": "PowerPoint exposes the LibreOffice engine badge", "pass": page.locator(".option-engine-badge").is_visible() and "LibreOffice" in page.locator(".option-engine-badge").inner_text()})
        page.evaluate("window.selectOperation('pdf_to_jpg', false)")
        findings.append({"check": "PDF to JPG exposes DPI choices", "pass": page.locator("#dpi").is_visible() and page.locator("#dpi option").count() == 3})
        page.evaluate("window.selectOperation('pdf_to_pdfa', false)")
        findings.append({"check": "PDF/A exposes conformance choices", "pass": page.locator("#conformance").is_visible() and page.locator("#conformance option").count() == 2})
        page.screenshot(path=str(SCREENSHOT_DIR / "tool-options.png"), full_page=True)

        page.route("**/api/ai/chat", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"answer": "The verified answer is on the cited passage.", "citations": [2, 4], "provider": "Browser fixture", "fallback_used": False})))
        page.route("**/api/ai/summarize", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"status": "success", "summary": "### Executive Summary\n\n- Verified decision\n- Important deadline"})))
        # AI Studio chat: verify the actual user bubble and input in dark mode.
        set_theme("dark")
        page.evaluate("window.switchWorkspaceView('ai', null, false)")
        page.locator("#ai-file-input").set_input_files(str(fixture_path))
        page.locator("#chat-input").fill("What was verified?")
        page.locator("#chat-send-btn").click()
        page.locator("#chat-messages .chat-bubble.user").wait_for(state="visible")
        chat_styles = page.locator("#chat-messages .chat-bubble.user").evaluate(
            "el => { const parse = value => { const m = value.match(/rgba?\\(([^)]+)\\)/); if (!m) return null; const p = m[1].split(',').map(v => parseFloat(v.trim())); return { rgb: p.slice(0, 3), alpha: p.length > 3 ? p[3] : 1 }; }; const lum = rgb => { const s = rgb.map(v => v / 255).map(v => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)); return 0.2126 * s[0] + 0.7152 * s[1] + 0.0722 * s[2]; }; const ratio = (a, b) => { const l1 = lum(a.rgb || a); const l2 = lum(b.rgb || b); return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05); }; const bubble = getComputedStyle(el); const input = getComputedStyle(document.querySelector('#chat-input')); const placeholder = getComputedStyle(document.querySelector('#chat-input'), '::placeholder'); const fg = parse(bubble.color); const bg = parse(bubble.backgroundColor); const inputBg = parse(input.backgroundColor); return { bubbleColor: bubble.color, bubbleBackground: bubble.backgroundColor, bubbleContrast: ratio(fg, bg), inputColor: input.color, inputBackground: input.backgroundColor, inputContrast: ratio(parse(input.color), inputBg), placeholderColor: placeholder.color, placeholderContrast: ratio(parse(placeholder.color), inputBg) }; }"
        )
        findings.append({
            "check": "AI Studio dark-mode chat bubble and input maintain contrast",
            "pass": chat_styles["bubbleColor"] == "rgb(255, 255, 255)" and chat_styles["bubbleContrast"] >= 3 and chat_styles["inputContrast"] >= 4.5 and chat_styles["placeholderContrast"] >= 3,
            "styles": chat_styles,
        })
        page.screenshot(path=str(SCREENSHOT_DIR / "ai-chat-dark.png"), full_page=True)

        # Preserve the existing desk-result smoke check as a separate workflow.
        set_theme("light")
        page.evaluate("window.switchWorkspaceView('desk', null, false)")
        page.evaluate("window.selectOperation('ai_chat', false)")
        page.locator("#file-input").set_input_files(str(fixture_path))
        page.locator("#question").fill("What was verified?")
        page.locator("#run-button").click()
        page.locator("#result-content").wait_for(state="visible")
        chat_result_text = page.locator("#result-content").inner_text()
        findings.append({"check": "AI Chat renders cited answer on-screen", "pass": "Page 2" in chat_result_text and "Open in Full AI Interactive Studio" in chat_result_text})

        page.evaluate("window.selectOperation('summarize', false)")
        page.locator("#file-input").set_input_files(str(fixture_path))
        page.locator("#run-button").click()
        page.locator("#result-content").wait_for(state="visible")
        summary_result_text = page.locator("#result-content").inner_text()
        findings.append({"check": "Summarize renders formatted briefing and actions", "pass": "Executive Summary" in summary_result_text and "Copy Summary" in summary_result_text and "Download PDF" in summary_result_text})
        page.screenshot(path=str(SCREENSHOT_DIR / "ai-results.png"), full_page=True)

        # Modal header/control smoke checks in dark mode.
        set_theme("dark")
        for modal_id in ("forms-modal", "compress-modal", "repair-modal"):
            show_modal(modal_id)
            modal = page.locator(f"#{modal_id}")
            icon = modal.locator(".modal-header-icon")
            close = modal.locator(".modal-close")
            cancel = modal.locator(".btn-cancel").first
            close_styles = close.evaluate("el => { const cs = getComputedStyle(el); const r = el.getBoundingClientRect(); return { width: r.width, height: r.height, cssWidth: cs.width, cssHeight: cs.height, borderRadius: cs.borderRadius, background: cs.backgroundColor, display: cs.display, svgCount: el.querySelectorAll('svg').length }; }")
            cancel_styles = cancel.evaluate("el => { const cs = getComputedStyle(el); return { background: cs.backgroundColor, color: cs.color, border: cs.border, borderRadius: cs.borderRadius, display: cs.display }; }")
            controls = {
                "iconText": icon.inner_text(),
                "svgCount": icon.locator("svg").count(),
                "close": close_styles,
                "cancel": cancel_styles,
            }
            findings.append({
                "check": f"{modal_id} uses SVG header, circular close, and styled cancel controls",
                "pass": icon.inner_text().strip() == "" and icon.locator("svg").count() == 1 and close_styles["cssWidth"] == "32px" and close_styles["cssHeight"] == "32px" and close_styles["svgCount"] == 1 and close_styles["borderRadius"] == "50%" and cancel_styles["display"] == "inline-flex",
                "controls": controls,
            })
            if modal_id == "forms-modal":
                page.screenshot(path=str(SCREENSHOT_DIR / "forms-modal-dark.png"), full_page=True)
            hide_modal(modal_id)

        page.locator("body").evaluate("el => { el.classList.remove('dark-mode'); el.classList.add('light-mode'); }")
        summary = {
            "findings": findings,
            "console_messages": console_messages,
            "page_errors": page_errors,
            "failed_requests": failed_requests,
        }
        (REPORT_DIR / "browser_verification.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        lines = ["# Browser Verification Report", "", f"Base URL: `{BASE_URL}`", "", "## Checks"]
        for finding in findings:
            status = "PASS" if finding["pass"] else "FAIL"
            lines.append(f"- **{status}** — {finding['check']}")
            if "geometry" in finding:
                lines.append(f"  - Geometry: `{finding['geometry']}`; background: `{finding['background']}`")
        lines.extend(["", "## Browser diagnostics", f"- Console warnings/errors: {len(console_messages)}", f"- Page errors: {len(page_errors)}", f"- Failed requests: {len(failed_requests)}"])
        if console_messages:
            lines.append("- Existing console diagnostics:")
            lines.extend(f"  - `{message}`" for message in console_messages)
        lines.append("- `reports/screenshots/ai-chat-dark.png`")
        lines.append("- `reports/screenshots/forms-modal-dark.png`")
        lines.extend(["", "## Screenshots", "- `reports/screenshots/home-light.png`", "- `reports/screenshots/settings-light.png`", "- `reports/screenshots/settings-dark.png`", "- `reports/screenshots/auth-light.png`", "- `reports/screenshots/auth-dark.png`", "- `reports/screenshots/pricing-light.png`", "- `reports/screenshots/pricing-dark.png`", "- `reports/screenshots/compress-light.png`", "- `reports/screenshots/compress-dark.png`", "- `reports/screenshots/tool-options.png`", "- `reports/screenshots/ai-results.png`"])
        lines.extend(["", "## Current-task screenshots", "- `reports/screenshots/ai-chat-dark.png`", "- `reports/screenshots/forms-modal-dark.png`"])
        (REPORT_DIR / "browser_verification.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        browser.close()


if __name__ == "__main__":
    main()
