"""Verify ID45's compact mid-size Studio ribbons in the production image."""
from __future__ import annotations

import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("PAPERPLANE_AUDIT_BASE", "http://127.0.0.1:18515")
IMAGE = os.environ.get("PAPERPLANE_TEST_IMAGE_TAG", "paperplane-v23-audit:codex-current")
results = []
errors: list[str] = []

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    for round_no in (1, 2):
        context = browser.new_context(viewport={"width": 901, "height": 760})
        page = context.new_page()
        page.on("pageerror", lambda err: errors.append(str(err)))
        response = page.goto(BASE + "/studio", wait_until="domcontentloaded", timeout=30000)
        assert response and response.status == 200
        assert page.locator("link[rel='stylesheet'][href='/assets/styles.css?v=61']").count() == 1
        metrics = page.evaluate("""() => {
          const toolbar=document.querySelector('.studio-toolbar');
          const primary=document.querySelector('.studio-primary-ribbon');
          const secondary=document.querySelector('.studio-sub-ribbon');
          const buttons=[...(toolbar?.querySelectorAll('button')||[])].filter(b=>getComputedStyle(b).display!=='none'&&b.getClientRects().length);
          return {
            viewport:innerWidth, documentWidth:document.documentElement.scrollWidth,
            rows:new Set(buttons.map(b=>Math.round(b.getBoundingClientRect().top))).size,
            buttonCount:buttons.length,
            toolbarHeight:toolbar?.getBoundingClientRect().height||0,
            primaryScroll:[primary?.scrollWidth||0,primary?.clientWidth||0],
            secondaryScroll:[secondary?.scrollWidth||0,secondary?.clientWidth||0],
            footerVisibility:getComputedStyle(document.querySelector('.app-global-footer')).visibility
          };
        }""")
        assert metrics["documentWidth"] == 901 and metrics["rows"] <= 4, metrics
        assert metrics["primaryScroll"][0] > metrics["primaryScroll"][1], metrics
        assert metrics["secondaryScroll"][0] > metrics["secondaryScroll"][1], metrics
        assert metrics["footerVisibility"] == "hidden", metrics
        results.append({"round": round_no, "metrics": metrics})
        context.close()
    browser.close()

assert not errors, errors
image_id = __import__("subprocess").check_output(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"], text=True).strip()
report = {"image": IMAGE, "image_id": image_id, "rounds": results, "page_errors": errors, "verdict": "PASS"}
Path(__file__).resolve().parent.joinpath("browser-id45-docker-v147-toolbar.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))

