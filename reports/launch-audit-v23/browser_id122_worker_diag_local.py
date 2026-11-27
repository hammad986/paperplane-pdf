import json
from pathlib import Path
import time

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(r"C:\Users\mdham\Downloads\notes.pdf")
OUT = ROOT / "reports" / "launch-audit-v23" / "browser-id122-render-worker-diagnostic.json"
BASE = "http://127.0.0.1:8501"


def main():
    result = {"source": str(SOURCE), "pageErrors": [], "consoleWarningsOrErrors": [], "workerResponses": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3,
                                      is_mobile=True, has_touch=True)
        context.add_init_script("""window.__longTasks=[];new PerformanceObserver(list=>window.__longTasks.push(
          ...list.getEntries().map(entry=>({duration:entry.duration,start:entry.startTime}))))
          .observe({type:'longtask',buffered:true});""")
        page = context.new_page()
        page.on("pageerror", lambda error: result["pageErrors"].append(str(error)))
        page.on("console", lambda message: result["consoleWarningsOrErrors"].append(
            {"type": message.type, "text": message.text[:500]}) if message.type in {"warning", "error"} else None)
        page.on("response", lambda response: result["workerResponses"].append(
            {"url": response.url, "status": response.status}) if "studio_render_worker" in response.url else None)
        cdp = context.new_cdp_session(page)
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
        started = time.perf_counter()
        response = page.goto(BASE + "/studio", wait_until="domcontentloaded", timeout=30000)
        page.locator("#studio-file-input").set_input_files(str(SOURCE))
        page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent.trim()==='69' && document.querySelector('#studio-loading-overlay')?.hidden===true", timeout=90000)
        page.wait_for_function("document.querySelector('.studio-page-sheet[data-page=\"1\"] .pdf-page-canvas')?.dataset.rendered==='true'", timeout=30000)
        result.update({
            "httpStatus": response.status if response else None,
            "appAsset": page.locator('script[src*="app.js"]').get_attribute("src"),
            "renderSessionActive": page.evaluate("!!state.studio.renderSession"),
            "renderWorkerDisabled": page.evaluate("!!state.studio.renderWorkerDisabled"),
            "pageCount": page.locator("#page-total-indicator").inner_text(),
            "firstPageReadySeconds": round(time.perf_counter() - started, 2),
            "longTasks": page.evaluate("window.__longTasks"),
        })
        result["maximumLongTaskMs"] = max((entry["duration"] for entry in result["longTasks"]), default=0)
        browser.close()
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
