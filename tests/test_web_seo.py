from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from server import OPERATION_SLUGS, SEO_CATALOG, app


client = TestClient(app)


def test_all_operation_slugs_render_crawlable_pages():
    for slug in OPERATION_SLUGS.values():
        response = client.get(f"/{slug}")
        assert response.status_code == 200
        assert '<link rel="canonical"' in response.text
        assert 'application/ld+json' in response.text
        assert 'class="seo-content"' in response.text


def test_operation_shell_is_server_rendered_for_deep_links():
    response = client.get("/word-to-pdf")
    assert response.status_code == 200
    assert '<div id="view-home" class="home-container" hidden>' in response.text
    assert '<div id="view-tool-desk" class="tool-desk-container">' in response.text
    assert '<h1 id="tool-title">Word to PDF</h1>' in response.text
    assert 'id="tool-hero-cat">Convert to PDF</span>' in response.text
    assert 'id="desk-breadcrumb-label">Convert to PDF / Word to PDF</span>' in response.text


def test_root_shell_keeps_home_view_visible():
    response = client.get("/")
    assert response.status_code == 200
    assert '<div id="view-home" class="home-container">' in response.text
    assert '<div id="view-tool-desk" class="tool-desk-container" hidden>' in response.text


def test_each_operation_has_unique_seo_catalog_and_schema_payload():
    assert set(SEO_CATALOG) == set(OPERATION_SLUGS)
    assert len({entry["title"] for entry in SEO_CATALOG.values()}) == len(SEO_CATALOG)
    assert len({entry["description"] for entry in SEO_CATALOG.values()}) == len(SEO_CATALOG)
    assert len({entry["heading"] for entry in SEO_CATALOG.values()}) == len(SEO_CATALOG)
    for operation, slug in OPERATION_SLUGS.items():
        assert len(SEO_CATALOG[operation]["how_to"]) == 3
        assert len(SEO_CATALOG[operation]["faqs"]) == 3
        assert len(set(SEO_CATALOG[operation]["related"])) == 4
        response = client.get(f"/{slug}")
        assert response.status_code == 200
        assert SEO_CATALOG[operation]["heading"] in response.text
        assert '"@type": "HowTo"' in response.text
        assert '"@type": "FAQPage"' in response.text


def test_forwarded_proxy_headers_drive_canonical_origin():
    response = client.get(
        "/word-to-pdf",
        headers={"x-forwarded-proto": "https", "x-forwarded-host": "pdf.example.test"},
    )
    assert response.status_code == 200
    assert 'href="https://pdf.example.test/word-to-pdf"' in response.text


def test_spa_seo_endpoint_returns_the_same_route_content_model():
    response = client.get("/api/seo/word_to_pdf")
    assert response.status_code == 200
    payload = response.json()
    assert payload["operation"] == "word_to_pdf"
    assert payload["slug"] == "word-to-pdf"
    assert len(payload["how_to"]) == 3
    assert len(payload["faqs"]) == 3


def test_sitemap_contains_every_operation_and_landing_pages():
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert all(f"/{slug}</loc>" in response.text for slug in OPERATION_SLUGS.values())
    assert "/convert-pdf</loc>" in response.text
    assert "/pdf-security</loc>" in response.text


def test_robots_allows_public_pages_and_points_to_sitemap():
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert "Allow: /" in response.text
    assert "Disallow: /api/" in response.text
    assert "sitemap.xml" in response.text


def test_cleanup_endpoint_queues_daemon_instead_of_running_inline():
    # Unauthenticated must be blocked (P1-2 Security Fix)
    unauth = client.post("/api/system/cleanup")
    assert unauth.status_code == 401

    # Authenticated privileged user succeeds
    import uuid
    from persistence import create_user, set_user_tier, create_session
    u_email = f"cleaner_{uuid.uuid4().hex[:6]}@example.com"
    uid = create_user(u_email, "CleanPass123!")
    set_user_tier(uid, "pro")
    sess = create_session(u_email, "CleanPass123!")
    auth_res = client.post("/api/system/cleanup", headers={"Authorization": f"Bearer {sess['token']}"})
    assert auth_res.status_code == 200
    assert auth_res.json() == {
        "status": "queued",
        "message": "Ephemeral storage purge queued for the background cleanup daemon.",
    }


def test_delivery_shell_keeps_heavy_assets_deferred_and_uses_clean_urls():
    root = Path(__file__).resolve().parent.parent
    app_js = (root / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    index_html = (root / "web" / "index.html").read_text(encoding="utf-8")
    styles_css = (root / "web" / "assets" / "styles.css").read_text(encoding="utf-8")
    launcher = (root / "app.py").read_text(encoding="utf-8")

    assert "window.history.pushState({ view: 'desk', op: state.operation }, '', targetPath)" in app_js
    assert '<script src="/assets/pdf.min.js" defer></script>' in index_html
    assert '<script src="/assets/pdf-lib.min.js" defer></script>' in index_html
    assert "@media (max-width: 900px)" in styles_css
    assert "workers = 1 if os.name == \"nt\" else max(1, configured_workers)" in launcher
    assert app_js.count("handleInitialRouting();") == 1
    assert "pathSlug === 'convert-pdf'" in app_js
    assert "pathSlug === 'pdf-security'" in app_js
