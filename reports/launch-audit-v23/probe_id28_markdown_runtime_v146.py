"""Time Markdown page extraction phases without printing document text."""
from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

import fitz

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path("C:/Users/mdham/Downloads/notes.pdf")
OUT = Path(__file__).resolve().parent / "probe-id28-markdown-runtime-v146.json"
started = perf_counter()
with fitz.open(SOURCE) as document:
    phases = []
    for number, page in enumerate(document, 1):
        page_started = perf_counter()
        tables = page.find_tables()
        table_elapsed = perf_counter() - page_started
        text_started = perf_counter()
        raw = page.get_text("rawdict", sort=True)
        text_elapsed = perf_counter() - text_started
        phases.append({"page": number, "find_tables_seconds": round(table_elapsed, 4),
                       "rawdict_seconds": round(text_elapsed, 4),
                       "table_count": len(tables.tables), "block_count": len(raw.get("blocks", []))})
        OUT.write_text(json.dumps({"pages": len(document), "processed_pages": number,
                                   "elapsed_seconds": round(perf_counter() - started, 3),
                                   "phases": phases}, indent=2), encoding="utf-8")
        print(json.dumps(phases[-1]), flush=True)
print(json.dumps({"pages": len(phases), "elapsed_seconds": round(perf_counter() - started, 3), "evidence": OUT.name}))
