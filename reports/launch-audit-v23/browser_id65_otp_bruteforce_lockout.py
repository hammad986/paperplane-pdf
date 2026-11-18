from pathlib import Path
from tempfile import TemporaryDirectory
import json, os, secrets, socket, subprocess, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

with TemporaryDirectory(prefix='paperplane-id65-') as temp:
    data = Path(temp) / 'data'
    data.mkdir()
    candidate = socket.socket()
    candidate.bind(('127.0.0.1', 0))
    port = candidate.getsockname()[1]
    candidate.close()
    env = {name:value for name,value in os.environ.items()
        if not name.upper().startswith(('PAPERPLANE_', 'CASHFREE_', 'SMTP_', 'RESEND_', 'OPENAI_', 'OPENROUTER_', 'BLUESMINDS_', 'ANTHROPIC_', 'GEMINI_', 'DEEPSEEK_', 'GOOGLE_API_', 'AI_', 'ADMIN_'))
        and name not in {'SESSION_SECRET_KEY'}}
    env.update(PAPERPLANE_SKIP_DOTENV='1', PAPERPLANE_ENV='development', PAPERPLANE_DATA_DIR=str(data),
        PAPERPLANE_ADMIN_KEY=secrets.token_urlsafe(64), PAPERPLANE_ADMIN_CODE=secrets.token_urlsafe(30),
        PAPERPLANE_PORT=str(port), PAPERPLANE_SECURE_COOKIES='false', TESTING='True', PYTHONPATH=str(ROOT))
    emails = [f'id65-browser-{secrets.token_hex(4)}@example.invalid' for _ in range(2)]
    seed = f"""from persistence import init_db, create_user
import json
init_db()
password='OTP-Test-Password!234'
emails={emails!r}
for email in emails:
    create_user(email,password)
print(json.dumps(emails))
"""
    seeded = subprocess.run([sys.executable, '-c', seed], cwd=ROOT, env=env, text=True, capture_output=True, check=True)
    accounts = json.loads(seeded.stdout)
    app = subprocess.Popen([sys.executable, 'app.py'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f'http://127.0.0.1:{port}'
    try:
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        rounds = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='chrome', headless=True)
            for number, email in enumerate(accounts, start=1):
                page = browser.new_page(viewport={'width': 1366, 'height': 900})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '/', wait_until='domcontentloaded')
                result = page.evaluate("""async ({email,password}) => {
                  const login = new URLSearchParams({email,password,require_otp:'1'});
                  const challengeResponse = await fetch('/api/auth/login',{method:'POST',body:login});
                  const challenge = await challengeResponse.json();
                  const wrong = String((Number(challenge.dev_otp)+1)%1000000).padStart(6,'0');
                  const attempts=[];
                  for(let i=1;i<=6;i++){
                    const response=await fetch('/api/auth/verify-login-otp',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,otp:wrong})});
                    attempts.push({number:i,status:response.status,body:await response.json(),retryAfter:response.headers.get('Retry-After')});
                  }
                  const correctWhileLocked=await fetch('/api/auth/verify-login-otp',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,otp:challenge.dev_otp})});
                  return {challengeStatus:challengeResponse.status,challenge:challenge.status,hasDevOtp:!!challenge.dev_otp,attempts,correctWhileLocked:correctWhileLocked.status,correctRetryAfter:correctWhileLocked.headers.get('Retry-After')};
                }""", {'email':email,'password':'OTP-Test-Password!234'})
                assert result['challengeStatus']==200 and result['challenge']=='otp_required' and result['hasDevOtp'],result
                assert [a['status'] for a in result['attempts']]==[400,400,400,400,400,429],result
                assert result['attempts'][-1]['retryAfter'] and result['correctWhileLocked']==429 and result['correctRetryAfter'],result
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id65-otp-lockout-round{number}.png'))
                rounds.append({'round':number,**result,'page_errors':errors})
                page.close()
            browser.close()
        output={'rounds':rounds}
        (OUT/'browser-id65-otp-bruteforce-lockout.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
        print(json.dumps(output,indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
