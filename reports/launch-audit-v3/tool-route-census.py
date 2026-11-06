import re,requests,json,sys
from pathlib import Path
sys.path.insert(0,str(__import__('pathlib').Path.cwd()))
import server
source=open('web/assets/app.js',encoding='utf-8').read()
slug_block=source.split('const TOOL_SLUGS = {',1)[1].split('};',1)[0]
slugs=dict(re.findall(r"\b(\w+)\s*:\s*'([^']+)'",slug_block))
results=[]
for op,info in server.OPERATIONS.items():
    slug=slugs.get(op,op)
    r=requests.get('http://127.0.0.1:8501/'+slug,allow_redirects=False,timeout=8)
    page_title=re.search(r'<title>(.*?)</title>',r.text,re.I|re.S)
    results.append({'operation':op,'path':'/'+slug,'status':r.status_code,'location':r.headers.get('location'),'title':re.sub(r'\s+',' ',page_title.group(1)).strip() if page_title else None,'branded404':'Page Not Found' in r.text})
for alias in ['/remove-pages','/tool-desk','/api-docs','/developers','/docs','/redoc','/openapi.json']:
    r=requests.get('http://127.0.0.1:8501'+alias,allow_redirects=False,timeout=8)
    results.append({'operation':'legacy-route','path':alias,'status':r.status_code,'location':r.headers.get('location'),'branded404':'Page Not Found' in r.text})
tool_routes = [row for row in results if row['operation'] != 'legacy-route']
expected_aliases = {
    '/remove-pages': (301, '/remove-pages-pdf'),
    '/tool-desk': (307, '/'),
    '/api-docs': (307, '/developers'),
    '/developers': (200, None),
    '/docs': (307, '/developers'),
    # FastAPI schema viewers are deliberately disabled in production.
    '/redoc': (404, None),
    '/openapi.json': (404, None),
}
alias_routes = [row for row in results if row['operation'] == 'legacy-route']
failures = [row for row in tool_routes if row['status'] != 200 or not row['title']]
failures.extend(
    row for row in alias_routes
    if (row['status'], row['location']) != expected_aliases.get(row['path'])
)
report = {
    'operation_count': len(server.OPERATIONS),
    'tool_routes_passed': len(tool_routes) - len([row for row in failures if row['operation'] != 'legacy-route']),
    'expected_aliases_and_disabled_docs_passed': len(alias_routes) - len([row for row in failures if row['operation'] == 'legacy-route']),
    'failures': failures,
    'routes': results,
}
Path('reports/launch-audit-v3/tool-route-census.json').write_text(
    json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8'
)
print(json.dumps({key: report[key] for key in ('operation_count', 'tool_routes_passed', 'expected_aliases_and_disabled_docs_passed', 'failures')}, ensure_ascii=False))
