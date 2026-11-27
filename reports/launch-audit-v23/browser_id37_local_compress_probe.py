import json
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(r"C:\Users\mdham\Downloads\notes.pdf")
OUT = ROOT / "reports" / "launch-audit-v23" / "browser-id37-local-compress-probe.json"
URL = "http://127.0.0.1:8501/"


def main():
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.add_init_script("document.addEventListener('change', e => { if (e.target?.id === 'file-input' && e.target.files?.[0]) window.__probeFile = e.target.files[0]; }, true)")
        page.goto(URL, wait_until="domcontentloaded")
        page.locator("#file-input").set_input_files(str(SOURCE))
        page.wait_for_function("window.PaperplanePdfRuntime && window.__probeFile")
        for round_no in range(1, 3):
            result = page.evaluate("""async () => {
              const file = window.__probeFile;
              const source = new Uint8Array(await file.arrayBuffer());
              const { PDFDocument } = await window.PaperplanePdfRuntime.ensurePdfLib();
              const started = performance.now();
              const doc = await PDFDocument.load(source);
              const pages = doc.getPageCount();
              const output = await doc.save({ useObjectStreams: true });
              const inputByteLength = source.byteLength;
              const outputByteLength = output.byteLength;
              const elapsedMs = performance.now() - started;
              const pdfjs = await window.PaperplanePdfRuntime.ensurePdfJs();
              async function inspect(bytes) {
                const task = pdfjs.getDocument({ data: bytes, isEvalSupported: false });
                const pdf = await task.promise;
                let text = '';
                for (let i = 1; i <= pdf.numPages; i++) {
                  const page = await pdf.getPage(i);
                  const content = await page.getTextContent();
                  text += content.items.map(item => item.str).join(' ');
                }
                const pageCount = pdf.numPages;
                await task.destroy();
                return { pageCount, text };
              }
              const original = await inspect(source);
              const rewritten = await inspect(output);
              return {
                inputBytes: inputByteLength,
                outputBytes: outputByteLength,
                reductionPercent: Number((100 * (1 - outputByteLength / inputByteLength)).toFixed(3)),
                pages: { input: original.pageCount, output: rewritten.pageCount },
                textChars: { input: original.text.length, output: rewritten.text.length },
                exactTextMatch: original.text === rewritten.text,
                elapsedMs: Math.round(elapsedMs),
              };
            }""")
            result["round"] = round_no
            results.append(result)
        browser.close()
    evidence = {
        "source": str(SOURCE),
        "sourceBytes": SOURCE.stat().st_size,
        "rounds": results,
        "pageErrors": page_errors,
        "note": "Browser-only pdf-lib load/save feasibility probe; not a product implementation or a compression quality claim.",
    }
    OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
