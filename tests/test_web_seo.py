from __future__ import annotations

import html
from pathlib import Path
import re

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
    assert '<div id="view-tool-desk-directory" class="tool-desk-directory" hidden>' in response.text
    assert '<div id="view-tool-desk" class="tool-desk-container">' in response.text
    assert '<h1 id="tool-title">Word to PDF</h1>' in response.text
    assert 'id="tool-hero-cat">Convert to PDF</span>' in response.text
    assert 'id="desk-breadcrumb-label">Convert to PDF / Word to PDF</span>' in response.text


def test_common_guessed_tool_slugs_redirect_to_canonical_pages():
    aliases = {
        "exam-photo-signature-resizer": "ssc-photo-resizer",
        "resize-photo": "resize-image-dimensions",
        "photo-resize": "resize-image-dimensions",
        "compress-photo": "compress-image-online",
        "add-page-numbers": "add-page-numbers-to-pdf",
        "mask-aadhaar": "mask-aadhaar-card-online",
        "flatten-pdf-forms": "flatten-pdf",
        "ai-summarize": "summarize-pdf",
        "extract-pages": "split-pdf",
        "grayscale-pdf": "convert-pdf-to-grayscale",
        "pdf-to-ppt": "pdf-to-powerpoint",
        "ppt-to-pdf": "powerpoint-to-pdf",
    }
    for alias, canonical in aliases.items():
        response = client.get(f"/{alias}", follow_redirects=False)
        assert response.status_code == 301
        assert response.headers["location"] == f"/{canonical}"


def test_root_shell_renders_tool_desk_directory_for_first_visit():
    response = client.get("/")
    assert response.status_code == 200
    assert '<div id="view-tool-desk-directory" class="tool-desk-directory">' in response.text
    assert '<div id="view-tool-desk" class="tool-desk-container" hidden>' in response.text


def test_home_shell_privacy_copy_matches_processing_modes_and_footer_links():
    response = client.get("/")
    assert response.status_code == 200
    assert "Browser processing for supported tools" in response.text
    assert "when browser processing is selected" in response.text
    assert "100% locally" not in response.text
    assert "100% Private Browser Processing" not in response.text
    for href in ("/tool-desk", "/dashboard", "/pricing", "/faq"):
        assert f'href="{href}"' in response.text


def test_each_operation_has_unique_seo_catalog_and_schema_payload():
    assert set(SEO_CATALOG) == set(OPERATION_SLUGS)
    assert len({entry["title"] for entry in SEO_CATALOG.values()}) == len(SEO_CATALOG)
    assert len({entry["description"] for entry in SEO_CATALOG.values()}) == len(SEO_CATALOG)
    assert len({entry["heading"] for entry in SEO_CATALOG.values()}) == len(SEO_CATALOG)
    for operation, slug in OPERATION_SLUGS.items():
        assert len(SEO_CATALOG[operation]["how_to"]) == 3
        assert len(SEO_CATALOG[operation]["faqs"]) >= 3
        assert len(set(SEO_CATALOG[operation]["related"])) == 4
        response = client.get(f"/{slug}")
        assert response.status_code == 200
        assert SEO_CATALOG[operation]["heading"] in response.text
        assert '"@type": "HowTo"' in response.text
        assert '"@type": "FAQPage"' in response.text


