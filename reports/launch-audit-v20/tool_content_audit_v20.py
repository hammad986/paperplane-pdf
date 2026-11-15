"""Exercise the 44-operation catalog twice with synthetic or repository fixtures."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import secrets
import sys
from tempfile import TemporaryDirectory
import time

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

for name in list(os.environ):
    if any(marker in name.upper() for marker in ("KEY", "SECRET", "TOKEN", "PASSWORD", "PAPERPLANE_",
                                                 "SMTP_", "RESEND_", "CASHFREE_", "AI_", "ADMIN_")):
        os.environ.pop(name, None)
os.environ.update(PAPERPLANE_SKIP_DOTENV="1", PAPERPLANE_ENV="development",
                  PAPERPLANE_ADMIN_KEY=secrets.token_urlsafe(64), PAPERPLANE_ADMIN_CODE=secrets.token_urlsafe(32))


def load_previous_checks():
    location = ROOT / "reports/launch-audit-v10/run_tool_content_audit.py"
    # Reuse the existing fixture builders and output validators. Its old entry
    # point and env setup are omitted because they target an older catalog.
    source = location.read_text(encoding="utf-8")
    start, end = source.index("# Isolate this local processor"), source.index("RUNNER_PATH =")
    namespace = {"__file__": str(location), "__name__": "previous_content_checks"}
    exec(compile(source[:start] + source[end:], str(location), "exec"), namespace)
    return namespace


def round_result(number, server, checks, base):
    checks["AUDIT_ROOT"] = base
    runner = checks["load_runner"]()
    samples = checks["make_sample_set"](base / f"round-{number}")
    runner.OUTPUTS = samples["outputs"]
    runner.FORM_SOURCE = samples["form"]
    runner.PASSWORD = secrets.token_urlsafe(24)
    runner.EXPECTED_FIELDS = checks["EXPECTED_FIELDS"]
    catalog = server.get_operations()
    modes = {
        "split": {"pages": "1"}, "remove": {"pages": "1"}, "rotate": {"degrees": 90},
        "organize": {"pages": [{"page": 2}, {"page": 1}]}, "compress": {"preset": "100kb"},
        "edit": {"page": 1, "text": "PAPERPLANE_EDITED_TEXT", "x": 72, "y": 220, "font_size": 12},
        "annotate": {"annotations": [{"type": "text", "page": 1, "point": [72, 420], "text": "ANNOTATION_AUDIT_NOTE"}]},
        "crop": {"left": 18, "top": 18, "right": 18, "bottom": 18},
        "redact": {"terms": "REDACT_THIS_MARKER"}, "watermark": {"text": "AUDIT_WATERMARK"},
        "page_numbers": {"format": "page_of_total", "start_number": 1},
        "sign": {"mode": "visual", "signer_name": "PAPERPLANE AUDIT SIGNATURE"},
        "metadata": {"title": "PAPERPLANE_AUDIT_METADATA", "author": "Synthetic Audit"},
        "ai_chat": {"question": "What marker is written on page two?"},
        "ai_extract": {"document_type": "auto"}, "photo_resizer": {"preset": "ssc_photo", "format": "jpg"},
        "photo_compress": {"target_kb": 50}, "photo_resize": {"width": 350, "height": 450},
        "photo_merge": {"layout": "grid"}, "html_to_pdf": {"url": "http://127.0.0.1:1/"},
        "protect": {"password": runner.PASSWORD, "owner_password": secrets.token_urlsafe(24)},
        "unlock": {"password": runner.PASSWORD}, "forms": {"fields": runner.EXPECTED_FIELDS},
        "flatten": {"flatten": True},
    }
    results = []
    protected = None
    for operation, entry in catalog.items():
        started = time.monotonic()
        if not entry.get("available", False) and operation != "ai_chat":
            results.append({"operation": operation, "status": "unavailable", "reason": entry["prerequisite"]})
            continue
        paths = [samples["pdf"]]
        if operation == "merge":
            paths = [samples["large_pdf"], samples["pdf"]]
        elif operation == "compare":
            paths = [samples["pdf"], samples["changed_pdf"]]
        elif operation in {"scan_pdf", "photo_resizer", "photo_compress", "photo_resize"}:
            paths = [samples["image"]]
        elif operation in {"jpg_to_pdf", "photo_merge"}:
            paths = [samples["image"], samples["image2"]]
        elif operation in {"word_to_pdf", "excel_to_pdf", "powerpoint_to_pdf"}:
            paths = [samples[{"word_to_pdf": "docx", "excel_to_pdf": "xlsx", "powerpoint_to_pdf": "pptx"}[operation]]]
        elif operation in {"forms", "flatten"}:
            paths = [samples["form"]]
        elif operation == "unlock" and protected:
            paths = [protected]
        elif operation in {"split", "remove", "rotate", "compress", "repair", "pdf_to_word", "pdf_to_excel",
                           "pdf_to_powerpoint", "pdf_to_pdfa", "pdf_to_text", "pdf_to_markdown", "grayscale"}:
            paths = [samples["large_pdf"]]
        elif operation == "html_to_pdf":
            paths = []
        record = {"operation": operation}
        try:
            output = server.process(operation, paths, modes.get(operation, {}), runner.OUTPUTS)
            if operation == "protect":
                protected = output
            data = output.read_bytes()
            if operation.startswith("photo_"):
                with Image.open(output) as image:
                    size = image.size
                    image.load()
                verified = (
                    len(data) <= 50 * 1024 if operation == "photo_compress"
                    else size == (350, 450) and (operation != "photo_resizer" or 20 * 1024 <= len(data) <= 50 * 1024)
                    if operation in {"photo_resize", "photo_resizer"} else size[0] > 0 and size[1] > 0
                )
                detail = {"dimensions": size, "verified": verified}
            else:
                detail = checks["verify_output_content"](runner, operation, output, data, output.suffix.lower(), paths)
            record.update(status="completed", bytes=len(data), checks=checks["redact_id_text"](detail))
        except Exception as error:
            if operation == "html_to_pdf" and ("forbidden" in str(error).lower() or "security guard" in str(error).lower()):
                record.update(status="ssrf_blocked")
            else:
                record.update(status="failed", exception=type(error).__name__)
        record["seconds"] = round(time.monotonic() - started, 3)
        results.append(record)
    return {"round": number, "results": results}


def main():
    with TemporaryDirectory(prefix="paperplane-v13-content-") as temp:
        base = Path(temp)
        os.environ["PAPERPLANE_DATA_DIR"] = str(base / "data")
        import server

        checks = load_previous_checks()
        records = []
        for number in (1, 2):
            record = round_result(number, server, checks, base)
            records.append(record)
            statuses = [item["status"] for item in record["results"]]
            print(f"Round {number}: {len(statuses)} catalog entries, "
                  + ", ".join(f"{status}={statuses.count(status)}" for status in sorted(set(statuses))), flush=True)
        (OUT / "tool-content-audit.json").write_text(json.dumps(records, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
