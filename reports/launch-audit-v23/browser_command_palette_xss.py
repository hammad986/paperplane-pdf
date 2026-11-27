"""Verify command-palette operation metadata is rendered as inert text in Chromium."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import time
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

marker = "__paperplane_command_palette_xss"
hostile = f'<img src=x onerror="window.{marker}=true">'
operation_key = "evil" + hostile

with TemporaryDirectory(prefix="paperplane-command-palette-xss-") as temporary:
    process, base, _identity = helper.start_server(Path(temporary) / "data")
    try:
        for _ in range(150):
            try:
                with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=.2):
                    break
            except OSError:
                time.sleep(.2)
        else:
            raise RuntimeError("Local app failed to start")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page_errors = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            response = page.goto(base, wait_until="domcontentloaded")
            page.wait_for_function("typeof window.renderCommandResults === 'function' && window.state?.operations")
            result = page.evaluate(
                """({ marker, operationKey, hostile }) => {
                  window[marker] = false;
                  window.state.operations = {
                    [operationKey]: {
                      label: hostile,
                      description: hostile,
                      category: hostile,
                    },
                    merge: { label: hostile, description: hostile, category: 'Organize PDF', prerequisite: hostile,
                      available: false, status: 'DEPENDENCY_MISSING' },
                  };
                  window.renderCommandResults('evil');
                  const palette = document.querySelector('#command-results');
                  const item = palette?.querySelector('.command-item');
                  const paletteSnapshot = {
                    appScript: [...document.scripts].find(script => script.src.includes('/assets/app.js'))?.src,
                    itemCount: palette?.querySelectorAll('.command-item').length ?? -1,
                    injectedImages: palette?.querySelectorAll('img').length ?? -1,
                    markerExecuted: window[marker],
                    key: item?.getAttribute('data-command-operation'),
                    labelText: item?.querySelector('strong')?.textContent,
                    descriptionText: item?.querySelector('small')?.textContent,
                    categoryText: item?.querySelector('.command-item-badge')?.textContent,
                    role: item?.getAttribute('role'),
                    tabindex: item?.getAttribute('tabindex'),
                  };
                  window.renderSidebarTools();
                  const homeCatalog = document.createElement('div');
                  homeCatalog.id = 'home-tools-catalog';
                  document.body.appendChild(homeCatalog);
                  window.renderHomeToolsGrid('organize');
                  const sidebar = document.querySelector('#sidebar-tools-container');
                  const home = document.querySelector('#home-tools-catalog');
                  window.state.operation = 'merge';
                  window.state.files = [{ name: 'test.pdf', size: 100 }];
                  window.updateButton();
                  const runButton = document.querySelector('#run-button');
                  const unavailableButton = {
                    images: runButton?.querySelectorAll('img').length ?? -1,
                    text: runButton?.textContent.trim(),
                  };
                  window.state.operations.merge.available = true;
                  window.state.operations.merge.status = 'READY';
                  window.updateButton();
                  return {
                    ...paletteSnapshot,
                    sidebar: {
                      images: sidebar?.querySelectorAll('img').length ?? -1,
                      buttonText: sidebar?.querySelector('.sidebar-tool-item[data-select-operation="merge"]')?.textContent.trim(),
                      operation: sidebar?.querySelector('.sidebar-tool-item[data-select-operation="merge"]')?.getAttribute('data-select-operation'),
                    },
                    home: {
                      images: home?.querySelectorAll('img').length ?? -1,
                      title: home?.querySelector('.home-tool-title')?.textContent,
                      description: home?.querySelector('.home-tool-desc')?.textContent,
                      badge: home?.querySelector('.home-status-badge')?.textContent,
                    },
                    runButton: {
                      images: runButton?.querySelectorAll('img').length ?? -1,
                      text: runButton?.textContent.trim(),
                    },
                    unavailableButton,
                    pageWidth: document.documentElement.scrollWidth,
                    viewportWidth: innerWidth,
                  };
                }""",
                {"marker": marker, "operationKey": operation_key, "hostile": hostile},
            )
            assert response and response.status == 200
            assert result["appScript"].endswith("/assets/app.js?v=124"), result
            assert result["itemCount"] == 1, result
            assert result["injectedImages"] == 0, result
            assert result["markerExecuted"] is False, result
            assert result["key"] == operation_key, result
            assert result["labelText"] == hostile, result
            assert result["descriptionText"] == hostile, result
            assert result["categoryText"] == hostile, result
            assert result["role"] == "button" and result["tabindex"] == "0", result
            assert result["sidebar"]["images"] == 0 and result["sidebar"]["buttonText"] == hostile, result
            assert result["sidebar"]["operation"] == "merge", result
            assert result["home"]["images"] == 0, result
            assert result["home"]["title"] == hostile and result["home"]["description"] == hostile, result
            assert result["home"]["badge"] == hostile, result
            assert result["runButton"]["images"] == 0, result
            assert result["runButton"]["text"] == f"{hostile} Now →", result
            assert result["unavailableButton"]["images"] == 0, result
            assert result["unavailableButton"]["text"] == f"{hostile} unavailable ✕", result
            assert result["pageWidth"] <= result["viewportWidth"] + 2, result
            assert not page_errors, page_errors
            browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except Exception:
            process.kill()

evidence = {
    "runtime": "local Chromium against isolated current-source server",
    "synthetic_payload_only": True,
    "checks": result,
    "page_errors": page_errors,
}
target = ROOT / "reports" / "launch-audit-v23" / "browser-command-palette-xss.json"
target.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
print(json.dumps(evidence, indent=2))
