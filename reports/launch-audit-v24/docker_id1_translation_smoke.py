"""Controlled exact-fixture translation smoke inside the production image."""
from __future__ import annotations

import json
import re
from pathlib import Path

import fitz
import ai_engine

SOURCE = Path("/app/arxiv.pdf")
calls = {"requests": 0, "segments": 0}


def deterministic_provider(batch, target_language, deadline=None):
    calls["requests"] += 1
    calls["segments"] += len(batch)
    output = {}
    for segment_id, text in batch:
        if len(re.findall(r"\w+", text, flags=re.UNICODE)) <= 2:
            translated = "हाँ" if target_language == "Hindi" else "es"
        else:
            translated = f"अनुवादित {segment_id}" if target_language == "Hindi" else f"Traducido {segment_id}"
        output[segment_id] = translated
    return output


ai_engine._translate_text_batch = deterministic_provider
results = []
for language, marker in (("Spanish", "Traducido"), ("Hindi", "अनुवादित")):
    output = Path(f"/app/arxiv-{language}.pdf")
    report = {}
    ai_engine.translate_pdf_layout(SOURCE, output, target_language=language, report=report)
    with fitz.open(output) as pdf:
        texts = [page.get_text() for page in pdf]
        marker_pages = sum(
            marker in text or (language == "Spanish" and "es" in text)
            or (language == "Hindi" and "हाँ" in text)
            for text in texts
        )
        results.append({
            "language": language,
            "status": report["translation_status"],
            "pages": pdf.page_count,
            "character_coverage_percent": round(report["translated_fraction"] * 100, 2),
            "block_coverage_percent": round(report["translated_block_fraction"] * 100, 2),
            "blocks": report["blocks_seen"],
            "blocks_translated": report["blocks_translated"],
            "blocks_preserved": report["blocks_preserved"],
            "segments": report["text_segments_seen"],
            "provider_requests": calls["requests"],
            "provider_segments": calls["segments"],
            "target_marker_pages": marker_pages,
            "output_bytes": output.stat().st_size,
            "warnings": report["warnings"],
        })
    calls.update(requests=0, segments=0)

print(json.dumps(results, ensure_ascii=False))
if any(
    result["status"] not in {"translated", "partial"}
    or result["pages"] != 15
    or result["character_coverage_percent"] < 50
    or result["block_coverage_percent"] < 50
    or result["target_marker_pages"] != 15
    for result in results
):
    raise SystemExit(1)
