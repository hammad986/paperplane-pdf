"""Verify feedback launcher lifecycle with a synthetic account and local API stub."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/launch-audit-v24/browser-id128-feedback-lifecycle.json"
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main():
    with TemporaryDirectory(prefix="paperplane-id128-") as temp_name:
        app, base, _ = helper.start_server(Path(temp_name) / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.15)
            else:
                raise RuntimeError("Local Paperplane server did not start")

            evidence = {"viewport": {"width": 390, "height": 844}, "page_errors": [], "console_errors": []}
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context(viewport=evidence["viewport"])
                page = context.new_page()
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                page.on("console", lambda message: evidence["console_errors"].append(message.text) if message.type == "error" else None)
                page.goto(base + "/", wait_until="domcontentloaded")
                page.locator("#pp-feedback-launcher").wait_for(state="attached")
                evidence["guest_launcher_hidden"] = page.locator("#pp-feedback-launcher").evaluate("element => element.hidden")
                page.evaluate("document.dispatchEvent(new CustomEvent('paperplane:auth-changed', {detail:{userId:'synthetic-id128-user'}}))")
                page.wait_for_function("document.querySelector('#pp-feedback-launcher')?.hidden === false")
                page.wait_for_timeout(150)
                evidence["first_time_launcher_state"] = page.evaluate("""() => {
                  const launcher = document.querySelector('#pp-feedback-launcher');
                  const button = launcher?.querySelector('#pp-btn-feedback-toggle');
                  const dismiss = launcher?.querySelector('#pp-feedback-dismiss');
                  const container = document.querySelector('#pp-feedback-container');
                  const a = launcher?.getBoundingClientRect();
                  const d = dismiss?.getBoundingClientRect();
                  const colliding = [...document.querySelectorAll('.main-area h1,.main-area h2,.main-area h3,#file-list .file-row-card,.home-tool-title,.home-tool-desc')].filter(element => {
                    const style=getComputedStyle(element), b=element.getBoundingClientRect();
                    return style.display!=='none' && style.visibility!=='hidden' && b.width>0 && b.height>0 && b.bottom>0 && b.top<innerHeight && b.left<a.right && b.right>a.left && b.top<a.bottom && b.bottom>a.top;
                  }).map(element => ({tag:element.tagName,text:(element.innerText||'').slice(0,100),box:(()=>{const b=element.getBoundingClientRect();return {x:b.x,y:b.y,w:b.width,h:b.height}})()}));
                  return {hidden:launcher?.hidden,containerDisplay:container?getComputedStyle(container).display:null,containerVisibility:container?getComputedStyle(container).visibility:null,launcherVisibility:launcher?getComputedStyle(launcher).visibility:null,launcherDisplay:launcher?getComputedStyle(launcher).display:null,buttonVisibility:button?getComputedStyle(button).visibility:null,buttonDisplay:button?getComputedStyle(button).display:null,dismissVisibility:dismiss?getComputedStyle(dismiss).visibility:null,dismissDisplay:dismiss?getComputedStyle(dismiss).display:null,dismissBox:d?{x:d.x,y:d.y,w:d.width,h:d.height}:null,verticalOffset:launcher?getComputedStyle(launcher).getPropertyValue('--pp-feedback-offset-y').trim():null,ariaHidden:launcher?.getAttribute('aria-hidden'),box:a?{x:a.x,y:a.y,w:a.width,h:a.height}:null,colliding};
                }""")
                if not page.locator("#pp-feedback-dismiss").is_visible():
                    evidence["dismiss_control_visible"] = False
                    OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
                    print(json.dumps(evidence, indent=2))
                    raise AssertionError(evidence["first_time_launcher_state"])
                if evidence["first_time_launcher_state"]["buttonVisibility"] == "hidden" or evidence["first_time_launcher_state"]["buttonDisplay"] == "none":
                    raise AssertionError(evidence["first_time_launcher_state"])
                if evidence["first_time_launcher_state"]["colliding"] or evidence["first_time_launcher_state"]["verticalOffset"] == "0px":
                    raise AssertionError("The first-time mobile feedback launcher must move clear of overlapping home content")
                evidence["first_time_account_launcher_visible"] = True
                page.locator("#pp-feedback-dismiss").click()
                evidence["dismissed_hidden"] = page.locator("#pp-feedback-launcher").evaluate("element => element.hidden")
                page.reload(wait_until="domcontentloaded")
                page.evaluate("document.dispatchEvent(new CustomEvent('paperplane:auth-changed', {detail:{userId:'synthetic-id128-user'}}))")
                page.wait_for_timeout(250)
                evidence["dismiss_persists_for_same_account"] = page.locator("#pp-feedback-launcher").evaluate("element => element.hidden")
                context.close()

                submit_context = browser.new_context(viewport=evidence["viewport"])
                submit_page = submit_context.new_page()
                submit_page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                submit_page.on("console", lambda message: evidence["console_errors"].append(message.text) if message.type == "error" else None)
                await_response = {"count": 0}

                def feedback_stub(route):
                    await_response["count"] += 1
                    route.fulfill(status=200, content_type="application/json", body=json.dumps({"status": "ok", "feedback_id": "synthetic-feedback-id128"}))

                submit_page.route("**/api/feedback", feedback_stub)
                submit_page.goto(base + "/", wait_until="domcontentloaded")
                submit_page.wait_for_timeout(300)
                submit_page.evaluate("document.dispatchEvent(new CustomEvent('paperplane:auth-changed', {detail:{userId:'synthetic-id128-submitter'}}))")
                submit_page.wait_for_function("document.querySelector('#pp-feedback-launcher')?.hidden === false")
                submit_page.locator("#pp-btn-feedback-toggle").click()
                submit_page.locator("#pp-fb-text-input").fill("Controlled feedback lifecycle test")
                submit_page.locator("#pp-btn-feedback-submit").click()
                submit_page.wait_for_function("document.querySelector('#pp-feedback-launcher')?.hidden === true")
                evidence["submit_request_count"] = await_response["count"]
                evidence["launcher_hidden_after_submit"] = submit_page.locator("#pp-feedback-launcher").evaluate("element => element.hidden")
                evidence["settings_feedback_entry_exists"] = submit_page.locator("#settings-feedback-open").count() == 1
                submit_page.reload(wait_until="domcontentloaded")
                submit_page.wait_for_timeout(300)
                submit_page.evaluate("document.dispatchEvent(new CustomEvent('paperplane:auth-changed', {detail:{userId:'synthetic-id128-submitter'}}))")
                submit_page.wait_for_timeout(250)
                evidence["submitted_hidden_after_reload"] = submit_page.locator("#pp-feedback-launcher").evaluate("element => element.hidden")
                submit_context.close()
                browser.close()

            required = ["guest_launcher_hidden", "first_time_account_launcher_visible", "dismissed_hidden", "dismiss_persists_for_same_account", "launcher_hidden_after_submit", "settings_feedback_entry_exists", "submitted_hidden_after_reload"]
            evidence["result"] = "passed" if all(evidence.get(key) for key in required) and evidence["submit_request_count"] == 1 and not evidence["page_errors"] and not evidence["console_errors"] else "failed"
            OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(json.dumps(evidence, indent=2))
            if evidence["result"] != "passed":
                raise SystemExit(1)
        finally:
            app.terminate()
            app.wait(timeout=5)


if __name__ == "__main__":
    main()
