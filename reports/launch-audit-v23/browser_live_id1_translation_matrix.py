"""Current-live Spanish/Hindi 10-page Translate retest, with content checks."""
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, re
from playwright.sync_api import sync_playwright

BASE = "https://paperplane.qd.je"
OUT = Path(__file__).resolve().parent


def make_source(path: Path) -> None:
    with fitz.open() as document:
        for number in range(1, 11):
            page = document.new_page()
            page.insert_text((72, 90),
                             f"SOURCE-PAGE-{number:03d} This paperplane document is ready for review and discussion.",
                             fontsize=12)
        document.save(path)


with TemporaryDirectory(prefix="paperplane-live-id1-") as temp:
    source = Path(temp) / "test-text-10page-live-synthetic.pdf"
    make_source(source)
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        for round_no in (1, 2):
            for language, code, translated_phrase in (
                ("Spanish", "es", "revisión y discusión"),
                ("Hindi", "hi", "तैयार"),
            ):
                context = browser.new_context(viewport={"width":1366,"height":900},accept_downloads=True)
                page = context.new_page()
                errors=[]
                page.on("pageerror", lambda error: errors.append(str(error)))
                api_status=[]
                api_headers=[]
                page.on("response", lambda response: (api_status.append(response.status), api_headers.append(dict(response.headers)))
                        if "/api/ai/translate" in response.url else None)
                response=page.goto(BASE+"/translate-pdf",wait_until="domcontentloaded",timeout=45000)
                assert response and response.status==200
                page.locator("#tool-title").wait_for(state="visible",timeout=30000)
                operations=page.evaluate("async()=>await (await fetch('/api/operations')).json()")
                translate_info=operations.get("translate",{})
                if translate_info.get("available") is False:
                    results.append({"round":round_no,"language":language,"available":False,
                                    "status":translate_info.get("status"),"prerequisite":translate_info.get("prerequisite"),
                                    "page_errors":errors})
                    context.close()
                    continue
                page.locator("#file-input").set_input_files(str(source))
                page.locator("#target_language").select_option(label=f"{code} ({language})")
                assert page.locator("#run-button").is_enabled()
                page.locator("#run-button").click()
                page.wait_for_function("""()=>{
                  const link=document.querySelector('#result-content a.btn-download');
                  const text=(document.querySelector('#result')?.innerText||'').toLowerCase();
                  return (link&&!link.hidden&&link.getBoundingClientRect().width>0) ||
                    (text.includes('failed')||text.includes('could not')||text.includes('rate limited'));
                }""",timeout=180000)
                output_name=None
                output_path=None
                content_checked=False
                translated_pages=0
                preserved_page_markers=0
                source_english_remaining=0
                link=page.locator("#result-content a.btn-download")
                if link.count() and link.is_visible():
                    output_name=link.get_attribute("download") or f"live-{code}.pdf"
                    with page.expect_download(timeout=45000) as download:
                        link.click()
                    output_path=Path(temp)/f"round-{round_no}-{code}.pdf"
                    download.value.save_as(output_path)
                    with fitz.open(output_path) as translated:
                        texts=[p.get_text() for p in translated]
                        translated_pages=sum(translated_phrase.casefold() in text.casefold() for text in texts)
                    preserved_page_markers=sum(
                        f"SOURCE-PAGE-{index:03d}" in text for index, text in enumerate(texts, start=1)
                    )
                    source_english_remaining=sum(
                        "this paperplane document is ready for review and discussion." in text.casefold()
                        for text in texts
                    )
                    content_checked=(len(texts)==10 and translated_pages==10 and
                                     preserved_page_markers==10 and source_english_remaining==0)
                    assert len(texts)==10, len(texts)
                result_text=page.locator("#result").inner_text() if page.locator("#result").count() else ""
                result={"round":round_no,"language":language,"available":True,
                        "http_status":api_status[-1] if api_status else None,
                        "retry_after":api_headers[-1].get("retry-after") if api_headers else None,
                        "output_name":output_name,"download_content_checked":content_checked,
                        "page_count":10 if output_path else None,"expected_translation_pages":translated_pages,
                        "preserved_page_markers":preserved_page_markers,
                        "source_english_remaining":source_english_remaining,"result_text":result_text[:800],
                        "page_errors":errors}
                if output_path:
                    result["download_bytes"]=output_path.stat().st_size
                results.append(result)
                page.screenshot(path=str(OUT/f"id1-live-{code}-round{round_no}.png"))
                context.close()
        browser.close()
    evidence={"site":BASE,"source":"synthetic 10-page fixture; owner-supplied test-text-10page.pdf was not present in workspace",
              "cases":results,"page_errors":sum(len(x.get("page_errors",[])) for x in results)}
    (OUT/"browser-live-id1-translation-matrix.json").write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(evidence,ensure_ascii=False,indent=2))
