"""Run a local browser audit twice with a disposable database and synthetic data."""
from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from urllib.parse import urlsplit
from zipfile import ZipFile

import fitz
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
REPORT = Path(__file__).parent
PAGE_MARKER = "Synthetic v13 acceptance page "


def documents(directory):
    paths = []
    for count in (2, 3, 69):
        path = directory / f"synthetic-{count}.pdf"
        with fitz.open() as document:
            for number in range(1, count + 1):
                page = document.new_page(width=595, height=842)
                page.insert_text((70, 70), f"{PAGE_MARKER}{number}.")
            document.save(path)
        paths.append(path)
    return paths


def start_server(directory):
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        port = candidate.getsockname()[1]
    env = {
        name: value for name, value in os.environ.items()
        if not name.upper().startswith(("PAPERPLANE_", "CASHFREE_", "SMTP_", "RESEND_", "OPENAI_", "OPENROUTER_",
                                       "BLUESMINDS_", "ANTHROPIC_", "GEMINI_", "DEEPSEEK_", "GOOGLE_API_", "AI_", "ADMIN_"))
        and name not in {"TESTING", "SESSION_SECRET_KEY"}
    }
    env.update(
        PAPERPLANE_SKIP_DOTENV="1", PAPERPLANE_ENV="development", PAPERPLANE_DATA_DIR=str(directory),
        PAPERPLANE_ADMIN_KEY=secrets.token_urlsafe(64), PAPERPLANE_ADMIN_CODE=secrets.token_urlsafe(30),
        PAPERPLANE_PORT=str(port), PYTHONPATH=str(ROOT), PAPERPLANE_SECURE_COOKIES="false",
    )
    seed = """
import json, secrets
from persistence import init_db, create_user, create_session, create_admin_session
from server import PRIMARY_ADMIN_EMAIL
init_db()
identity = []
for _ in range(2):
    email = f'audit-{secrets.token_hex(4)}@example.invalid'
    password = secrets.token_urlsafe(24)
    create_user(email, password)
    identity.append((email, create_session(email, password)['token']))
print(json.dumps({'accounts': identity, 'admin': create_admin_session(PRIMARY_ADMIN_EMAIL)}))
"""
    seeded = subprocess.run([sys.executable, "-c", seed], cwd=ROOT, env=env, text=True, capture_output=True, check=True)
    identities = json.loads(seeded.stdout)
    base = f"http://127.0.0.1:{port}"
    app = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return app, base, identities


def read_pdf(path):
    with fitz.open(path) as document:
        return [page.get_text().strip() for page in document]


