"""Read-only 1024px layout check for a live PDF route."""
from __future__ import annotations

import json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "https://paperplane.qd.je"
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1024, "height": 900}, service_workers="block")
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)[:300]))
    response = page.goto(BASE + "/merge-pdf", wait_until="domcontentloaded", timeout=30000)
    assets = page.evaluate("""() => [...document.querySelectorAll('script[src],link[href]')]
      .map(n=>n.src||n.href).filter(u=>/app\\.js\\?v=|styles\\.css\\?v=/.test(u))""")
    layout = page.evaluate("""() => {
      const bar=document.querySelector('.topbar');
      const rect=e=>{const r=e.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom}};
      const groups=['.topbar-left','.workspace-tabs','.topbar-right'].map(s=>bar?.querySelector(s)).filter(e=>e&&getComputedStyle(e).display!=='none');
      const boxes=groups.map(e=>({selector:e.className,...rect(e)}));
      const overlaps=[];
      for(let i=0;i<boxes.length;i++)for(let j=i+1;j<boxes.length;j++)if(Math.min(boxes[i].right,boxes[j].right)-Math.max(boxes[i].left,boxes[j].left)>2&&Math.min(boxes[i].bottom,boxes[j].bottom)-Math.max(boxes[i].top,boxes[j].top)>2)overlaps.push([boxes[i].selector,boxes[j].selector]);
      return {viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,topbar:{clientWidth:bar?.clientWidth,scrollWidth:bar?.scrollWidth,boxes,overlaps}};
    }""")
    browser.close()
result={"site":BASE,"route":"/merge-pdf","read_only":True,"status":response.status if response else None,
        "assets":assets,"layout":layout,"page_errors":errors}
Path(__file__).with_name("browser-live-1024-layout-2026-11-22.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
print(json.dumps(result,indent=2))
