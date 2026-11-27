"""Verify visible pricing names, INR amounts, periods, and per-tool names in Chrome."""
from __future__ import annotations
import json, socket, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"reports"/"launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402

def main():
    evidence={"checks":[],"page_errors":[],"console_errors":[]}
    with TemporaryDirectory(prefix="paperplane-v24-id40-") as tmp:
        app,base,_=helper.start_server(Path(tmp)/"data")
        try:
            port=int(base.rsplit(":",1)[1])
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1",port),timeout=.2): break
                except OSError: time.sleep(.2)
            else: raise RuntimeError("local app did not start")
            with sync_playwright() as p:
                browser=p.chromium.launch(channel="chrome",headless=True)
                for width,height in ((390,844),(1366,900)):
                    page=browser.new_page(viewport={"width":width,"height":height})
                    page.on("pageerror",lambda error:evidence["page_errors"].append(str(error)))
                    page.on("console",lambda msg:evidence["console_errors"].append(msg.text) if msg.type=="error" else None)
                    response=page.goto(base+"/pricing",wait_until="domcontentloaded")
                    cards=page.locator(".pricing-tier-card[data-plan-tier]")
                    cards.first.wait_for()
                    data=page.evaluate("""() => [...document.querySelectorAll('.pricing-tier-card[data-plan-tier]')].map(card=>({tier:card.dataset.planTier,
                      name:card.querySelector('.tier-title')?.innerText.trim(),price:card.querySelector('.tier-price-val')?.innerText.trim(),
                      period:card.querySelector('.tier-price-period')?.innerText.trim(),cta:card.querySelector('.tier-subscribe-btn')?.innerText.trim()||''}))""")
                    limits=page.locator("#pricing-limits-table tbody tr").all_inner_texts()
                    expected={"free":("Free","₹0","/ always"),"exam_pass":("Exam Pass","₹19","/ 24 hours"),
                    "student_pro":("Student & Educator","₹49","/ 30 days"),"cyber_cafe":("All-In-One Pro & Developer","₹299","/ 30 days")}
                    tier_matches=all((x["name"],x["price"],x["period"])==expected.get(x["tier"]) for x in data) and len(data)==4
                    cta_amounts_match=all((not x["cta"] or x["price"] in x["cta"]) for x in data)
                    no_alternate_currency=not any(token in json.dumps(data) for token in ("$","USD","US$"))
                    catalog_names=page.evaluate("Object.values(state.operations).map(tool=>tool.label)")
                    pricing_tool_names=page.locator("#pricing-limits-table tbody tr th[scope='row']").all_inner_texts()
                    same_catalog=(len(limits)==len(catalog_names)==44 and pricing_tool_names==catalog_names)
                    layout=page.evaluate("({innerWidth,documentWidth:document.documentElement.scrollWidth,tableRows:document.querySelectorAll('#pricing-limits-table tbody tr').length})")
                    screenshot=Path(__file__).parent/f"browser-id40-pricing-{width}.png"
                    page.screenshot(path=str(screenshot),full_page=True)
                    evidence["checks"].append({"viewport":width,"status":response.status if response else None,"tiers":data,
                      "tier_names_prices_periods_match":tier_matches,"cta_amounts_match_cards":cta_amounts_match,
                      "INR_only":no_alternate_currency,"tool_rows_match_44_operation_catalog":same_catalog,
                      "catalog_names":catalog_names,"pricing_tool_names":pricing_tool_names,
                      "layout":layout,"no_horizontal_overflow":layout["documentWidth"]==width,"screenshot":screenshot.name})
                    page.close()
                browser.close()
        finally:
            app.terminate(); app.wait(timeout=5)
    evidence["result"]=len(evidence["checks"])==2 and not evidence["page_errors"] and not evidence["console_errors"] and all(
      x["status"]==200 and x["tier_names_prices_periods_match"] and x["cta_amounts_match_cards"] and x["INR_only"] and x["tool_rows_match_44_operation_catalog"] and x["no_horizontal_overflow"] for x in evidence["checks"])
    out=Path(__file__).parent/"browser-id40-pricing-name-consistency.json"
    out.write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    print(json.dumps(evidence,indent=2))
    if not evidence["result"]: raise SystemExit(1)

if __name__=="__main__": main()
