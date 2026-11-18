"""Check AI workspace de-duplication while retaining legacy public routes."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def inspect_site(page, name: str, base: str, evidence: dict) -> None:
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    response = page.goto(f"{base}/tool-desk", wait_until="domcontentloaded", timeout=30000)
    page.locator("#tool-desk-tools-catalog").wait_for(timeout=15000)
    page.wait_for_function("document.querySelector('#tool-desk-tools-catalog')?.innerText?.length > 100", timeout=15000)
    directory = page.evaluate("""() => ({
      title: document.title,
      nav: [...document.querySelectorAll('.tab-pill')].map(x => x.innerText.trim()),
      cards: [...document.querySelectorAll('#tool-desk-tools-catalog .home-tool-card')]
        .map(x => ({title: x.querySelector('.home-tool-title')?.textContent.trim(), href: x.getAttribute('href')})),
      workspaceNote: [...document.querySelectorAll('#tool-desk-tools-catalog a[href="/ai-intelligence"]')]
        .map(x => x.textContent.trim()),
      badge: document.querySelector('#view-tool-desk-directory .tool-category-badge')?.textContent.trim(),
      toolMeta: document.querySelector('#tool-desk-search-meta')?.textContent.trim()
    })""")
    page.locator('#tool-desk-directory-filters [data-desk-category="ai"]').click()
    ai_filter = page.evaluate("""() => [...document.querySelectorAll('#tool-desk-tools-catalog .home-tool-card')]
      .map(x => x.querySelector('.home-tool-title')?.textContent.trim())""")
    page.screenshot(path=str(ROOT / "reports" / "launch-audit-v23" / f"id39-{name}-tool-desk.png"), full_page=True)

    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{base}/tool-desk", wait_until="domcontentloaded", timeout=30000)
    page.locator("#tool-desk-tools-catalog").wait_for(timeout=15000)
    mobile_tool_desk = page.evaluate("""() => ({
      viewport: innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      workspaceNoteInsideViewport: (() => {
        const rect = document.querySelector('.tool-desk-ai-workspace-note')?.getBoundingClientRect();
        return !!rect && rect.left >= 0 && rect.right <= innerWidth;
      })()
    })""")
    page.screenshot(path=str(ROOT / "reports" / "launch-audit-v23" / f"id39-{name}-tool-desk-mobile.png"), full_page=True)

    ai_response = page.goto(f"{base}/ai-intelligence", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector("#chat-form", state="visible", timeout=10000)
    workspace = page.evaluate("""() => ({
      pageTitle: document.title,
      aiViewVisible: !document.querySelector('#view-ai')?.hidden,
      chatFormVisible: !!document.querySelector('#chat-form') && document.querySelector('#chat-form').getClientRects().length > 0,
      summaryVisible: !!document.querySelector('#summary-display') && document.querySelector('#summary-display').getClientRects().length > 0,
      viewport: innerWidth,
      documentWidth: document.documentElement.scrollWidth
    })""")
    page.screenshot(path=str(ROOT / "reports" / "launch-audit-v23" / f"id39-{name}-ai-workspace-mobile.png"), full_page=True)
    legacy_response = page.goto(f"{base}/ai-pdf-chat", wait_until="domcontentloaded", timeout=30000)
    legacy_route = page.evaluate("""() => ({
      toolHeading: document.querySelector('#desk-breadcrumb-label')?.textContent.trim(),
      formAvailable: !!document.querySelector('#job-form')
    })""")
    evidence[name] = {
        "tool_desk_status": response.status if response else None,
        "tool_desk": directory,
        "ai_category_filter_titles": ai_filter,
        "ai_intelligence_status": ai_response.status if ai_response else None,
        "ai_workspace": workspace,
        "mobile_tool_desk": mobile_tool_desk,
        "legacy_ai_chat_status": legacy_response.status if legacy_response else None,
        "legacy_ai_chat_route": legacy_route,
        "page_errors": errors,
    }


def main() -> None:
    evidence: dict = {}
    with TemporaryDirectory(prefix="paperplane-v23-id39-") as temp:
        app, local, _identities = helper.start_server(Path(temp) / "data")
        try:
            port = int(local.rsplit(":", 1)[1])
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local Paperplane test server did not start.")

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                inspect_site(browser.new_page(viewport={"width": 1366, "height": 900}), "local", local, evidence)
                inspect_site(browser.new_page(viewport={"width": 1366, "height": 900}), "live", "https://paperplane.qd.je", evidence)
                browser.close()

            local_cards = {card["title"] for card in evidence["local"]["tool_desk"]["cards"]}
            duplicate_titles = {"AI PDF Chat", "Smart Metadata", "AI Summarize"}
            evidence["result"] = {
                "local_duplicate_cards_removed": not (local_cards & duplicate_titles),
                "local_workspace_link_present": bool(evidence["local"]["tool_desk"]["workspaceNote"]),
                "local_ai_chat_summary_available_in_workspace": (
                    evidence["local"]["ai_workspace"]["chatFormVisible"]
                    and evidence["local"]["ai_workspace"]["summaryVisible"]
                ),
                "local_ai_filter_has_no_duplicate_workflows": not (set(evidence["local"]["ai_category_filter_titles"]) & duplicate_titles),
                "local_legacy_chat_route_preserved": evidence["local"]["legacy_ai_chat_status"] == 200
                    and evidence["local"]["legacy_ai_chat_route"]["formAvailable"],
                "local_mobile_layout_fits": evidence["local"]["mobile_tool_desk"]["documentWidth"] <= evidence["local"]["mobile_tool_desk"]["viewport"]
                    and evidence["local"]["mobile_tool_desk"]["workspaceNoteInsideViewport"]
                    and evidence["local"]["ai_workspace"]["documentWidth"] <= evidence["local"]["ai_workspace"]["viewport"],
                "live_still_has_duplicate_chat_card": "AI PDF Chat" in {
                    card["title"] for card in evidence["live"]["tool_desk"]["cards"]
                },
            }
            evidence["result"]["passed"] = all(value for key, value in evidence["result"].items() if key != "live_still_has_duplicate_chat_card")
            output = ROOT / "reports" / "launch-audit-v23" / "browser-id39-ai-tool-dedup.json"
            output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(json.dumps(evidence, indent=2))
            if not evidence["result"]["passed"]:
                raise SystemExit(1)
        finally:
            app.terminate()
            try:
                app.wait(timeout=8)
            except Exception:
                app.kill()


if __name__ == "__main__":
    main()
