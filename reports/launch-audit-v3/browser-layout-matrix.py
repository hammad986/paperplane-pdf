from pathlib import Path
import json

from playwright.sync_api import sync_playwright


BASE = "http://127.0.0.1:8501"
WIDTHS = [360, 375, 390, 414, 768, 1024, 1280, 1366, 1920]
VIEWS = ["home", "desk", "studio", "ai", "download", "api-docs", "legal"]
VIEW_SELECTORS = {
    "home": "#view-home",
    "desk": "#view-tool-desk",
    "studio": "#view-pdf-studio",
    "ai": "#view-ai-studio",
    "download": "#view-download",
    "api-docs": "#view-api-docs",
    "legal": "#view-legal",
}


def main():
    Path("reports/launch-audit-v3").mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE, wait_until="domcontentloaded", timeout=20000)
        page.add_style_tag(content="*,*::before,*::after{transition:none!important;animation:none!important;scroll-behavior:auto!important}")
        # The workspace switches views only after auth and the catalog finish.
        # Wait for that boot transaction so the layout matrix doesn't race it.
        page.locator("#sidebar-tools-container .sidebar-tool-item").first.wait_for(state="attached", timeout=20000)
        results = []

        for width in WIDTHS:
            height = 900 if width > 600 else 812
            page.set_viewport_size({"width": width, "height": height})
            for theme in ["light", "dark"]:
                page.evaluate("""theme => {
                  document.body.classList.toggle('dark-mode', theme === 'dark');
                  document.body.classList.toggle('light-mode', theme === 'light');
                }""", theme)
                for sidebar in ["open", "closed"]:
                    page.evaluate("""state => {
                      const shell = document.querySelector('#app-shell');
                      const sb = document.querySelector('#sidebar');
                      if (innerWidth <= 900) {
                        sb?.classList.toggle('mobile-open', state === 'open');
                        shell?.classList.remove('sidebar-collapsed');
                      } else {
                        sb?.classList.remove('mobile-open');
                        shell?.classList.toggle('sidebar-collapsed', state === 'closed');
                      }
                    }""", sidebar)
                    for view in VIEWS:
                        page.evaluate("""view => {
                          if (view === 'legal') switchWorkspaceView(view, 'privacy', false);
                          else switchWorkspaceView(view, null, false);
                        }""", view)
                        # Home defaults to a collapsed rail, and view switches
                        # close the mobile drawer. Reapply the requested state
                        # after navigation so both requested states are real.
                        page.evaluate("""state => {
                          const shell = document.querySelector('#app-shell');
                          const sb = document.querySelector('#sidebar');
                          if (innerWidth <= 900) {
                            sb?.classList.toggle('mobile-open', state === 'open');
                            shell?.classList.remove('sidebar-collapsed');
                          } else {
                            sb?.classList.remove('mobile-open');
                            shell?.classList.toggle('sidebar-collapsed', state === 'closed');
                          }
                        }""", sidebar)
                        page.wait_for_timeout(10)
                        data = page.evaluate("""({width, theme, sidebar, view, selector}) => {
                          const rect = el => {
                            const b = el.getBoundingClientRect();
                            return {x: Math.round(b.x), y: Math.round(b.y), right: Math.round(b.right), bottom: Math.round(b.bottom), width: Math.round(b.width), height: Math.round(b.height)};
                          };
                          const styleVisible = el => getComputedStyle(el).display !== 'none' && getComputedStyle(el).visibility !== 'hidden' && Number(getComputedStyle(el).opacity) !== 0;
                          const onScreen = el => {
                            const b = el.getBoundingClientRect();
                            return b.width > 0 && b.height > 0 && styleVisible(el) && b.right > 0 && b.left < innerWidth && b.bottom > 0 && b.top < innerHeight;
                          };
                          const hasScrollableXAncestor = el => {
                            for (let p = el.parentElement; p; p = p.parentElement) {
                              const s = getComputedStyle(p);
                              if (['auto','scroll'].includes(s.overflowX) && p.scrollWidth > p.clientWidth + 2) return true;
                            }
                            return false;
                          };
                          const hasScrollableYAncestor = el => {
                            for (let p = el.parentElement; p; p = p.parentElement) {
                              const s = getComputedStyle(p);
                              if (['auto','scroll'].includes(s.overflowY) && p.scrollHeight > p.clientHeight + 2) return true;
                            }
                            return false;
                          };
                          const visibleControls = [...document.querySelectorAll('.topbar button,.topbar a,.sidebar a,.sidebar button,.mobile-workspace-bar button,.mobile-workspace-bar a')].filter(onScreen);
                          const clipped = visibleControls.filter(el => {
                            const b = el.getBoundingClientRect();
                            return ((b.left < -1 || b.right > innerWidth + 1) && !hasScrollableXAncestor(el)) || ((b.top < -1 || b.bottom > innerHeight + 1) && !hasScrollableYAncestor(el));
                          }).map(el => ({text:(el.innerText || '').trim().replace(/\\s+/g,' ').slice(0,48), aria:el.getAttribute('aria-label'), title:el.title, rect:rect(el)})).slice(0,12);
                          const sidebarControls = [...document.querySelectorAll('.sidebar a,.sidebar button')].filter(onScreen);
                          const unlabeled = sidebarControls.filter(el => {
                            const text = (el.innerText || '').trim() || [...el.querySelectorAll('*')].filter(n => {
                              const s=getComputedStyle(n); return s.display !== 'none' && s.visibility !== 'hidden' && (n.children.length===0 || n.matches('span'));
                            }).map(n=>(n.innerText||'').trim()).join(' ').trim();
                            return !(text || el.getAttribute('aria-label') || el.title || el.getAttribute('aria-labelledby'));
                          }).map(el => ({tag:el.tagName, cls:el.className, html:el.outerHTML.slice(0,140)})).slice(0,10);
                          const shell=document.querySelector('#app-shell');
                          const viewEl=document.querySelector(selector);
                          return {
                            width, height:innerHeight, theme, sidebar, view,
                            viewport:innerWidth,
                            docWidth:document.documentElement.scrollWidth,
                            bodyWidth:document.body.scrollWidth,
                            horizontalOverflow:Math.max(document.documentElement.scrollWidth,document.body.scrollWidth)>innerWidth+1,
                            visibleView:!!viewEl && !viewEl.hidden,
                            content: viewEl ? rect(viewEl) : null,
                            shell: rect(shell),
                            clipped,
                            unlabeled
                          };
                        }""", {"width": width, "theme": theme, "sidebar": sidebar, "view": view, "selector": VIEW_SELECTORS[view]})
                        results.append(data)

        for width in [360, 390, 768, 1366]:
            page.set_viewport_size({"width": width, "height": 812 if width < 600 else 900})
            page.evaluate("""() => {
              document.body.classList.remove('dark-mode');
              document.body.classList.add('light-mode');
              document.querySelector('#app-shell')?.classList.toggle('sidebar-collapsed', innerWidth > 900);
              document.querySelector('#sidebar')?.classList.remove('mobile-open');
              switchWorkspaceView('home', null, false);
            }""")
            page.screenshot(path=f"reports/launch-audit-v3/layout-{width}.png")

        failures = [r for r in results if r["horizontalOverflow"] or r["clipped"] or r["unlabeled"] or not r["visibleView"]]
        summary = {"cases": len(results), "widths": WIDTHS, "themes": ["light", "dark"], "sidebar_states": ["open", "closed"], "views": VIEWS, "failures": failures, "errors": errors, "all_results": results}
        Path("reports/launch-audit-v3/layout-matrix.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        concise = [{"width": f["width"], "theme": f["theme"], "sidebar": f["sidebar"], "view": f["view"], "horizontalOverflow": f["horizontalOverflow"], "visibleView": f["visibleView"], "clipped": f["clipped"], "unlabeled": f["unlabeled"]} for f in failures[:20]]
        print(json.dumps({"cases": len(results), "failure_count": len(failures), "failures": concise, "page_errors": errors}, ensure_ascii=False, indent=2))
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
