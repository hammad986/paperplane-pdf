from __future__ import annotations

import json
from pathlib import Path

from catalog_output_audit import verify_output


ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "catalog-outputs"


def main() -> None:
    path = ROOT / "catalog-output-audit.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    operations = {
        "pdf_to_word": (OUTPUTS / "pdf_to_word.docx", ".docx"),
        "pdf_to_excel": (OUTPUTS / "pdf_to_excel.xlsx", ".xlsx"),
        "pdf_to_powerpoint": (OUTPUTS / "pdf_to_powerpoint.pptx", ".pptx"),
    }
    rechecks = {}
    by_name = {item["operation"]: item for item in report["results"]}
    for operation, (output_path, extension) in operations.items():
        content = output_path.read_bytes()
        verification = verify_output(operation, content, extension)
        record = by_name[operation]
        record.update({
            "status": "completed" if verification.get("verified") else "verification_failed",
            "output_bytes": len(content),
            "output_path": str(output_path),
            "verification": verification,
        })
        record.pop("error", None)
        rechecks[operation] = {"verified": verification.get("verified"), "verification": verification}
    report["saved_output_rechecks"] = rechecks
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({name: value["verified"] for name, value in rechecks.items()}, indent=2))


if __name__ == "__main__":
    main()
