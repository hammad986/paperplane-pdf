"""Verify the self-found Studio toast fix in the current production image."""
from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent
BASE = os.environ.get("PAPERPLANE_AUDIT_BASE", "http://127.0.0.1:18515")
results = []

with TemporaryDirectory(prefix="paperplane-docker-toast-v146-") as temporary:
    temp = Path(temporary)
    files: dict[str, Path] = {}
    for name, size in (("portrait", (612, 792)), ("landscape", (792, 612))):
        path = temp / f"{name}.pdf"
        with fitz.open() as document:
            page = document.new_page(width=size[0], height=size[1])
            page.insert_text((48, 80), f"Current image toast geometry: {name}")
            document.save(path)
        files[name] = path

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        for round_number in (1, 2):
            for width, height in ((390, 844), (320, 740)):
                for orientation in ("portrait", "landscape"):
                    context = browser.new_context(viewport={"width": width, "height": height},
                                                  is_mobile=True, has_touch=True)
                    page = context.new_page()
                    errors: list[str] = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    response = page.goto(BASE + "/studio", wait_until="domcontentloaded", timeout=30000)
                    assert response and response.status == 200
                    page.locator("#studio-file-input").set_input_files(str(files[orientation]))
                    page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered === 'true'", timeout=30000)
                    page.wait_for_selector(".toast-notice[role='status']", timeout=5000)
                    page.wait_for_timeout(150)
                    measured = page.evaluate("""() => {
                      const rect=s=>{const e=document.querySelector(s);if(!e)return null;const r=e.getBoundingClientRect();return {top:r.top,bottom:r.bottom,width:r.width,height:r.height}};
                      const toast=document.querySelector('.toast-notice');
                      return {toast:rect('.toast-notice'),sheet:rect('.studio-page-sheet'),dock:rect('#studio-mobile-dock'),
                        hidden:toast.classList.contains('toast-visually-hidden'),role:toast.getAttribute('role'),
                        live:toast.getAttribute('aria-live'),text:toast.innerText};
                    }""")
                    toast, sheet, dock = measured["toast"], measured["sheet"], measured["dock"]
                    if orientation == "portrait":
                        assert measured["hidden"] and toast["width"] <= 1 and toast["height"] <= 1, measured
                    else:
                        assert not measured["hidden"], measured
                        assert toast["top"] >= sheet["bottom"] + 7, measured
                        assert toast["bottom"] <= dock["top"] - 7, measured
                    assert measured["role"] == "status" and measured["live"] == "polite", measured
                    assert not errors, errors
                    page.screenshot(path=str(OUT / f"self-found-studio-toast-docker-v146-{width}-{orientation}-round{round_number}.png"), full_page=True)
                    page.evaluate("showToast('Docker controlled error announcement', 'error', 1000)")
                    page.wait_for_timeout(120)
                    error_state = page.evaluate("""() => {
                      const rect=s=>{const e=document.querySelector(s);const r=e.getBoundingClientRect();return {top:r.top,bottom:r.bottom,width:r.width,height:r.height}};
                      const toast=document.querySelector('.toast-notice');return {toast:rect('.toast-notice'),sheet:rect('.studio-page-sheet'),dock:rect('#studio-mobile-dock'),
                        hidden:toast.classList.contains('toast-visually-hidden'),role:toast.getAttribute('role'),live:toast.getAttribute('aria-live')};
                    }""")
                    available = error_state["dock"]["top"] - error_state["sheet"]["bottom"]
                    if available < error_state["toast"]["height"] + 20:
                        assert error_state["hidden"] and error_state["toast"]["width"] <= 1, error_state
                    else:
                        assert not error_state["hidden"], error_state
                        assert error_state["toast"]["top"] >= error_state["sheet"]["bottom"] + 7, error_state
                        assert error_state["toast"]["bottom"] <= error_state["dock"]["top"] - 7, error_state
                    assert error_state["role"] == "alert" and error_state["live"] == "assertive", error_state
                    assert not errors, errors
                    results.append({"round": round_number, "viewport": [width, height], "orientation": orientation,
                                    **measured, "error_layout": error_state, "page_errors": errors})
                    context.close()
        browser.close()

evidence = {"base": BASE, "image": "paperplane-v23-audit:codex-v146", "rounds": results}
(OUT / "browser-self-found-studio-toast-docker-v146.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
print(json.dumps({"checks": len(results), "page_errors": sum(len(row["page_errors"]) for row in results),
                  "evidence": "browser-self-found-studio-toast-docker-v146.json"}, indent=2))
