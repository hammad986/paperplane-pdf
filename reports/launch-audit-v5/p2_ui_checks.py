from __future__ import annotations

import json
import time
from pathlib import Path

import fitz
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8501"


def make_fillable_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page()
    labels = ["Applicant name", "Contact email", "Program title", "Statement"]
    for index, (name, label) in enumerate(zip(("ApplicantName", "ContactEmail", "ProgramTitle", "Statement"), labels)):
        y = 60 + index * 95
        page.insert_text((60, y), label, fontsize=11)
        widget = fitz.Widget()
        widget.field_name = name
        widget.field_label = label
        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        widget.rect = fitz.Rect(60, y + 8, 535, y + 45 if name != "Statement" else y + 75)
        widget.text_fontsize = 10
        if name == "Statement":
            widget.field_flags = fitz.PDF_TX_FIELD_IS_MULTILINE
        page.add_widget(widget)
    document.save(path)
    document.close()


def main() -> None:
    form_pdf = OUT / "p2-long-form-source.pdf"
    make_fillable_pdf(form_pdf)
    test_values = {
        "ApplicantName": "Alexandra Elizabeth Montgomery-Smith",
        "ContactEmail": "alexandra.montgomery.smith@example-research-institute.org",
        "ProgramTitle": "A longitudinal study of low-resource document workflows, multilingual accessibility, and robust community-led digital infrastructure",
        "Statement": "This extended statement checks that long JSON values remain readable while editing on a narrow mobile screen. " * 8,
    }
    payload = json.dumps(test_values, ensure_ascii=False)
    results: dict[str, object] = {"compress_preset": [], "fill_form": [], "json_chars": len(payload)}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for width in (1366, 375):
            page = browser.new_page(
                viewport={"width": width, "height": 900 if width > 900 else 812},
                is_mobile=width < 600,
                has_touch=width < 600,
                accept_downloads=True,
            )
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)

            page.goto(f"{BASE}/compress-pdf", wait_until="domcontentloaded")
            page.locator("#preset").wait_for(timeout=15000)
            preset = page.evaluate(
                """() => {
                  const select=document.querySelector('#preset');
                  const box=select.getBoundingClientRect();
                  return {value:select.value, selectedText:select.selectedOptions[0]?.textContent.trim(), label:select.labels?.[0]?.textContent.trim(), width:box.width, height:box.height, right:box.right, viewport:innerWidth, documentOverflow:document.documentElement.scrollWidth>document.documentElement.clientWidth};
                }"""
            )
            page.locator("#options").scroll_into_view_if_needed()
            page.screenshot(path=str(OUT / f"compress-preset-{width}-after.png"), full_page=True)
            results["compress_preset"].append({"viewport": width, **preset, "screenshot": str(OUT / f"compress-preset-{width}-after.png")})

            page.goto(f"{BASE}/fill-pdf-form", wait_until="domcontentloaded")
            page.locator("#fields").wait_for(timeout=15000)
            page.locator("#file-input").set_input_files(str(form_pdf))
            baseline = page.evaluate(
                """payload => {
                  const current=document.querySelector('#fields');
                  const legacy=document.createElement('input');
                  legacy.id='fields'; legacy.type='text'; legacy.placeholder='{"Name":"Alex", "Email":"alex@example.com", "City":"Pune"}';
                  window.__p2OriginalTextarea=current;
                  current.replaceWith(legacy); legacy.value=payload;
                  const rect=legacy.getBoundingClientRect();
                  return {tag:legacy.tagName,width:rect.width,height:rect.height,clientWidth:legacy.clientWidth,scrollWidth:legacy.scrollWidth,valueLength:legacy.value.length};
                }""",
                payload,
            )
            baseline_screenshot = OUT / f"p2-fill-form-{width}-before.png"
            page.screenshot(path=str(baseline_screenshot), full_page=True)
            page.evaluate(
                """payload => {
                  const legacy=document.querySelector('#fields');
                  const textarea=window.__p2OriginalTextarea;
                  delete window.__p2OriginalTextarea;
                  legacy.replaceWith(textarea);
                  textarea.value=payload; textarea.dispatchEvent(new Event('input',{bubbles:true}));
                }""",
                payload,
            )
            page.locator("#options").scroll_into_view_if_needed()
            page.wait_for_timeout(250)
            layout = page.evaluate(
                """() => {
                  const field=document.querySelector('#fields');
                  const rect=field.getBoundingClientRect();
                  return {tag:field.tagName, width:rect.width, height:rect.height, clientWidth:field.clientWidth, scrollWidth:field.scrollWidth, clientHeight:field.clientHeight, scrollHeight:field.scrollHeight, right:rect.right, viewport:innerWidth, documentWidth:document.documentElement.scrollWidth, documentOverflow:document.documentElement.scrollWidth>document.documentElement.clientWidth, valueLength:field.value.length};
                }"""
            )
            after_screenshot = OUT / f"p2-fill-form-{width}-after.png"
            page.screenshot(path=str(after_screenshot), full_page=True)
            page.locator("#run-button").click()
            page.locator("#result-download-link").wait_for(state="visible", timeout=90000)
            output_path = OUT / f"p2-fill-form-{width}-after.pdf"
            with page.expect_download(timeout=45000) as download_event:
                page.locator("#result-download-link").click()
            download = download_event.value
            download.save_as(str(output_path))
            output = fitz.open(output_path)
            output_values = {}
            for output_page in output:
                for widget in output_page.widgets() or []:
                    output_values[widget.field_name] = widget.field_value
            output.close()
            results["fill_form"].append({
                "viewport": width,
                "textarea_layout": layout,
                "output_filename": download.suggested_filename,
                "output_bytes": output_path.stat().st_size,
                "output_page_count": len(fitz.open(output_path)),
                "output_widget_values_match": output_values == test_values,
                "output_widget_names": sorted(output_values),
                "output_statement_chars": len(output_values.get("Statement", "")),
                "browser_errors": errors,
                "legacy_input_metrics": baseline,
                "before_screenshot": str(baseline_screenshot),
                "after_screenshot": str(after_screenshot),
                "output_pdf": str(output_path),
            })
            page.close()
        browser.close()

    target = OUT / "p2-ui-checks.json"
    target.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"report": str(target), **results}, indent=2, ensure_ascii=False))
    expected_viewports = {1366, 375}
    if {item["viewport"] for item in results["fill_form"]} != expected_viewports:
        raise SystemExit("Missing desktop or mobile fill-form run")
    if any(not item["output_widget_values_match"] or item["browser_errors"] for item in results["fill_form"]):
        raise SystemExit("Fill Form output values or browser checks failed")
    if any(item["selectedText"] != "🎯 Under 100 KB (Govt / SSC Exam Form)" for item in results["compress_preset"]):
        raise SystemExit("Compress default preset label did not match owner-approved value")


if __name__ == "__main__":
    main()
