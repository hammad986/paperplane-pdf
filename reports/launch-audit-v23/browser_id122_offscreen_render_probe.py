import base64
import json
from pathlib import Path
import time

from playwright.sync_api import sync_playwright
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(r"C:\Users\mdham\Downloads\notes.pdf")
OUT = ROOT / "reports" / "launch-audit-v23"
BASE = "http://127.0.0.1:8501"


def main():
    evidence = {"source": str(SOURCE), "sourceBytes": SOURCE.stat().st_size, "rounds": [], "pageErrors": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for round_no in (1, 2):
            context = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3,
                                          is_mobile=True, has_touch=True)
            page = context.new_page()
            page.on("pageerror", lambda error: evidence["pageErrors"].append(str(error)))
            page.goto(BASE + "/robots.txt", wait_until="domcontentloaded")
            page.evaluate("""() => {
              const input=document.createElement('input'); input.type='file'; input.id='probe-file-input';
              input.style.position='fixed'; input.style.left='-10000px'; document.body.append(input);
            }""")
            page.locator("#probe-file-input").set_input_files(str(SOURCE))
            page.wait_for_function("document.querySelector('#probe-file-input').files[0]?.size > 0", timeout=30000)
            cdp = context.new_cdp_session(page)
            cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
            report = page.evaluate("""async () => {
              const file = document.querySelector('#probe-file-input').files[0];
              const input = await file.arrayBuffer();
              const longTasks=[];
              new PerformanceObserver(list=>longTasks.push(...list.getEntries().map(e=>({duration:e.duration,start:e.startTime}))))
                .observe({type:'longtask',buffered:false});
              const started=performance.now();
              const worker = new Worker('/assets/studio_render_worker.js?v=1');
              const result = await new Promise((resolve, reject) => {
                worker.onmessage = event => event.data.error ? reject(new Error(event.data.error)) : resolve(event.data);
                worker.onerror = event => reject(new Error(event.message || 'Worker error'));
                worker.postMessage({bytes: input, pageNumber: 1, scale: 0.86, outputScale: 1.5}, [input]);
              });
              const canvas = document.createElement('canvas');
              canvas.id='offscreen-render-result';
              canvas.width = result.width; canvas.height = result.height;
              canvas.style.width='240px'; canvas.style.height='auto'; document.body.append(canvas);
              const context = canvas.getContext('2d', {alpha:false});
              context.drawImage(result.bitmap, 0, 0);
              result.bitmap.close(); worker.terminate();
              const output = {pages:result.pages, pageNumber:result.pageNumber, width:result.width, height:result.height,
                cssWidth:result.cssWidth, cssHeight:result.cssHeight, renderMilliseconds:result.renderMilliseconds,
                roundTripMilliseconds:Math.round(performance.now()-started),
                documentPages:result.pages, longTasks};
              await new Promise(resolve=>setTimeout(resolve,0));
              output.longTasks=longTasks;
              return output;
            }""")
            report["round"] = round_no
            image_path = OUT / f"id122-offscreen-page1-round{round_no}.png"
            page.locator("#offscreen-render-result").screenshot(path=str(image_path))
            with Image.open(image_path) as image:
                report["nonWhitePixels"] = sum(1 for pixel in image.convert("RGB").getdata()
                                                if min(pixel) < 235)
            evidence["rounds"].append(report)
            context.close()
        browser.close()
    evidence["passed"] = all(
        round_result["pages"] == 69 and round_result["documentPages"] == 69
        and round_result["nonWhitePixels"] > 100 and not round_result["longTasks"]
        for round_result in evidence["rounds"]
    ) and not evidence["pageErrors"]
    (OUT / "browser-id122-offscreen-render-probe.json").write_text(
        json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
