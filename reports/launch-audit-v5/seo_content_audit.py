from __future__ import annotations

import json
import sys
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import server
from fastapi.testclient import TestClient


OUT = Path(__file__).resolve().parent


class JsonLdParser(HTMLParser):
    """Collect page JSON-LD, which drives each route's rendered workflow copy."""

    def __init__(self) -> None:
        super().__init__()
        self._in_json_ld = False
        self._parts: list[str] = []
        self.blocks: list[str] = []

    def handle_starttag(self, tag, attrs) -> None:
        if tag == "script" and dict(attrs).get("type") == "application/ld+json":
            self._in_json_ld = True
            self._parts = []

    def handle_endtag(self, tag) -> None:
        if tag == "script" and self._in_json_ld:
            self.blocks.append("".join(self._parts))
            self._parts = []
            self._in_json_ld = False

    def handle_data(self, data) -> None:
        if self._in_json_ld:
            self._parts.append(data)


def main() -> None:
    rows = []
    with TestClient(server.app) as client:
        for operation, slug in server.OPERATION_SLUGS.items():
            context = server.seo_page_context(operation)
            response = client.get(f"/{slug}")
            parser = JsonLdParser()
            parser.feed(response.text)
            structured = []
            for block in parser.blocks:
                try:
                    parsed = json.loads(block)
                    structured.extend(parsed.get("@graph", [parsed]))
                except json.JSONDecodeError:
                    continue
            how_to = next((item for item in structured if item.get("@type") == "HowTo"), {})
            faq = next((item for item in structured if item.get("@type") == "FAQPage"), {})
            rendered_steps = [step.get("name") for step in how_to.get("step", [])]
            rendered_faqs = [question.get("name") for question in faq.get("mainEntity", [])]
            section_start = response.text.find('<section class="seo-content"')
            section_end = response.text.find("</section>", section_start)
            visible_section = unescape(response.text[section_start:section_end]) if section_start >= 0 and section_end >= 0 else ""
            title = context.get("heading")
            title_rendered = bool(title and title in visible_section)
            intro_rendered = bool(context.get("intro") and context["intro"] in visible_section)
            steps_match = rendered_steps == list(context.get("how_to", []))
            faqs_match = rendered_faqs == [item[0] for item in context.get("faqs", [])]
            visible_steps_match = all(step in visible_section for step in context.get("how_to", []))
            visible_faqs_match = all(question in visible_section for question, _ in context.get("faqs", []))
            rows.append({
                "operation": operation,
                "route": f"/{slug}",
                "http_status": response.status_code,
                "heading": context.get("heading"),
                "intro": context.get("intro"),
                "steps": context.get("how_to", []),
                "faqs": context.get("faqs", []),
                "related": context.get("related", []),
                "rendered_heading_present": title_rendered,
                "rendered_intro_present": intro_rendered,
                "rendered_how_to_steps": rendered_steps,
                "rendered_steps_match_context": steps_match,
                "rendered_faq_questions": rendered_faqs,
                "rendered_faqs_match_context": faqs_match,
                "visible_steps_match_context": visible_steps_match,
                "visible_faqs_match_context": visible_faqs_match,
                "route_copy_verified": response.status_code == 200 and title_rendered and intro_rendered and steps_match and faqs_match and visible_steps_match and visible_faqs_match,
            })
    target = OUT / "tool-copy-audit.json"
    target.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    missing = [row["route"] for row in rows if not row["heading"] or not row["intro"] or len(row["steps"]) < 3 or len(row["faqs"]) < 3]
    render_failures = [row["route"] for row in rows if not row["route_copy_verified"]]
    print(json.dumps({"tools": len(rows), "missing_content_contract": missing, "render_failures": render_failures, "report": str(target)}, indent=2))
    if missing or render_failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
