from __future__ import annotations

import re
from pathlib import Path

import server


def test_tool_how_to_steps_render_once_without_generic_claims():
    context = {
        "related": [],
        "faqs": [],
        "category": "Organize PDF",
        "heading": "Merge PDF",
        "intro": "Combine selected documents.",
        "how_to": ["Choose the PDFs", "Arrange their order", "Download the merged file"],
    }

    markup = server.render_seo_content(context)

    for step in context["how_to"]:
        assert markup.count(f"<h3>{step}</h3>") == 1
        assert f"<p>{step}</p>" not in markup
    assert "seo-proof-grid" not in markup
    assert "seo-comparison-table" not in markup
    assert "Zero-Upload Client Privacy Mode" not in markup


def test_browser_local_processing_is_limited_to_the_implemented_operations():
    root = Path(__file__).resolve().parent.parent
    app_js = (root / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    index_html = (root / "web" / "index.html").read_text(encoding="utf-8")

    match = re.search(r"CLIENT_SIDE_SUPPORTED_OPERATIONS\s*=\s*new Set\(\[([^\]]+)\]\)", app_js)
    assert match
    supported = set(re.findall(r"'([^']+)'", match.group(1)))
    assert supported == {"merge", "split", "remove", "rotate"}
    assert "input.disabled = !supported" in app_js
    assert "if (!CLIENT_SIDE_SUPPORTED_OPERATIONS.has(state.operation))" in app_js
    assert "100% Client-Side Privacy Mode Activated" not in app_js
    assert "Zero-Upload Client Privacy Mode" not in index_html
    assert "Browser-local processing is available only for Merge, Split / extract, Remove pages, and Rotate PDF." in index_html

    assert set(server.OPERATION_SLUGS) == set(server.SEO_CATALOG)


def test_ai_metadata_uses_a_dash_for_missing_values_and_privacy_copy_is_qualified():
    root = Path(__file__).resolve().parent.parent
    app_js = (root / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    index_html = (root / "web" / "index.html").read_text(encoding="utf-8")

    assert "'Not detected'" not in app_js
    assert "Browser-local processing is available for Merge, Split / extract, Remove pages, and Rotate PDF; other tools use server processing." in index_html
    assert "ephemeral and zero-upload" not in index_html.lower()

    for operation in server.OPERATION_SLUGS:
        context = server.seo_page_context(operation=operation)
        combined = " ".join([context["description"], context["intro"], *(answer for _, answer in context["faqs"])])
        if operation not in {"merge", "split", "remove", "rotate"}:
            assert "zero-upload" not in combined.lower()
            assert "browser-local processing is available for supported operations" not in combined.lower()


def test_spa_seo_refresh_guards_stale_responses_and_updates_the_page_title():
    root = Path(__file__).resolve().parent.parent
    app_js = (root / "web" / "assets" / "app.js").read_text(encoding="utf-8")

    assert "let seoContentRequestVersion = 0;" in app_js
    assert "requestVersion === seoContentRequestVersion && state.operation === operation" in app_js
    assert "document.title = `${operationLabel} | Paperplane`;" in app_js
    assert "if (!isCurrentRequest()) return;" in app_js
    assert "section.innerHTML = `" in app_js
    assert "section.removeAttribute('aria-busy');" in app_js
    assert "Could not refresh SEO content for operation:" in app_js


def test_studio_page_jump_scrolls_to_target_before_render_and_shows_accurate_status():
    root = Path(__file__).resolve().parent.parent
    app_js = (root / "web" / "assets" / "app.js").read_text(encoding="utf-8")

    jump_function = app_js.split("async function jumpToStudioPage", 1)[1].split("const studioPageStack", 1)[0]
    assert "loading.textContent = `Loading page ${target}…`" in jump_function
    assert jump_function.index("alignStudioPageInViewport(slot, behavior)") < jump_function.index("await renderStudioPage(target")
    assert "will render as you scroll" not in app_js
    assert "preview is paused to keep Studio responsive" in app_js