def test_workflow_cards_have_useful_body_copy_without_claiming_missing_controls():
    import re

    for slug in OPERATION_SLUGS.values():
        response = client.get(f"/{slug}")
        section = re.search(r'<section class="seo-content".*?</section>', response.text, re.S)
        assert section, slug
        cards = re.findall(r'<article class="seo-howto-step">.*?<h3>(.*?)</h3><p>(.*?)</p>', section.group(0), re.S)
        assert len(cards) == 3, slug
        assert all(title.strip() and body.strip() for title, body in cards), slug

    checks = {
        "ocr-pdf": ("After upload, select an available OCR language", "quality setting"),
        "translate-pdf": ("available before upload", "not shown before upload"),
        "html-to-pdf": ("Enter an allowed public URL", "page-size controls"),
        "pdf-to-word": ("Select a text-based PDF", "OCR settings selector"),
        "pdf-to-excel": ("Convert the extracted content, then review the workbook", "table-region previews"),
        "pdf-to-powerpoint": ("Convert the pages into slides", "text reconstruction options"),
        "pdf-to-jpg": ("After upload, choose an export resolution", "page and image quality options"),
        "excel-to-pdf": ("Convert the workbook and review its pages", "sheet selector"),
        "annotate-pdf": ("Choose an annotation type", "Load the PDF into Studio"),
        "watermark-pdf": ("Enter watermark text or select an image", "position"),
        "protect-pdf": ("Enter a password for the protected copy", "owner passwords plus permissions"),
        "pdf-metadata": ("title, author, and subject", "keywords"),
    }
    for slug, (present, absent) in checks.items():
        response = client.get(f"/{slug}")
        section = re.search(r'<section class="seo-content".*?</section>', response.text, re.S)
        assert section, slug
        cards = re.findall(r'<article class="seo-howto-step">.*?<h3>(.*?)</h3><p>(.*?)</p>', section.group(0), re.S)
        card_copy = " ".join(" ".join(item) for item in cards)
        card_titles = " ".join(title for title, _ in cards)
        assert present in card_copy, slug
        assert absent not in card_titles, slug

    home = client.get("/")
    apps = client.get("/download")
    home_section = re.search(r'<section class="seo-howto-grid tool-desk-quick-steps".*?</section>', home.text, re.S)
    apps_section = re.search(r'<section class="download-howto-section".*?</section>', apps.text, re.S)
    home_cards = re.findall(r'<article class="seo-howto-step">.*?<h3>(.*?)</h3><p>(.*?)</p>', home_section.group(0), re.S) if home_section else []
    app_cards = re.findall(r'<article class="seo-howto-step">.*?<h3>(.*?)</h3><p>(.*?)</p>', apps_section.group(0), re.S) if apps_section else []
    assert len(home_cards) == 3 and all(title.strip() and body.strip() for title, body in home_cards)
    assert len(app_cards) == 3 and all(title.strip() and body.strip() for title, body in app_cards)
    assert "No app installer is available to download yet" in apps.text


def test_untrusted_forwarded_headers_cannot_change_canonical_origin():
    response = client.get(
        "/word-to-pdf",
        headers={"x-forwarded-proto": "https", "x-forwarded-host": "pdf.example.test"},
    )
    assert response.status_code == 200
    assert 'href="http://testserver/word-to-pdf"' in response.text


def test_spa_seo_endpoint_returns_the_same_route_content_model():
    response = client.get("/api/seo/word_to_pdf")
    assert response.status_code == 200
    payload = response.json()
    assert payload["operation"] == "word_to_pdf"
    assert payload["slug"] == "word-to-pdf"
    assert len(payload["how_to"]) == 3
    assert len(payload["faqs"]) == 4
    assert payload["faqs"][-1][0] == "Does Paperplane keep a job history?"
    assert "does not provide a recent-files or job-history page" in payload["faqs"][-1][1]


def test_faq_workspace_matches_the_four_home_page_faqs():
    home = client.get("/").text
    faq_page = client.get("/faq").text
    home_section = re.search(r'<div class="seo-faq">(.*?)</div>\s*<nav class="seo-related"', home, re.S)
    workspace_section = re.search(r'<section id="view-faq"[^>]*>(.*?)</section>', faq_page, re.S)
    assert home_section and workspace_section

    def entries(section: str) -> list[tuple[str, str]]:
        values = re.findall(r'<details[^>]*>\s*<summary>(.*?)</summary>\s*<p>(.*?)</p>\s*</details>', section, re.S)
        return [(html.unescape(re.sub(r"<[^>]+>", " ", question)).strip(),
                 html.unescape(re.sub(r"<[^>]+>", " ", answer)).strip())
                for question, answer in values]

    home_entries = entries(home_section.group(1))
    workspace_entries = entries(workspace_section.group(1))
    assert len(home_entries) == 4
    assert workspace_entries == home_entries


def test_developer_api_docs_use_configured_free_app_quota():
    response = client.get("/developers")
    assert response.status_code == 200
    assert "free app workflow quota is 10 operations/day" in response.text
    assert "free app workflow quota is 100 operations/day" not in response.text


