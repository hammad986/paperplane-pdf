"""Stress the current PDF processing path with concurrent synthetic watermark jobs.

This is a diagnostic for ID 28's intermittent queued Watermark stall. It does not
replace an end-to-end browser/production-worker check and does not prove the old
stall is fixed.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ.update(
    PAPERPLANE_SKIP_DOTENV="1",
    PAPERPLANE_ENV="development",
    PAPERPLANE_ADMIN_KEY="synthetic-admin-key-for-test-only",
    PAPERPLANE_ADMIN_CODE="synthetic-admin-code",
    PAPERPLANE_SESSION_SECRET="synthetic-session-secret-for-test-only",
)

import fitz  # noqa: E402


PAGE_COUNT = 20
ROUNDS = 5
CONCURRENCY = 8


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="paperplane-id28-concurrent-watermark-") as temp:
        root = Path(temp)
        # Importing server initializes its persistence/configuration modules.
        # Keep even read-side credential/config checks inside the isolated run.
        os.environ["PAPERPLANE_DATA_DIR"] = str(root / "data")
        import server  # noqa: PLC0415

        source = root / "source.pdf"
        document = fitz.open()
        for page_number in range(1, PAGE_COUNT + 1):
            page = document.new_page()
            page.insert_text((72, 72), f"ID28-CONTENT-PAGE-{page_number:02d}", fontsize=14)
        document.save(source)
        document.close()

        def run_one(job_number: int) -> dict[str, object]:
            output_dir = root / f"job-{job_number}"
            output_dir.mkdir()
            started = time.perf_counter()
            output = server.process(
                "watermark",
                [source],
                {"text": f"ID28-WATERMARK-{job_number}", "opacity": 0.2},
                output_dir,
            )
            with fitz.open(output) as result:
                extracted = "\n".join(page.get_text() for page in result)
                return {
                    "job": job_number,
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                    "pages": result.page_count,
                    "source_markers_preserved": all(
                        f"ID28-CONTENT-PAGE-{page_number:02d}" in extracted
                        for page_number in range(1, PAGE_COUNT + 1)
                    ),
                    "own_watermark_present": f"ID28-WATERMARK-{job_number}" in extracted,
                    "output_bytes": output.stat().st_size,
                }

        results: list[dict[str, object]] = []
        round_results = []
        for round_number in range(1, ROUNDS + 1):
            started = time.perf_counter()
            first_job = (round_number - 1) * CONCURRENCY
            with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
                current = list(pool.map(run_one, range(first_job, first_job + CONCURRENCY)))
            round_result = {
                "round": round_number,
                "concurrency": CONCURRENCY,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "jobs": current,
            }
            round_results.append(round_result)
            results.extend(current)

        evidence = {
            "item": 28,
            "test": "in-process concurrent current-source watermark stress",
            "source_pages": PAGE_COUNT,
            "rounds": ROUNDS,
            "concurrency_per_round": CONCURRENCY,
            "jobs_total": len(results),
            "all_jobs_complete": len(results) == ROUNDS * CONCURRENCY,
            "all_page_counts_preserved": all(row["pages"] == PAGE_COUNT for row in results),
            "all_source_markers_preserved": all(row["source_markers_preserved"] for row in results),
            "all_unique_watermarks_present": all(row["own_watermark_present"] for row in results),
            "max_job_seconds": max(float(row["elapsed_seconds"]) for row in results),
            "round_results": round_results,
            "limitation": "This does not reproduce the intermittent queued-job stall or prove its root cause/fix.",
        }
        destination = Path(__file__).with_name("id28-concurrent-watermark-stress.json")
        destination.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
        return 0 if all(
            evidence[key]
            for key in (
                "all_jobs_complete",
                "all_page_counts_preserved",
                "all_source_markers_preserved",
                "all_unique_watermarks_present",
            )
        ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
