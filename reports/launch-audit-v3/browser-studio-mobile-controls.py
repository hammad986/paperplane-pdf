from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE = "http://127.0.0.1:8501"
PDF = str(Path("web/assets/sample_document.pdf").resolve())


def ribbon_state(page, selector: str, end_selector: str) -> dict:
    ribbon = page.locator(selector)
    return ribbon.evaluate(
        """(el, endSelector) => {
          const end = document.querySelector(endSelector);
          const rr = el.getBoundingClientRect();
          const er = end?.getBoundingClientRect();
          return {
            clientWidth: el.clientWidth,
            scrollWidth: el.scrollWidth,
            scrollLeft: el.scrollLeft,
            overflowX: getComputedStyle(el).overflowX,
            buttonCount: el.querySelectorAll('button').length,
            lastControlVisible: !!er && er.left >= rr.left - 1 && er.right <= rr.right + 1,
            lastControl: end?.id || null,
            lastControlSize: er ? { width: Math.round(er.width), height: Math.round(er.height) } : null
          };
        }""",
        end_selector,
    )


def swipe_ribbon_left(context, page, selector: str) -> dict:
    ribbon = page.locator(selector)
    ribbon.evaluate("el => { el.scrollLeft = 0; }")
    rect = ribbon.bounding_box()
    assert rect is not None
    start_x = max(3, rect["x"] + rect["width"] - 8)
    end_x = rect["x"] + max(8, rect["width"] * 0.30)
    y = rect["y"] + rect["height"] / 2
    session = context.new_cdp_session(page)
    session.send(
        "Input.dispatchTouchEvent",
        {"type": "touchStart", "touchPoints": [{"id": 0, "x": start_x, "y": y, "radiusX": 4, "radiusY": 4, "force": 1}]},
    )
    for step in range(1, 5):
        x = start_x + (end_x - start_x) * step / 4
        session.send(
            "Input.dispatchTouchEvent",
            {"type": "touchMove", "touchPoints": [{"id": 0, "x": x, "y": y, "radiusX": 4, "radiusY": 4, "force": 1}]},
        )
    session.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    page.wait_for_timeout(250)
    result = ribbon.evaluate("el => ({ scrollLeft: el.scrollLeft, scrollWidth: el.scrollWidth, clientWidth: el.clientWidth })")
    session.detach()
    return result


def main() -> None:
    errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=1,
            is_mobile=True,
            has_touch=True,
        )
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE, wait_until="domcontentloaded", timeout=20_000)
        page.evaluate("switchWorkspaceView('studio')")
        page.locator("#studio-file-input").set_input_files(PDF)
        page.locator("#pdf-canvas[data-rendered='true']").wait_for(timeout=45_000)

        ribbons = [
            (".studio-primary-ribbon", "#clear-canvas-btn"),
            (".studio-sub-ribbon", "#editor-delete-page-btn"),
        ]
        checks = {}
        for selector, end_selector in ribbons:
            page.locator(selector).evaluate("el => { el.scrollLeft = 0; }")
            before = ribbon_state(page, selector, end_selector)
            swipe = swipe_ribbon_left(context, page, selector)
            after_swipe = ribbon_state(page, selector, end_selector)
            page.locator(selector).evaluate("el => { el.scrollLeft = el.scrollWidth; }")
            page.wait_for_timeout(100)
            at_end = ribbon_state(page, selector, end_selector)
            checks[selector] = {"before": before, "after_touch_swipe": after_swipe, "at_end": at_end}

        page.locator("#page-jump-input").fill("1")
        page.locator("#page-jump-input").press("Enter")
        page.wait_for_timeout(350)
        canvas = page.locator("#studio-canvas-area")
        rect = canvas.bounding_box()
        assert rect is not None
        start_x = rect["x"] + rect["width"] / 2
        start_y = rect["y"] + rect["height"] * 0.82
        end_y = rect["y"] + rect["height"] * 0.22
        session = context.new_cdp_session(page)
        session.send(
            "Input.dispatchTouchEvent",
            {"type": "touchStart", "touchPoints": [{"id": 0, "x": start_x, "y": start_y, "radiusX": 5, "radiusY": 5, "force": 1}]},
        )
        for step in range(1, 7):
            y = start_y + (end_y - start_y) * step / 6
            session.send(
                "Input.dispatchTouchEvent",
                {"type": "touchMove", "touchPoints": [{"id": 0, "x": start_x, "y": y, "radiusX": 5, "radiusY": 5, "force": 1}]},
            )
        session.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        page.wait_for_timeout(700)
        scroll_sync = page.evaluate(
            """() => ({
              activePage: document.querySelector('#page-jump-input')?.value,
              activeThumb: document.querySelector('.organizer-thumb-card.active')?.dataset.page,
              canvasScrollTop: Math.round(document.querySelector('#studio-canvas-area')?.scrollTop || 0)
            })"""
        )
        session.detach()

        result = {"viewport": {"width": 390, "height": 844}, "ribbons": checks, "touch_page_scroll_sync": scroll_sync, "page_errors": errors}
        Path("reports/launch-audit-v3/phone-studio-controls.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        assert not errors, result
        for selector, _ in ribbons:
            item = checks[selector]
            assert item["before"]["scrollWidth"] > item["before"]["clientWidth"], (selector, item)
            assert item["after_touch_swipe"]["scrollLeft"] > 0, (selector, item)
            assert item["at_end"]["lastControlVisible"], (selector, item)
        assert int(scroll_sync["activePage"]) > 1, result
        assert scroll_sync["activePage"] == scroll_sync["activeThumb"], result
        page.screenshot(path="reports/launch-audit-v3/phone-studio-controls-reached.png", full_page=True)
        browser.close()


if __name__ == "__main__":
    main()