def test_howto_and_faq_copy_does_not_promise_missing_pdf_controls():
    pdf_to_text = client.get("/api/seo/pdf_to_text").json()
    text_pages_faq = dict(pdf_to_text["faqs"])["Can I extract only certain pages?"]
    assert "currently exports the full document" in text_pages_faq
    assert "page-range controls" not in text_pages_faq

    pdf_to_jpg = client.get("/api/seo/pdf_to_jpg").json()
    assert "every document page" in pdf_to_jpg["intro"]
    assert "selected document pages" not in pdf_to_jpg["intro"]

    compare = client.get("/api/seo/compare").json()
    assert "plain-text report" in compare["description"]
    assert "highlight text" not in compare["description"]

    metadata = client.get("/api/seo/metadata").json()
    assert "title, author, and subject" in metadata["description"]
    assert "keywords" not in metadata["description"]
    assert "not editable here" in dict(metadata["faqs"])["What PDF metadata can I change?"]


def test_conversion_and_annotation_copy_matches_available_controls():
    word = client.get("/api/seo/word_to_pdf").json()
    assert word["how_to"][1] == "Convert with the available document renderer"
    assert "no OCR or page-layout controls" in client.get("/word-to-pdf").text

    powerpoint = client.get("/api/seo/powerpoint_to_pdf").json()
    assert powerpoint["how_to"][1] == "Convert the slides with the available renderer"
    assert "no orientation or output-options controls" in client.get("/powerpoint-to-pdf").text

    annotate = client.get("/api/seo/annotate").json()
    assert "freehand" not in annotate["description"]
    assert "draw shapes" not in annotate["description"]
    assert "rectangle mark" in dict(annotate["faqs"])["Can I highlight text in a PDF?"]

    operations = client.get("/api/operations").json()
    annotate_operation = operations["annotate"]
    assert "strike through" in annotate_operation["description"]
    assert "draw shapes" not in annotate_operation["description"]

    watermark = client.get("/api/seo/watermark").json()
    assert "built-in placement" in watermark["description"]
    assert "adjustable placement" not in watermark["description"]
    assert "rotation" not in watermark["description"]

    protect = client.get("/api/seo/protect").json()
    assert "does not provide separate owner-password or permission controls" in protect["description"]
    assert "owner controls" not in protect["intro"]
    assert "does not offer permission controls" in dict(protect["faqs"])["Can I prevent copying or printing?"]
    operations = client.get("/api/operations").json()
    assert "one password" in operations["protect"]["description"]
    assert "separate owner-password and permission controls are not provided" in operations["protect"]["description"]

    crop = client.get("/api/seo/crop").json()
    assert "every PDF page" in crop["description"]
    assert "one or more pages" not in " ".join(crop["how_to"])
    assert "Preview and download" not in crop["how_to"]
    assert "same top, bottom, left, and right margins to every page" in dict(crop["faqs"])["Can I crop all pages with the same margins?"]


def test_page_organizer_copy_matches_its_page_number_order_control():
    response = client.get("/api/seo/organize")
    assert response.status_code == 200
    payload = response.json()
    description = " ".join([payload["description"], payload["heading"], payload["intro"], *payload["how_to"]])
    assert "comma-separated page numbers" in description
    assert "every page number exactly once" in description
    assert not any(term in description.lower() for term in ("drag-and-drop", "visual organizer", "thumbnails"))


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
    pdf_runtime_js = (root / "web" / "assets" / "pdf_runtime.js").read_text(encoding="utf-8")
    index_html = (root / "web" / "index.html").read_text(encoding="utf-8")
    styles_css = (root / "web" / "assets" / "styles.css").read_text(encoding="utf-8")
    launcher = (root / "app.py").read_text(encoding="utf-8")

    assert "window.history.pushState({ view: 'desk', op: state.operation }, '', targetPath)" in app_js
    assert '<script src="/assets/pdf_runtime.js?v=25" defer></script>' in index_html
    assert '<script src="/assets/pdf.min.js" defer></script>' not in index_html
    assert '<script src="/assets/pdf-lib.min.js" defer></script>' not in index_html
    assert "ensurePdfJs" in pdf_runtime_js and "ensurePdfLib" in pdf_runtime_js
    assert "PaperplanePdfRuntime.ensurePdfJs()" in app_js
    assert "@media (max-width: 900px)" in styles_css
    assert "workers = 1 if os.name == \"nt\" else max(1, configured_workers)" in launcher
    assert app_js.count("handleInitialRouting();") == 1
    assert "pathSlug === 'convert-pdf'" in app_js
    assert "pathSlug === 'pdf-security'" in app_js
