from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


OUT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8501"
NOTES = Path(__file__).resolve().parents[2] / "runtime_data_codex_audit" / "notes_69pages_audit.pdf"
TARGETS = (69, 1, 35)


def canvas_state(page, target: int) -> dict:
    return page.evaluate(
        """target => {
          const sheet = document.querySelector(`#studio-page-stack .studio-page-sheet.is-current[data-page='${target}']`);
          const canvas = sheet?.querySelector('canvas');
          const rect = canvas?.getBoundingClientRect();
          const slotRect = sheet?.getBoundingClientRect();
          const loading = sheet?.querySelector('.studio-page-loading');
          let hasInk = false;
          if (canvas?.width && canvas?.height) {
            try {
              const context = canvas.getContext('2d', { willReadFrequently: true });
              const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
              for (let i = 0; i < pixels.length; i += 64) {
                if (pixels[i] < 235 || pixels[i + 1] < 235 || pixels[i + 2] < 235) { hasInk = true; break; }
              }
            } catch { /* the canvas can still be painting while this snapshot is taken */ }
          }
          return {
            currentPage: document.querySelector('#page-jump-input')?.value || null,
            rendered: Boolean(canvas && canvas.width > 0 && canvas.height > 0 && hasInk),
            renderedFlag: canvas?.dataset.rendered || null,
            hasInk,
            canvasWidth: canvas?.width || 0,
            canvasHeight: canvas?.height || 0,
            visibleWidth: rect ? Math.round(rect.width) : 0,
            visibleHeight: rect ? Math.round(rect.height) : 0,
            loadingText: loading && !loading.hidden ? loading.innerText.trim() : null,
            slotTop: slotRect ? Math.round(slotRect.top) : null,
            slotBottom: slotRect ? Math.round(slotRect.bottom) : null,
            slotVisible: Boolean(slotRect && slotRect.bottom > 0 && slotRect.top < innerHeight)
          };
        }""",
        target,
    )


results = []
errors = []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    for run in (1, 2):
        context = browser.new_context(viewport={"width": 375, "height": 812}, is_mobile=True, has_touch=True)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.add_init_script("localStorage.setItem('paperplane_theme', 'dark')")
        page.goto(f"{BASE}/studio", wait_until="domcontentloaded")
        page.locator("#studio-file-input").set_input_files(str(NOTES))
        page.locator("#studio-page-count").wait_for(state="attached")
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline and page.locator("#studio-page-count").inner_text().strip() != "69":
            page.wait_for_timeout(100)
        assert page.locator("#studio-page-count").inner_text().strip() == "69"
        page.locator("#studio-page-stack .studio-page-sheet.is-current canvas[data-rendered=true]").wait_for(timeout=45_000)

        run_results = []
        for target in TARGETS:
            jump = page.locator("#page-jump-input")
            jump.fill(str(target))
            jump.press("Enter")
            started = time.monotonic()
            immediate = canvas_state(page, target)
            page.screenshot(path=str(OUT / f"after-studio-jump-{target}-run-{run}-0s.png"))
            page.wait_for_timeout(1000)
            after_one_second = canvas_state(page, target)
            page.screenshot(path=str(OUT / f"after-studio-jump-{target}-run-{run}-1s.png"))
            page.wait_for_timeout(4000)
            after_five_seconds = canvas_state(page, target)
            page.screenshot(path=str(OUT / f"after-studio-jump-{target}-run-{run}-5s.png"))
            assert immediate["currentPage"] == str(target), {"target": target, "state": immediate}
            assert immediate["slotVisible"], {"target": target, "state": immediate}
            if not immediate["rendered"]:
                assert immediate["loadingText"] == f"Loading page {target}…", {"target": target, "state": immediate}
            assert after_five_seconds["rendered"], {"target": target, "state": after_five_seconds}
            run_results.append({
                "page": target,
                "elapsed_after_go_seconds": round(time.monotonic() - started, 3),
                "at_0s": immediate,
                "at_1s": after_one_second,
                "at_5s": after_five_seconds,
            })
        results.append({"run": run, "pages": run_results})
        context.close()
    browser.close()

report = {"base": BASE, "fixture_pages": 69, "viewport": {"width": 375, "height": 812}, "results": results, "page_errors": errors}
(OUT / "studio-page-jump-probe.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
