from pathlib import Path
from tempfile import TemporaryDirectory
import os
import socket
import sys
import time
import json
import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'reports' / 'launch-audit-v23'
ROUND = int(os.environ.get('ID42_ROUND', '1'))
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id42-ai-') as temp:
    temp_path = Path(temp)
    fixture = temp_path / 'ai-mobile-layout.pdf'
    with fitz.open() as doc:
        doc.new_page().insert_text((72, 72), 'AI layout handoff fixture')
        doc.save(fixture)
    app, base, _identity = helper.start_server(temp_path / 'data')
    try:
        port = int(base.rsplit(':', 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        results = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='chrome', headless=True)
            for width, height in [(320, 740), (390, 844), (820, 1180), (1366, 900)]:
                page = browser.new_page(viewport={'width': width, 'height': height}, is_mobile=width < 500, has_touch=width < 500)
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                response = page.goto(base + '/ai-intelligence', wait_until='domcontentloaded')
                page.wait_for_timeout(800)
                metrics = page.evaluate('''() => {
                  const rect = selector => {
                    const element = document.querySelector(selector);
                    if (!element) return null;
                    const box = element.getBoundingClientRect();
                    return {x:box.x, y:box.y, width:box.width, height:box.height, bottom:box.bottom};
                  };
                  return {viewport:innerWidth, docWidth:document.documentElement.scrollWidth,
                    aiTopbar:rect('.ai-studio-topbar'), container:rect('.ai-studio-container'),
                    chat:rect('.ai-studio-container > .ai-chat-card'), uploadButton:rect('#ai-upload-btn'),
                    howto:rect('.ai-howto-section'), mobileNav:rect('.mobile-workspace-bar')};
                }''')
                assert response and response.status == 200, response.status if response else None
                assert metrics['docWidth'] <= width, metrics
                if width <= 900:
                    assert metrics['chat']['y'] <= metrics['aiTopbar']['bottom'] + 40, metrics
                    assert metrics['uploadButton']['bottom'] < metrics['mobileNav']['y'], metrics
                    assert metrics['howto']['y'] >= metrics['container']['bottom'], metrics
                    page.locator('#ai-file-input').set_input_files(str(fixture))
                    page.wait_for_function("document.querySelector('#ai-active-doc-bar')?.hidden === false", timeout=10000)
                    metrics['loaded_document_visible'] = not page.locator('#ai-active-doc-bar').is_hidden()
                    assert metrics['loaded_document_visible'], metrics
                else:
                    assert metrics['howto']['y'] < metrics['container']['y'], metrics
                assert not errors, errors
                page.screenshot(path=str(OUT / f'id42-local-ai-{width}-round{ROUND}.png'), full_page=width > 500)
                results.append({'round':ROUND, 'status':response.status, **metrics, 'page_errors':errors})
                page.close()
            browser.close()
        (OUT / f'browser-id42-local-ai-layout-round{ROUND}.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        print(json.dumps(results, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
