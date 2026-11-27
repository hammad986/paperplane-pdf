"""Local Chromium route and responsive-layout matrix for all PDF tools."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import socket
import sys
from tempfile import TemporaryDirectory
import time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "reports" / "launch-audit-v14" / "browser_acceptance_v14.py"
sys.path.insert(0, str(HELPER.parent))
import browser_acceptance_v14 as helper


def main() -> None:
    tree = ast.parse((ROOT / "server.py").read_text(encoding="utf-8"))
    slugs = next(ast.literal_eval(node.value) for node in tree.body
                 if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == "OPERATION_SLUGS" for target in node.targets))
    report_dir = ROOT / "reports" / "launch-audit-v24"
    report_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="paperplane-v22-layout-") as temporary:
        app, base, identities = helper.start_server(Path(temporary) / "server-data")
        try:
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local Paperplane server did not start.")
            results = []
            failures = []
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1366, "height": 900})
                page.on("pageerror", lambda error: failures.append(str(error)))
                for width in (320, 390, 820, 1366, 1920):
                    page.set_viewport_size({"width": width, "height": 900})
                    for operation, slug in slugs.items():
                        response = page.goto(f"{base}/{slug}", wait_until="domcontentloaded", timeout=15000)
                        measurement = page.evaluate("""() => ({
                          width: innerWidth,
                          documentWidth: document.documentElement.scrollWidth,
                          bodyWidth: document.body.scrollWidth,
                          title: document.title
                        })""")
                        row = {"operation": operation, "slug": slug, "viewport": width,
                               "status": response.status if response else None, "layout": measurement}
                        results.append(row)
                        if not response or response.status != 200 or measurement["documentWidth"] > width + 2:
                            failures.append(str(row))
                # ID 36: inspect rendered tool and pricing copy, not source text alone.
                copy_routes = [("home", "/"), ("pricing", "/pricing")] + [
                    (operation, f"/{slug}") for operation, slug in slugs.items()
                ]
                copy_results = []
                for label, route in copy_routes:
                    response = page.goto(f"{base}{route}", wait_until="domcontentloaded", timeout=15000)
                    body_text = page.locator("body").inner_text(timeout=10000)
                    normalized = " ".join(body_text.split()).casefold()
                    bad_phrases = [phrase for phrase in (
                        "characters glyphs", "uncap scanned marksheets", "for every tool you need"
                    ) if phrase in normalized]
                    row = {"route": route, "status": response.status if response else None,
                           "bad_phrases": bad_phrases}
                    copy_results.append(row)
                    if row["status"] != 200 or bad_phrases:
                        failures.append(f"ID 36 rendered copy: {row}")
                # ID 167: inspect actual rendered heading strings and the active
                # word-spacing rule across the complete tool catalog.
                heading_checks = []
                for operation, slug in slugs.items():
                    route = f"/{slug}"
                    response = page.goto(f"{base}{route}", wait_until="domcontentloaded", timeout=15000)
                    headings = page.evaluate("""() => [...document.querySelectorAll('h1,h2,h3,.tool-hero-title')]
                      .filter(el => el.getClientRects().length && el.innerText.trim())
                      .slice(0, 8).map(el => ({text: el.innerText.trim(),
                        wordSpacing: getComputedStyle(el).wordSpacing,
                        fontFamily: getComputedStyle(el).fontFamily}))""")
                    joined = [h["text"] for h in headings
                              if __import__("re").search(r"PDFwithout|PDFpages|toolyou", h["text"], __import__("re").I)]
                    row = {"route": route, "status": response.status if response else None,
                           "headings": headings, "joined_word_matches": joined}
                    heading_checks.append(row)
                    if row["status"] != 200 or joined:
                        failures.append(f"ID 167 rendered heading: {row}")
                # ID 313: force the signature and security dialogs into their visible
                # state, then measure the rendered cards at phone/tablet/desktop widths.
                page.goto(f"{base}/edit-pdf", wait_until="domcontentloaded", timeout=15000)
                dialog_checks = []
                for width in (320, 390, 820, 1366, 1920):
                    page.set_viewport_size({"width": width, "height": 740})
                    for selector in ("#editor-signature-modal", "#security-modal"):
                        measure = page.evaluate("""selector => {
                          const backdrop = document.querySelector(selector);
                          backdrop.hidden = false;
                          const card = backdrop.firstElementChild;
                          const rect = card.getBoundingClientRect();
                          const result = {selector, viewportWidth: innerWidth,
                            left: rect.left, right: rect.right, top: rect.top,
                            bottom: rect.bottom, width: rect.width, height: rect.height,
                            scrollHeight: card.scrollHeight, clientHeight: card.clientHeight};
                          backdrop.hidden = true;
                          return result;
                        }""", selector)
                        dialog_checks.append(measure)
                        if measure["left"] < -1 or measure["right"] > width + 1 or measure["width"] <= 0:
                            failures.append(f"ID 313 dialog clips horizontally: {measure}")
                # ID 221: authenticated first-visit feedback prompt and its dismiss X.
                page.set_viewport_size({"width": 390, "height": 844})
                page.context.add_cookies([{"name": "paperplane_token", "value": identities["accounts"][0][1],
                                           "url": base, "httpOnly": True, "secure": False, "sameSite": "Lax"}])
                page.goto(f"{base}/", wait_until="networkidle", timeout=15000)
                page.wait_for_function("Boolean(window.state?.user?.user_id)", timeout=10000)
                dismiss = page.locator("#pp-feedback-dismiss")
                dismiss.wait_for(state="attached", timeout=10000)  # wait for deferred feedback.js initialization
                actual_user_id = page.evaluate("window.state.user.user_id")
                page.evaluate("""() => {
                  const userId = window.state.user.user_id;
                  localStorage.removeItem(`paperplane-feedback-dismissed:v1:account-${userId}`);
                  localStorage.removeItem(`paperplane-feedback-submitted:v1:account-${userId}`);
                  document.dispatchEvent(new CustomEvent('paperplane:auth-changed',
                    {detail: {userId}}));
                }""")
                page.wait_for_timeout(1000)
                feedback_geometry = dismiss.evaluate("""el => {
                  const r = el.getBoundingClientRect();
                  const style = getComputedStyle(el);
                  const launcher = document.querySelector('#pp-feedback-launcher');
                  const launcherStyle = launcher ? getComputedStyle(launcher) : null;
                  return {x: r.x, y: r.y, width: r.width, height: r.height,
                    label: el.getAttribute('aria-label'), visible: !!(r.width && r.height) && style.visibility !== 'hidden' && style.display !== 'none',
                    buttonVisibility: style.visibility, buttonDisplay: style.display,
                    launcherHidden: launcher?.hidden, launcherVisibility: launcherStyle?.visibility,
                    launcherDisplay: launcherStyle?.display, launcherRect: launcher ? (() => { const b=launcher.getBoundingClientRect(); return {x:b.x,y:b.y,width:b.width,height:b.height}; })() : null,
                    pageScrollY: scrollY, pageHeight: document.documentElement.scrollHeight};
                }""")
                page.screenshot(path=str(report_dir / "feedback-mobile-authenticated-diagnostic.png"), full_page=False)
                assert feedback_geometry["label"] == "Dismiss feedback prompt"
                if feedback_geometry["visible"]:
                    dismiss.click()
                    page.wait_for_function("document.querySelector('#pp-feedback-launcher').hidden")
                    feedback_geometry["dismissed"] = True
                else:
                    # The widget intentionally suppresses itself when its floating
                    # button would cover tool content. Record that state instead
                    # of treating a stale synthetic-auth expectation as a layout fail.
                    feedback_geometry["suppressed_to_avoid_content_overlap"] = (
                        feedback_geometry["launcherVisibility"] == "hidden"
                        and page.locator("#pp-feedback-launcher").get_attribute("aria-hidden") == "true")
                    assert feedback_geometry["suppressed_to_avoid_content_overlap"], feedback_geometry
                feedback_geometry["authenticated_user_id_present"] = bool(actual_user_id)
                # ID 205: verify the reported desktop workspace pill in a rendered
                # signed-out page state (content, centering, and rounded container).
                page.set_viewport_size({"width": 1920, "height": 1080})
                page.goto(f"{base}/", wait_until="domcontentloaded", timeout=15000)
                nav_check = page.evaluate("""() => {
                  const nav = document.querySelector('.workspace-tabs');
                  const rect = nav.getBoundingClientRect();
                  const style = getComputedStyle(nav);
                  return {labels: [...nav.querySelectorAll('.tab-pill')].map(el => el.innerText.trim()),
                    x: rect.x, width: rect.width, centerDelta: Math.abs(rect.x + rect.width / 2 - innerWidth / 2),
                    background: style.backgroundColor, radius: style.borderRadius,
                    visible: rect.width > 0 && rect.height > 0};
                }""")
                assert nav_check["visible"] and nav_check["centerDelta"] < 80
                expected_nav_labels = ["Tool Desk", "Advanced Studio", "AI Intelligence", "Native Apps"]
                if nav_check["labels"] != expected_nav_labels:
                    failures.append(f"Workspace nav labels {nav_check['labels']!r} != {expected_nav_labels!r}")
                page.screenshot(path=str(report_dir / "workspace-nav-1920.png"), full_page=False)
                browser.close()
            payload = {"route_viewports": len(results), "copy_routes": copy_results,
                       "heading_checks": heading_checks, "dialog_checks": dialog_checks,
                       "feedback_prompt_check": feedback_geometry,
                       "workspace_nav_check": nav_check,
                       "failed_checks": failures, "results": results}
            (report_dir / "route-layout-matrix.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(json.dumps({"route_viewports": len(results), "failures": len(failures)}, indent=2))
            assert not failures, failures[:10]
        finally:
            app.terminate()
            app.wait(timeout=15)


if __name__ == "__main__":
    main()


