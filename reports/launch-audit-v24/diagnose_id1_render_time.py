"""Measure current-source translation rendering with a deterministic local provider."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/launch-audit-v24/fixtures/arxiv-1706.03762v7.pdf"
import sys
sys.path.insert(0, str(ROOT))
import ai_engine


def deterministic_provider(blocks, target_language, deadline=None):
    output = {}
    for block_id, source in blocks:
        words = re.findall(r"\w+", source, flags=re.UNICODE)
        if len(words) <= 2:
            translated = "हाँ" if target_language == "Hindi" else "es"
        else:
            translated = f"अनुवादित {block_id}" if target_language == "Hindi" else f"Traducido {block_id}"
        output[block_id] = translated
    return output


def main():
    ai_engine._translate_text_batch = deterministic_provider
    with TemporaryDirectory(prefix="paperplane-id1-render-time-") as tmp:
        started = time.perf_counter()
        report = {}
        output = Path(tmp) / "translated.pdf"
        ai_engine.translate_pdf_layout(SOURCE, output, target_language="Spanish", report=report)
        elapsed = time.perf_counter() - started
        with fitz.open(output) as document:
            output_text = "\n".join(page.get_text() for page in document)
            evidence = {
                "fixture_pages": document.page_count,
                "output_bytes": output.stat().st_size,
                "elapsed_seconds": round(elapsed, 2),
                "blocks_seen": report["blocks_seen"],
                "blocks_translated": report["blocks_translated"],
                "blocks_preserved": report["blocks_preserved"],
                "coverage_percent": round(report["translated_fraction"] * 100, 2),
                "block_coverage_percent": round(report["translated_block_fraction"] * 100, 4),
                "spanish_marker_present": "Traducido" in output_text,
                "replacement_character_absent": "�" not in output_text,
                "warnings": report["warnings"],
                "diagnostic_result": "partial_output_reproduced" if report["blocks_preserved"] else "complete_output",
            }
        (ROOT / "reports/launch-audit-v24/id1-render-time-diagnostic-v206.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
