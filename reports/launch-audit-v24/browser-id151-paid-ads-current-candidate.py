import json
from pathlib import Path
from playwright.sync_api import sync_playwright
rounds=[];errors=[]
with sync_playwright() as p:
 b=p.chromium.launch()
 for i in (1,2):
  page=b.new_page(viewport={'width':1366,'height':900});page.on('pageerror',lambda e:errors.append(str(e)));page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
  page.goto('http://127.0.0.1:8767/',wait_until='domcontentloaded');page.wait_for_function("()=>!document.body.classList.contains('auth-pending')")
  paid=page.evaluate("""()=>{if(typeof window.updateBillingUI!=='function')return false;window.updateBillingUI({authenticated:true,user_id:'synthetic-pro',tier:'pro',is_pro:true,usage_today:0,daily_limit:10,plan_limits:{free_operations_per_day:10,guest_max_file_size_mb:50,platform_max_file_size_mb:500,exam_pass_max_file_size_mb:500,pro_max_file_size_mb:500,max_batch_files:100}});return true}""")
  scan=page.evaluate("""()=>({ads:[...document.querySelectorAll('.adsense-banner-container, ins.adsbygoogle, [data-ad-slot], [id*=ad-slot]')].map(x=>({tag:x.tagName,id:x.id,cls:x.className,visible:x.checkVisibility()})),sponsorText:(document.body.innerText.match(/SPONSORED|Go Ad-Free|Sponsored Content/gi)||[]),placeholderIds:(document.documentElement.innerHTML.match(/ca-pub-[A-Z0-9-]+/gi)||[]),paidBadge:document.querySelector('#user-role-badge')?.innerText,upgradeVisible:[...document.querySelectorAll('#sidebar-upgrade-btn,#topbar-upgrade-btn')].some(x=>x.checkVisibility())})""")
  rounds.append({'round':i,'paid_ui_applied':paid,**scan});page.close()
 b.close()
result={'build':'app191/styles71','rounds':rounds,'browser_errors':errors,'passed':len(rounds)==2 and all(x['paid_ui_applied'] and not x['ads'] and not x['sponsorText'] and not x['placeholderIds'] and not x['upgradeVisible'] for x in rounds) and not errors}
Path('reports/launch-audit-v24/browser-id151-paid-ads-current-candidate.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))