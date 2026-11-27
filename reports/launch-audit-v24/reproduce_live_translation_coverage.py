"""Isolate PDF layout capacity from live translation-provider completeness."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import ai_engine  # noqa: E402

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "launch-audit-v23" / "fixtures" / "totpdf-sample-5-pages.pdf"
OUT = HERE / "controlled-translation-five-pages.pdf"

SPANISH = {
    "TotPDF sample": "Muestra de TotPDF",
    "Free local PDF tools": "Herramientas PDF locales gratuitas: nada sale de su dispositivo.",
    "This page exists only": "Esta página existe solo para probar una herramienta. Combínela, divídala, gírela o comprímala.",
    "Every sample file": "TotPDF crea cada archivo de muestra y permite usarlo gratis para pruebas, demostraciones y tutoriales.",
    "No account": "Sin cuenta, sin carga, sin seguimiento.",
}


def complete_batch(batch, *_args, **_kwargs):
    result = {}
    for segment_id, text in batch:
        result[segment_id] = next((value for prefix, value in SPANISH.items() if text.startswith(prefix)), "Texto traducido.")
    return result


def main() -> None:
    ai_engine._translate_text_batch = complete_batch
    report = {}
    error = None
    try:
        ai_engine.translate_pdf_layout(SOURCE, OUT, target_lang="es", report=report)
    except RuntimeError as exc:
        error = str(exc)
    result = {"source": str(SOURCE), "output_exists": OUT.exists(), "error": error, "report": report}
    (HERE / "controlled-translation-five-pages.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
