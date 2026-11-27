"""Verify the Studio save-banner and footer behavior across viewport profiles."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "launch-audit-v23"
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

VIEWPORTS = [
    {"width": 320, "height": 740},
    {"width": 390, "height": 844},
    {"width": 683, "height": 900},
    {"width": 820, "height": 900},
    {"width": 901, "height": 760},
    {"width": 1366, "height": 900},
]
rounds: list[dict] = []

with TemporaryDirectory(prefix="paperplane-id45-footer-") as tmp_name:
    tmp = Path(tmp_name)
    fixture = tmp / "id45-studio.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "Studio footer visibility regression fixture")
        pdf.save(fixture)

    app, base, _ = helper.start_server(tmp / "data")
    try:
        for _ in range(120):
            try:
                with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("Local app failed to start")

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for round_no in (1, 2):
                context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
                page = context.new_page()
                errors: list[str] = []
                page.on("pageerror", lambda err: errors.append(str(err)))
                response = page.goto(base + "/studio", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.locator("#studio-file-input").set_input_files(str(fixture))
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent.trim()==='1' && document.querySelector('#studio-loading-overlay')?.hidden===true", timeout=30000)
                for viewport in VIEWPORTS:
                    page.set_viewport_size(viewport)
                    page.wait_for_timeout(250)
                    state = page.evaluate("""() => {
                      const footer = document.querySelector('.app-global-footer');
                      const bannerText = [...document.querySelectorAll('body *')]
                        .filter(el => el.children.length === 0)
                        .map(el => el.textContent.trim())
                        .filter(text => text === 'PDF and page edits save here. Export annotations to keep them.' || text === 'Clear saved work');
                      const primary = document.querySelector('.studio-primary-ribbon');
                      const secondary = document.querySelector('.studio-sub-ribbon');
                      const toolbar = document.querySelector('.studio-toolbar');
                      const toolButtons = [...(toolbar?.querySelectorAll('button') || [])]
                        .filter(button => getComputedStyle(button).display !== 'none' && button.getClientRects().length);
                      return {
                        width: innerWidth, height: innerHeight,
                        documentWidth: document.documentElement.scrollWidth,
                        footerVisibility: footer ? getComputedStyle(footer).visibility : 'missing',
                        footerOpacity: footer ? getComputedStyle(footer).opacity : 'missing',
                        footerRevealed: document.documentElement.classList.contains('footer-revealed'),
                        saveBannerTexts: bannerText,
                        primaryRows: primary ? new Set([...primary.children].map(el => Math.round(el.getBoundingClientRect().top))).size : 0,
                        secondaryRows: secondary ? new Set([...secondary.children].map(el => Math.round(el.getBoundingClientRect().top))).size : 0,
                        toolbarHeight: toolbar?.getBoundingClientRect().height || 0,
                        visibleToolButtons: toolButtons.length,
                        visibleToolButtonRows: new Set(toolButtons.map(button => Math.round(button.getBoundingClientRect().top))).size,
                        primaryRibbon: primary ? {scrollWidth: primary.scrollWidth, clientWidth: primary.clientWidth} : null,
                        secondaryRibbon: secondary ? {scrollWidth: secondary.scrollWidth, clientWidth: secondary.clientWidth} : null
                      };
                    }""")
                    assert state["documentWidth"] <= viewport["width"], state
                    assert state["footerVisibility"] == "hidden" and state["footerOpacity"] == "0" and not state["footerRevealed"], state
                    assert not state["saveBannerTexts"], state
                    if 901 <= viewport["width"] <= 1023:
                        assert state["visibleToolButtonRows"] <= 4, state
                        assert state["secondaryRibbon"]["scrollWidth"] > state["secondaryRibbon"]["clientWidth"], state

                    scrolled = page.evaluate("""() => {
                      const main = document.querySelector('.main-area');
                      if (main) main.scrollTop = main.scrollHeight;
                      window.scrollTo(0, document.documentElement.scrollHeight);
                      if (main) main.dispatchEvent(new Event('scroll', {bubbles:true}));
                      window.dispatchEvent(new Event('scroll'));
                      return {mainTop: main?.scrollTop || 0, windowTop: window.scrollY};
                    }""")
                    page.wait_for_function("document.documentElement.classList.contains('footer-revealed')", timeout=5000)
                    revealed = page.locator(".app-global-footer").evaluate("el=>getComputedStyle(el).visibility")
                    assert revealed == "visible", {"viewport": viewport, "scroll": scrolled, "state": state}
                    rounds.append({"round": round_no, "viewport": viewport, "initial": state,
                                   "scroll": scrolled, "revealed_visibility": revealed})
                    page.evaluate("window.scrollTo(0, 0); const m=document.querySelector('.main-area'); if(m)m.scrollTop=0; window.dispatchEvent(new Event('scroll')); if(m)m.dispatchEvent(new Event('scroll',{bubbles:true}));")
                    page.wait_for_function("!document.documentElement.classList.contains('footer-revealed')", timeout=5000)
                    page.wait_for_timeout(250)

                assert not errors, errors
                context.close()
            browser.close()
    finally:
        app.terminate()
        app.wait(timeout=10)

report = {"view": "Studio", "viewport_profiles": len(VIEWPORTS), "runs_per_profile": 2,
          "checks": rounds, "browser_page_errors": [], "verdict": "PASS"}
(OUT / "browser-id45-footer-visibility-matrix.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
