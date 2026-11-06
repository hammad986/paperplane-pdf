import re,requests,sys
sys.stdout.reconfigure(encoding='utf-8')
base='https://paperplane.qd.je'
r=requests.get(base+'/developers',timeout=12)
print('developers',r.status_code,r.url)
for href,body in re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',r.text,re.I|re.S):
    label=re.sub(r'<[^>]+>',' ',body).strip()
    if any(word in (label+' '+href).lower() for word in ['swagger','redoc','openapi','api guide','/docs']):
        print('link',repr(label),href)
for path in ['/docs','/redoc','/openapi.json']:
    response=requests.get(base+path,allow_redirects=False,timeout=12)
    print(path,response.status_code,response.headers.get('location'),response.headers.get('content-type'))