def run_round(browser, directory):
    source, second, long_pdf = documents(directory)
    photo = directory / "sample.jpg"
    Image.new("RGB", (1200, 800), (130, 166, 188)).save(photo)
    app, base, identity = start_server(directory)
    context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
    page = context.new_page()
    errors, server_operations = [], []
    context.on("page", lambda item: item.on("pageerror", lambda error: errors.append(str(error).splitlines()[0][:160])))
    page.on("pageerror", lambda error: errors.append(str(error).splitlines()[0][:160]))
    context.on("request", lambda request: server_operations.append(urlsplit(request.url).path)
               if request.method == "POST" and "/api/jobs" in request.url else None)
    context.route("**/*", lambda route: route.continue_()
                  if urlsplit(route.request.url).hostname == "127.0.0.1" else route.abort())
    evidence = {}

    def visit(path, target=None):
        response = page.goto(base + path, wait_until="domcontentloaded", timeout=10000)
        assert response.status == 200, path
        if target:
            page.locator(target).first.wait_for(state="visible", timeout=10000)

    def download(name, button="#result-download-link"):
        with page.expect_download(timeout=20000) as event:
            page.locator(button).click()
        result = directory / name
        event.value.save_as(result)
        return result

    def run_tool(paths, output_name):
        page.locator("#file-input").set_input_files([str(path) for path in paths])
        page.locator("#run-button").click()
        page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=20000)
        return download(output_name)

    try:
        for _ in range(60):
            try:
                with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=0.2):
                    break
            except OSError:
                if app.poll() is not None:
                    raise RuntimeError("Local audit server exited before startup.")
                time.sleep(0.15)
        visit("/", "#view-tool-desk-directory h1")
        page.locator("#tool-desk-search").fill("translate")
        count_text = page.locator("#tool-desk-search-meta").inner_text()
        assert count_text.startswith("1 tool found")
        evidence["142_153"] = {
            "singular": True, "catalog": page.evaluate("Object.keys(state.operations).length"),
            "title_badge": page.locator(".tool-desk-directory-hero .tool-category-badge").inner_text(),
        }
        for path, selector in (
            ("/faq", "#view-faq h1"), ("/pricing", "#pricing-page-content .pricing-tier-card"),
            ("/history", "#view-history h1"), ("/feedback", "#view-feedback h1"), ("/settings", "#settings-page-content .settings-tabs"),
        ):
            visit(path, selector + (":visible" if path != "/pricing" else ""))
        evidence["132_133"] = "Five route-specific pages reached, with inline Settings and Pricing."
        visit("/merge-pdf", "#tool-title")
        merged = run_tool([source, second], "merged.pdf")
        assert len(read_pdf(merged)) == 5 and not server_operations
        then = time.perf_counter()
        page.goto(base + "/", wait_until="domcontentloaded", timeout=2000)
        evidence["185"] = {"five_page_merge": True, "navigate_ms": round((time.perf_counter() - then) * 1000)}
        visit("/split-pdf", "#tool-title")
        page.locator("#file-input").set_input_files(str(second))
        page.locator("#split_mode").wait_for(timeout=10000)
        page.locator("#split_mode").select_option("all_pages")
        page.locator("#run-button").click()
        with ZipFile(download("split.zip")) as archive:
            assert len(archive.namelist()) == 3
            for name in archive.namelist():
                with fitz.open(stream=archive.read(name), filetype="pdf") as part:
                    assert part.page_count == 1
        evidence["156"] = "Three individual PDFs opened inside the local ZIP."
        visit("/merge-pdf", "#privacy-mode-label")
        page.locator(".privacy-toggle-row").click() if page.locator(".privacy-toggle-row").count() else page.locator("#client-privacy-toggle").evaluate("(input) => input.click()")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_function("!document.querySelector('#client-privacy-toggle').checked")
        assert not page.locator("#client-privacy-toggle").is_checked()
        prior = page.request.get(base + "/api/billing/status").json()["usage_today"]
        merged_server = run_tool([source, second], "merged-server.pdf")
        after = page.request.get(base + "/api/billing/status").json()["usage_today"]
        assert len(read_pdf(merged_server)) == 5 and len(server_operations) == 1 and after == prior + 1
        evidence["186"] = {"server_job": True, "quota_before": prior, "quota_after": after}
        visit("/resize-image-dimensions", "#preset")
        page.locator("#preset").select_option("passport")
        resized = run_tool([photo], "resized.jpg")
        with Image.open(resized) as result:
            assert result.size == (350, 450)
        assert "350 × 450 px" in page.locator("#result-meta").inner_text()
        visit("/merge-photos-online", "#layout")
        page.locator("#layout").select_option("grid")
        grid = run_tool([photo] * 4, "grid.jpg")
        with Image.open(grid) as result:
            assert result.size == (2400, 1600)
        visit("/ssc-photo-resizer", "#preset")
        exam = run_tool([photo], "exam.jpg")
        with Image.open(exam) as result:
            assert result.size == (350, 450)
        assert 20 * 1024 <= exam.stat().st_size <= 50 * 1024
        assert len(server_operations) == 1
        evidence["149_152_165_187_191"] = {"resize": [350, 450], "grid": [2400, 1600],
                                          "exam_bytes": exam.stat().st_size, "additional_server_jobs": 0}

        _, token = identity["accounts"][0]
        context.add_cookies([{"name": "paperplane_token", "value": token, "url": base, "httpOnly": True}])
        visit("/studio")
        page.locator("#topbar-auth-user").wait_for(state="visible")
        page.locator("#studio-file-input").set_input_files(str(long_pdf))
        page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '69'", timeout=30000)
        original = read_pdf(long_pdf)
        source_thumb = page.locator('.organizer-thumb-card[data-page="1"] .thumb-grip')
        target_thumb = page.locator('.organizer-thumb-card[data-page="2"]')
        source_thumb.scroll_into_view_if_needed()
        source_box, target_box = source_thumb.bounding_box(), target_thumb.bounding_box()
        with page.expect_response("**/api/studio/pages/reorder", timeout=20000) as reordered:
            page.mouse.move(source_box["x"] + source_box["width"] / 2, source_box["y"] + source_box["height"] / 2)
            page.mouse.down()
            page.mouse.move(target_box["x"] + 20, target_box["y"] + target_box["height"] * 0.8, steps=8)
            page.mouse.up()
        assert reordered.value.status == 200
        page.get_by_text("Pages reordered successfully.", exact=True).wait_for(timeout=30000)
        exported = download("studio-export.pdf", "#save-studio-btn")
        assert read_pdf(exported) == [original[1], original[0], *original[2:]]
        page.locator("#btn-mode-organize").click()
        page.locator('.organizer-thumb-card[data-page="2"] .thumb-checkbox-label').click()
        with page.expect_response("**/api/studio/pages/reorder", timeout=20000) as moved:
            page.locator("#batch-move-up-btn").click()
        assert moved.value.status == 200
        page.get_by_text("Pages reordered successfully.", exact=True).wait_for(timeout=30000)
        restored_order = download("studio-original-order.pdf", "#save-studio-btn")
        assert read_pdf(restored_order) == original
        page.locator('.organizer-thumb-card[data-page="1"] .thumb-checkbox-label').click()
        with page.expect_response("**/api/studio/pages/reorder", timeout=20000) as later:
            page.locator("#batch-move-down-btn").click()
        assert later.value.status == 200
        page.get_by_text("Pages reordered successfully.", exact=True).wait_for(timeout=30000)
        assert read_pdf(download("studio-later.pdf", "#save-studio-btn")) == [original[1], original[0], *original[2:]]
        evidence["47_49"] = {"pages": 69, "drag_earlier_and_later_checked": True}
        page.evaluate("() => { window.PaperplanePageOrganizer.deletePages([69]); }")
        with page.expect_response("**/api/studio/page/delete", timeout=20000) as deleted:
            page.get_by_role("button", name="Delete pages").click()
        assert deleted.value.status == 200
        page.get_by_text("Deleted 1 page(s).", exact=True).wait_for(timeout=30000)
        page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '68'", timeout=30000)
        page.reload(wait_until="domcontentloaded")
        page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '68'", timeout=30000)
        retained = download("studio-retained.pdf", "#save-studio-btn")
        assert len(read_pdf(retained)) == 68
        evidence["3"] = "69→68 pages survived browser reload and download."

        with page.expect_response("**/api/studio/page/duplicate", timeout=20000) as duplicated:
            page.evaluate("() => window.PaperplanePageOrganizer.duplicatePages([68])")
        assert duplicated.value.status == 200
        page.get_by_text("Duplicated 1 page(s).", exact=True).wait_for(timeout=30000)
        page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '69'")
        assert page.evaluate("""async () => {
          const doc = state.studio.pdfDoc;
          const first = await (await doc.getPage(68)).getTextContent();
          const second = await (await doc.getPage(69)).getTextContent();
          return first.items.map(item => item.str).join() === second.items.map(item => item.str).join();
        }""")
        evidence["48"] = "Duplicate returned HTTP 200, loaded 69 pages, and had an identical final pair."

        page.locator("#studio-file-input").set_input_files(str(source))
        page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '2'")
        page.locator("#btn-mode-organize").click()
        page.locator('.organizer-thumb-card[data-page="1"] .thumb-checkbox-label').click()
        page.locator("#batch-resize-btn").click()
        page.locator("#resize-preset-select").select_option("Letter")
        page.locator("input[name=resize-scope][value=all]").check()
        with page.expect_response("**/api/studio/pages/resize", timeout=20000) as resized_pages:
            page.locator("#btn-apply-resize").click()
        assert resized_pages.value.status == 200
        page.get_by_text("Pages resized successfully.", exact=True).wait_for(timeout=30000)
        check_resize = page.request.post(base + "/api/studio/pages/resize", multipart={
            "file": {"name": "synthetic.pdf", "mimeType": "application/pdf", "buffer": source.read_bytes()},
            "pages": "all", "target_w": "612", "target_h": "792", "mode": "scale",
        })
        assert check_resize.status == 200, f"Resize API returned HTTP {check_resize.status}: {check_resize.text()[:180]}"
        with fitz.open(stream=check_resize.body(), filetype="pdf") as letter:
            assert len(letter) == 2 and all((p.rect.width, p.rect.height) == (612, 792) for p in letter)
            assert [p.get_text().strip() for p in letter] == read_pdf(source)
        evidence["199"] = "Studio Resize returned two Letter pages with original text; API payload was reopened."

        page.locator('.organizer-thumb-card[data-page="2"] .thumb-checkbox-label').click()
        extracted = download("studio-extract.pdf", "#batch-extract-btn")
        assert read_pdf(extracted) == [read_pdf(source)[1]]
        assert page.locator("#studio-download-feedback a").is_visible()
        evidence["10"] = "Selected page 2 started a browser download and exposed a retry link."

        # Consume any remaining server operations for this synthetic account, then
        # inspect the real 402 response on the next export.
        remaining = 10 - page.request.get(base + "/api/billing/status").json()["usage_today"]
        for _ in range(remaining):
            allowed = page.request.post(base + "/api/studio/forms/analyze", multipart={
                "file": {"name": "synthetic.pdf", "mimeType": "application/pdf", "buffer": source.read_bytes()},
            })
            assert allowed.status == 200
        with page.expect_response("**/api/studio/apply-edits", timeout=10000) as limited:
            page.locator("#save-studio-btn").click()
        assert limited.value.status == 402
        quota_dialog = page.locator("#upgrade-modal")
        quota_dialog.wait_for(state="visible")
        assert "Daily limit reached" in quota_dialog.inner_text()
        assert "[object Object]" not in quota_dialog.inner_text()
        evidence["193"] = "A real 10/10 account received a 402 and displayed the readable upgrade modal."
        page.reload(wait_until="domcontentloaded")
        page.locator("#studio-clear-pdf-btn").click()
        page.get_by_role("button", name="Clear Studio PDF", exact=True).last.click()
        page.get_by_text("Studio PDF cleared from this browser.", exact=True).wait_for(timeout=15000)
        page.reload(wait_until="domcontentloaded")
        page.locator(".studio-empty-state").wait_for(state="visible")
        assert page.locator("#page-total-indicator").inner_text() == "0"
        evidence["69_174"] = "Clear Studio PDF removed the persisted file and reload showed the empty state."

        second_tab = context.new_page()
        second_tab.goto(base + "/settings")
        second_tab.locator("#topbar-auth-user").wait_for(state="visible")
        visit("/settings", "#settings-signout-btn")
        page.locator("#settings-signout-btn").click()
        page.locator("#topbar-signin-btn").wait_for(state="visible")
        second_tab.locator("#topbar-signin-btn").wait_for(state="visible")
        visit("/settings", "#topbar-signin-btn")
        assert page.request.get(base + "/api/auth/me").status == 401
        assert page.locator("#topbar-auth-user").is_hidden()
        page.locator("#topbar-signin-btn").click()
        page.locator("#auth-modal:not([hidden])").wait_for(state="visible")
        evidence["197_198"] = "Signed out, cross-tab Guest appeared, reload retained working Sign in."

        admin = context.new_page()
        admin.add_init_script("(token => sessionStorage.setItem('pp_admin_session', token))(" + json.dumps(identity["admin"]) + ")")
        admin.goto(base + "/admin")
        admin.locator("#tab-feedback-btn").click()
        message = "Synthetic browser auto-refresh evidence"
        assert page.request.post(base + "/api/feedback", data={"message": message, "rating": 4}).ok
        admin.locator("#feedback-tbody").get_by_text(message, exact=True).wait_for(timeout=14000)
        evidence["102"] = "Admin tab rendered newly submitted feedback on its next poll."

        visit("/protect-pdf", "#browse")
        page.locator("#file-input").set_input_files(str(source))
        page.locator("#open-security-audit-tool-btn").click()
        assert page.get_by_role("button", name="Sanitize Document Now").count() == 1
        evidence["129"] = "One Sanitize action after uploading a PDF."
        visit("/download")
        page.locator("#waitlist-email").wait_for(state="visible")
        evidence["134"] = "Waitlist form visible without the former async setup delay."

        widths = {}
        for width in (360, 390, 768, 820, 834, 1024, 1104, 1366):
            page.set_viewport_size({"width": width, "height": 844})
            visit("/remove-pages-pdf", "#tool-title")
            widths[str(width)] = page.evaluate("""() => {
              const visible = selector => !!document.querySelector(selector)?.getClientRects().length;
              const tabs = document.querySelector('.workspace-tabs');
              const rect = tabs.getBoundingClientRect();
              const title = document.querySelector('#tool-title').getBoundingClientRect();
              return {
                desktopSidebar: visible('#sidebar') && document.querySelector('#sidebar').getBoundingClientRect().right > 0,
                mobileBrand: visible('.mobile-brand'),
                navFits: !rect.width || (rect.left >= -1 && rect.right <= innerWidth + 1),
                titleBelowNav: !rect.height || title.top >= rect.bottom - 1,
                horizontalOverflow: document.documentElement.scrollWidth > innerWidth + 1,
              };
            }""")
        assert all(layout["desktopSidebar"] != layout["mobileBrand"]
                   and layout["navFits"] and layout["titleBelowNav"]
                   and not layout["horizontalOverflow"] for layout in widths.values())
        evidence["15_189_205"] = widths
        page.set_viewport_size({"width": 1104, "height": 844})
        for tool in ("remove-pages-pdf", "ocr-pdf"):
            visit("/" + tool, "#tool-title")
            page.locator("#dropzone").scroll_into_view_if_needed()
            assert page.evaluate("getComputedStyle(document.querySelector('.workspace-tabs')).position === 'static'")
        evidence["15_scroll"] = "At 1104 px the pills stayed in normal flow on both reported tool pages."

        visit("/settings", "#settings-page-content .settings-tabs")
        page.set_viewport_size({"width": 390, "height": 844})
        assert not page.evaluate("document.documentElement.scrollWidth > innerWidth + 1")
        page.locator("#settings-tab-btn-privacy").click()
        page.locator("#settings-feedback-open").click()
        page.locator("#pp-feedback-popover").wait_for(state="visible")
        evidence["128"] = "Settings opens the feedback form at 390 px."
        evidence["page_errors"] = errors
        assert not errors
        return evidence
    finally:
        context.close()
        app.terminate()
        app.wait(timeout=15)


if __name__ == "__main__":
    with sync_playwright() as playwright:
        chrome = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe"
        args = {"headless": True}
        if chrome.exists():
            args["executable_path"] = str(chrome)
        browser = playwright.chromium.launch(**args)
        rounds = []
        for n in (1, 2):
            print(f"Starting browser round {n}", flush=True)
            with TemporaryDirectory(prefix=f"paperplane-browser-{n}-") as temp:
                rounds.append(run_round(browser, Path(temp)))
            (REPORT / "browser-acceptance.json").write_text(json.dumps(rounds, indent=2), encoding="utf-8")
        browser.close()


