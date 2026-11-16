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

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "reports" / "launch-audit-v14" / "browser_acceptance_v14.py"
sys.path.insert(0, str(HELPER.parent))
import browser_acceptance_v14 as helper


def main() -> None:
    tree = ast.parse((ROOT / "server.py").read_text(encoding="utf-8"))
    slugs = next(ast.literal_eval(node.value) for node in tree.body
                 if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == "OPERATION_SLUGS" for target in node.targets))
    report_dir = ROOT / "reports" / "launch-audit-v22"
    report_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="paperplane-v22-layout-") as temporary:
        app, base, _identities = helper.start_server(Path(temporary) / "server-data")
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
                for width in (390, 820, 1366, 1920):
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
                browser.close()
            payload = {"route_viewports": len(results), "failed_checks": failures, "results": results}
            (report_dir / "route-layout-matrix.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(json.dumps({"route_viewports": len(results), "failures": len(failures)}, indent=2))
            assert not failures, failures[:10]
        finally:
            app.terminate()
            app.wait(timeout=15)


if __name__ == "__main__":
    main()
