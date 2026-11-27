"""Verify v191/v142 upload-limit copy in a Chromium browser against the image."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
import time
from urllib.request import urlopen
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "browser-v191-limit-policy.json"
errors: list[str] = []
for _ in range(60):
    try:
        with urlopen("http://127.0.0.1:8766/api/health", timeout=2) as health:
            if health.status == 200:
                break
    except Exception:
        time.sleep(0.5)
else:
    raise RuntimeError("The local production image did not become healthy")
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1366, "height": 900})
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    response = page.goto("http://127.0.0.1:8766/pdf-to-word", wait_until="networkidle")
    page.locator("#file-hint").wait_for(state="visible")
    page.wait_for_function("document.querySelector('#tool-tier-badge')?.innerText.includes('up to 50 MB')")
    result = page.evaluate("""() => ({
      title: document.title,
      appScript: [...document.scripts].map(s => s.src).find(src => src.includes('/assets/app.js?')),
      serviceWorker: navigator.serviceWorker.controller?.scriptURL || null,
      guestBadge: document.querySelector('#tool-tier-badge')?.innerText || '',
      uploadHint: document.querySelector('#file-hint')?.innerText || '',
      planLimits: JSON.parse(document.querySelector('#paperplane-bootstrap')?.textContent || '{}').planLimits || {},
      horizontalOverflow: document.documentElement.scrollWidth > innerWidth
    })""")
    pricing_response = page.goto("http://127.0.0.1:8766/pricing", wait_until="networkidle")
    page.locator("#pricing-limits-table").wait_for(state="visible", timeout=30_000)
    result["pricing"] = page.evaluate("""() => {
      const section = document.querySelector('#pricing-limits-table');
      return {
        title: section?.querySelector('h3')?.innerText || '',
        rowCount: section?.querySelectorAll('tbody tr').length || 0,
        text: section?.innerText || '',
        horizontalOverflow: document.documentElement.scrollWidth > innerWidth
      };
    }""")
    result["pricingResponsive"] = []
    for width in (320, 390, 820, 1366):
        page.set_viewport_size({"width": width, "height": 900})
        result["pricingResponsive"].append(page.evaluate("""() => {
          const section = document.querySelector('#pricing-limits-table');
          const region = section?.querySelector('.pricing-limits-scroll');
          const rect = section?.getBoundingClientRect();
          return {
            width: innerWidth,
            documentWidth: document.documentElement.scrollWidth,
            sectionRight: rect ? rect.right : null,
            regionClientWidth: region?.clientWidth || 0,
            regionScrollWidth: region?.scrollWidth || 0,
            noPageOverflow: document.documentElement.scrollWidth <= innerWidth,
            sectionWithinViewport: Boolean(rect && rect.left >= 0 && rect.right <= innerWidth + 1),
            tableHasNamedScrollRegion: Boolean(region?.getAttribute('aria-label'))
          };
        }"""))
    browser.close()

report = {
    "image": "pdf_splitter-paperplane:latest",
    "image_id": subprocess.check_output(["docker", "image", "inspect", "pdf_splitter-paperplane:latest", "--format", "{{.Id}}"], text=True).strip(),
    "status": response.status if response else None,
    "observed": result,
    "page_console_errors": errors,
    "checks": {
        "http_200": bool(response and response.status == 200),
        "app_v191": bool(result["appScript"] and "app.js?v=191" in result["appScript"]),
        "guest_50mb": "50 MB/file" in result["guestBadge"],
        "free_and_paid_no_plan_cap_with_500_service_max": "signed-in Free and recurring paid plans have no plan-specific file cap" in result["uploadHint"] and "service max 500 MB" in result["uploadHint"],
        "exam_pass_500mb": "Exam Pass up to 500 MB/file" in result["uploadHint"],
        "bootstrap_limits": result["planLimits"].get("guest_max_file_size_mb") == 50 and result["planLimits"].get("free_max_file_size_mb") == 500 and result["planLimits"].get("exam_pass_max_file_size_mb") == 500,
        "no_horizontal_overflow": not result["horizontalOverflow"],
        "pricing_http_200": bool(pricing_response and pricing_response.status == 200),
        "pricing_has_44_tool_rows": result["pricing"]["rowCount"] == 44,
        "pricing_discloses_all_plan_caps": all(term in result["pricing"]["text"] for term in ("Guest 50 MB", "Free no plan cap", "Exam Pass 500 MB", "paid no plan cap")),
        "pricing_no_horizontal_overflow": not result["pricing"]["horizontalOverflow"],
        "pricing_responsive_320_390_820_1366": all(
            check["noPageOverflow"] and check["sectionWithinViewport"] and check["tableHasNamedScrollRegion"]
            for check in result["pricingResponsive"]
        ),
        "no_page_console_errors": not errors,
    },
}
report["passed"] = all(report["checks"].values())
OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
if not report["passed"]:
    raise SystemExit(1)

