"""Check browser-vs-server processing claims on all 44 tool pages."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import socket
import sys
import time
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


def assignment(name: str):
    tree = ast.parse((ROOT / "server.py").read_text(encoding="utf-8"))
    return next(ast.literal_eval(node.value) for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == name for target in node.targets))


operations = assignment("OPERATIONS")
slugs = assignment("OPERATION_SLUGS")
app = (ROOT / "web/assets/app.js").read_text(encoding="utf-8")


def client_set(name: str) -> set[str]:
    match = re.search(rf"const {name} = new Set\(\[(.*?)\]\)", app, re.S)
    if not match:
        raise AssertionError(f"Could not find {name}")
    return set(re.findall(r"'([^']+)'", match.group(1)))


local_operations = client_set("CLIENT_SIDE_SUPPORTED_OPERATIONS")
local_only_photos = client_set("CLIENT_SIDE_IMAGE_OPERATIONS")
assert len(operations) == len(slugs) == 44
assert set(operations) == set(slugs)
assert len(local_operations | local_only_photos) == 25

results: list[dict] = []
errors: list[str] = []
requests: list[str] = []
with TemporaryDirectory(prefix="paperplane-id37-processing-mode-") as temporary:
    app_process, base, _ = helper.start_server(Path(temporary) / "data")
    try:
        for _ in range(150):
            try:
                with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("Local app failed to start")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(viewport={"width": 1366, "height": 900})
            context.add_init_script("try { localStorage.removeItem('paperplane-pdf-processing-mode'); } catch {}")
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: requests.append(request.url)
                    if "/api/jobs" in request.url else None)

            for round_no, viewport in ((1, 1366), (2, 390)):
                page.set_viewport_size({"width": viewport, "height": 900})
                for operation, slug in slugs.items():
                    response = page.goto(f"{base}/{slug}", wait_until="domcontentloaded", timeout=20000)
                    assert response and response.status == 200, {"operation": operation, "status": response.status if response else None}
                    page.wait_for_function("typeof state !== 'undefined' && state.operation", timeout=10000)
                    observed = page.evaluate("""() => {
                      const toggle = document.querySelector('#client-privacy-toggle');
                      const support = document.querySelector('#privacy-mode-support');
                      return {
                        operation: state.operation,
                        localMode: state.clientSideMode,
                        toggleDisabled: toggle?.disabled,
                        toggleChecked: toggle?.checked,
                        support: support?.textContent || '',
                        viewport: innerWidth,
                        documentWidth: document.documentElement.scrollWidth
                      };
                    }""")
                    expected_local = operation in local_operations | local_only_photos
                    expected_disabled = operation not in local_operations
                    assert observed["operation"] == operation, observed
                    assert observed["localMode"] == expected_local, {"expected_local": expected_local, **observed}
                    assert observed["toggleDisabled"] == expected_disabled, {"expected_disabled": expected_disabled, **observed}
                    assert observed["toggleChecked"] == expected_local, observed
                    assert observed["documentWidth"] <= observed["viewport"], observed
                    if expected_local:
                        assert "files stay on this device" in observed["support"], observed
                    else:
                        assert "uploads files for temporary server processing" in observed["support"], observed
                    results.append({"round": round_no, "viewport": viewport, "operation": operation,
                                    "expected_local": expected_local, "mode_matches": True,
                                    "toggle_disabled_matches": True, "no_horizontal_overflow": True,
                                    "http_status": response.status})

            assert not errors, errors
            assert not requests, requests
            context.close()
            browser.close()
    finally:
        app_process.terminate()
        try:
            app_process.wait(timeout=8)
        except Exception:
            app_process.kill()
            app_process.wait(timeout=3)

evidence = {
    "routes": len(slugs), "browser_local_operations": sorted(local_operations | local_only_photos),
    "server_only_operations": sorted(set(operations) - local_operations - local_only_photos),
    "checks": len(results), "zero_job_uploads": not requests, "page_errors": errors,
    "results": results, "result": "PASS",
}
(OUT / "browser-id37-browser-processing-capability.json").write_text(
    json.dumps(evidence, indent=2), encoding="utf-8")
print(json.dumps({key: value for key, value in evidence.items() if key != "results"}, indent=2))
