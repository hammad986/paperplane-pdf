"""Validate PDF/A metadata in the two current production-image browser outputs."""
from __future__ import annotations

import json
from pathlib import Path
import xml.etree.ElementTree as ET

import fitz
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
FIXTURE_ROOT = OUT / "docker-catalog-fixtures-current-v147-20261119-catalog-v147-recheck-2026-11-21" / "outputs"
XMP_NS = "http://www.aiim.org/pdfa/ns/id/"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"


def main() -> int:
    rounds = []
    for round_number in (1, 2):
        path = FIXTURE_ROOT / f"round-{round_number}" / "notes-69page_pdf_to_pdfa.pdf"
        assert path.is_file(), path
        reader = PdfReader(str(path), strict=True)
        assert len(reader.pages) == 69
        root = reader.trailer["/Root"]
        xmp_ref = root.get("/Metadata")
        assert xmp_ref is not None
        xmp = ET.fromstring(xmp_ref.get_object().get_data())
        description = next(
            item for item in xmp.findall(f".//{{{RDF_NS}}}Description")
            if f"{{{XMP_NS}}}part" in item.attrib
        )
        pdfa_part = description.attrib[f"{{{XMP_NS}}}part"]
        pdfa_conformance = description.attrib[f"{{{XMP_NS}}}conformance"]
        assert (pdfa_part, pdfa_conformance) == ("1", "B"), (pdfa_part, pdfa_conformance)
        intents = root.get("/OutputIntents")
        assert intents and len(intents) == 1
        intent = intents[0].get_object()
        profile = intent.get("/DestOutputProfile").get_object()
        assert intent.get("/S") == "/GTS_PDFA1"
        assert intent.get("/OutputConditionIdentifier") == "sRGB"
        assert profile.get("/N") == 3 and len(profile.get_data()) > 0
        assert "Ghostscript" in str(reader.metadata.get("/Producer", ""))
        with fitz.open(path) as document:
            page_text = [page.get_text() for page in document]
        assert "Page 1 of 69" in page_text[0]
        assert "Page 69 of 69" in page_text[-1]
        rounds.append({
            "round": round_number,
            "file": str(path.relative_to(ROOT)),
            "bytes": path.stat().st_size,
            "pages": len(reader.pages),
            "pdfa_part": pdfa_part,
            "pdfa_conformance": pdfa_conformance,
            "output_intent": str(intent.get("/S")),
            "output_condition": str(intent.get("/OutputConditionIdentifier")),
            "icc_components": profile.get("/N"),
            "icc_profile_bytes": len(profile.get_data()),
            "producer": str(reader.metadata.get("/Producer")),
            "first_last_page_markers_preserved": True,
        })
    evidence = {
        "source_browser_evidence": "browser-id28-v147-current-image-catalog-catalog-v147-recheck-2026-11-21.json",
        "validation": "pypdf strict parse + XMP PDF/A-1b + GTS_PDFA1 sRGB ICC output intent + PyMuPDF page-marker checks",
        "rounds": rounds,
    }
    destination = OUT / "id25-current-v147-pdfa-structure.json"
    destination.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
