"""Run the hostile operation-catalog DOM test against the v124 production image."""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:18502"
MARKER = "__paperplane_docker_command_xss"
HOSTILE = f'<img src=x onerror="window.{MARKER}=true">'
KEY = "evil" + HOSTILE
errors: list[str] = []
rounds = []

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel="chrome", headless=True)
    for viewport_width in (320, 390, 820, 1366):
        page = browser.new_page(viewport={"width": viewport_width, "height": 844})
        page.on("pageerror", lambda error: errors.append(str(error)))
        response = page.goto(BASE, wait_until="domcontentloaded", timeout=30000)
        assert response and response.status == 200
        page.wait_for_function("typeof window.renderCommandResults === 'function' && typeof window.updateButton === 'function' && window.state?.operations")
        result = page.evaluate(
            """({ marker, key, hostile }) => {
              window[marker] = false;
              window.state.operations = {
                [key]: { label: hostile, description: hostile, category: hostile },
                merge: { label: hostile, description: hostile, prerequisite: hostile,
                  available: false, status: 'DEPENDENCY_MISSING' },
              };
              window.renderCommandResults('evil');
              const palette = document.querySelector('#command-results');
              window.renderSidebarTools();
              const home = document.createElement('div'); home.id='home-tools-catalog'; document.body.append(home);
              window.renderHomeToolsGrid('organize');
              window.state.operation='merge'; window.state.files=[{name:'safe.pdf',size:10}];
              window.updateButton();
              const button=document.querySelector('#run-button');
              const unavailable=button?.textContent.trim();
              const unavailableImages=button?.querySelectorAll('img').length ?? -1;
              window.state.operations.merge.available=true; window.state.operations.merge.status='READY';
              window.updateButton();
              return {
                script:[...document.scripts].find(s=>s.src.includes('/assets/app.js'))?.getAttribute('src'),
                marker:window[marker],
                paletteImages:palette?.querySelectorAll('img').length ?? -1,
                sidebarImages:document.querySelector('#sidebar-tools-container')?.querySelectorAll('img').length ?? -1,
                homeImages:home.querySelectorAll('img').length,
                label:home.querySelector('.home-tool-title')?.textContent,
                description:home.querySelector('.home-tool-desc')?.textContent,
                prerequisite:home.querySelector('.home-status-badge')?.textContent,
                unavailable, unavailableImages,
                ready:button?.textContent.trim(), readyImages:button?.querySelectorAll('img').length ?? -1,
                documentWidth:document.documentElement.scrollWidth, bodyWidth:document.body.scrollWidth,
                viewportWidth:innerWidth,
              };
            }""",
            {"marker": MARKER, "key": KEY, "hostile": HOSTILE},
        )
        assert result["script"] == "/assets/app.js?v=124", result
        assert result["marker"] is False, result
        assert all(result[name] == 0 for name in ("paletteImages", "sidebarImages", "homeImages", "unavailableImages", "readyImages")), result
        assert result["label"] == result["description"] == result["prerequisite"] == HOSTILE, result
        assert result["unavailable"] == f"{HOSTILE} unavailable ✕", result
        assert result["ready"] == f"{HOSTILE} Now →", result
        assert result["documentWidth"] <= viewport_width + 2 and result["bodyWidth"] <= viewport_width + 2, result
        rounds.append(result)
        page.close()
    browser.close()

assert not errors, errors
evidence = {
    "runtime": "production-mode Docker image paperplane-v23-audit:codex-v124",
    "image_id": "sha256:a5df4a859eed7a2969ef601a43cb783169eadde1d33b41e322406070022d2fde",
    "synthetic_payload_only": True,
    "responsive_checks": rounds,
    "page_errors": errors,
}
out = ROOT / "reports" / "launch-audit-v23" / "browser-command-palette-xss-docker-v124.json"
out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
print(json.dumps(evidence, indent=2))
