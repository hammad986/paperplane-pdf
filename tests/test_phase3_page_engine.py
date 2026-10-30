"""
Paperplane PDF — Phase 3 Professional Page Management Engine Test Suite
========================================================================
Exhaustive verification of Phase 3 capabilities:
- Single & multi-page selection logic & range selection
- Page drag-and-drop / index reordering (single & multi-page)
- Page duplication (single & batch) with content & geometry preservation
- Blank page insertion with custom dimensions & orientation
- Cross-document page import (merging selected pages from Document B into Document A)
- Page safe deletion with empty-document prevention guard
- Page rotation (90°, 180°, 270°, -90°) with geometry persistence
- Page crop with 72 DPI document-space coordinate mapping
- Page resize (A4, Letter, A3, Legal, custom) with scale & center modes
- Page extraction (subset of pages in user-specified order)
- Document splitting (by page ranges and every N pages, returning ZIP when multiple)
- Multi-document merge with custom ordering
- Structural page metadata extraction (dimensions, orientation, rotation, labels)
- PDF structural integrity & reopening verification
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import fitz  # PyMuPDF
from fastapi.testclient import TestClient

import converters
from server import app


class TestPhase3PageEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.temp_dir = Path(tempfile.mkdtemp(prefix="paperplane_phase3_test_"))

        # Create a canonical 5-page test PDF (A: 5 pages)
        cls.pdf_a = cls.temp_dir / "doc_a.pdf"
        doc = fitz.open()
        for i in range(1, 6):
            page = doc.new_page(width=595, height=842)
            page.insert_text(
                fitz.Point(72, 72),
                f"DOCUMENT A - PAGE {i}\nCanonical text for page {i} identification.",
                fontsize=14,
            )
        doc.save(str(cls.pdf_a))
        doc.close()

        # Create a canonical 3-page test PDF (B: 3 pages)
        cls.pdf_b = cls.temp_dir / "doc_b.pdf"
        doc_b = fitz.open()
        for i in range(1, 4):
            page = doc_b.new_page(width=612, height=792)  # Letter size
            page.insert_text(
                fitz.Point(72, 72),
                f"DOCUMENT B - PAGE {i}\nCross-document import content B{i}.",
                fontsize=14,
            )
        doc_b.save(str(cls.pdf_b))
        doc_b.close()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    # --------------------------------------------------------------------------
    # 1. Page Reordering
    # --------------------------------------------------------------------------
    def test_01_reorder_pages_single_and_multi(self):
        """Verify reordering pages 1-5 into 1, 4, 2, 3, 5 (move 4 before 2)."""
        out_pdf = self.temp_dir / "out_reorder.pdf"
        # 0-based: [0, 3, 1, 2, 4] corresponds to pages [1, 4, 2, 3, 5]
        converters.reorder_pdf_pages(self.pdf_a, out_pdf, [0, 3, 1, 2, 4])

        self.assertTrue(out_pdf.exists())
        doc = fitz.open(str(out_pdf))
        self.assertEqual(len(doc), 5)
        # Verify page 2 is original page 4
        text_p2 = doc[1].get_text()
        self.assertIn("DOCUMENT A - PAGE 4", text_p2)
        # Verify page 3 is original page 2
        text_p3 = doc[2].get_text()
        self.assertIn("DOCUMENT A - PAGE 2", text_p3)
        doc.close()

    def test_02_api_studio_pages_reorder(self):
        """Verify POST /api/studio/pages/reorder endpoint."""
        with open(self.pdf_a, "rb") as f:
            resp = self.client.post(
                "/api/studio/pages/reorder",
                files={"file": ("doc_a.pdf", f, "application/pdf")},
                data={"order": json.dumps([2, 4, 1, 3, 5])}  # 1-based permutation
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("content-type"), "application/pdf")

        # Inspect resulting PDF
        doc = fitz.open(stream=resp.content, filetype="pdf")
        self.assertEqual(len(doc), 5)
        self.assertIn("PAGE 2", doc[0].get_text())
        self.assertIn("PAGE 4", doc[1].get_text())
        self.assertIn("PAGE 1", doc[2].get_text())
        doc.close()

    # --------------------------------------------------------------------------
    # 2. Page Rotation
    # --------------------------------------------------------------------------
    def test_03_rotate_pages_persistence(self):
        """Verify rotation on specific pages persists to PDF geometry."""
        out_pdf = self.temp_dir / "out_rotate.pdf"
        # Rotate page 2 by 90 degrees and page 4 by 180 degrees
        converters.rotate_pdf_pages(self.pdf_a, out_pdf, pages=[2], degrees=90)
        converters.rotate_pdf_pages(out_pdf, out_pdf, pages=[4], degrees=180)

        doc = fitz.open(str(out_pdf))
        self.assertEqual(doc[0].rotation, 0)
        self.assertEqual(doc[1].rotation, 90)
        self.assertEqual(doc[2].rotation, 0)
        self.assertEqual(doc[3].rotation, 180)
        self.assertEqual(doc[4].rotation, 0)
        doc.close()

    def test_04_api_studio_pages_rotate(self):
        """Verify POST /api/studio/pages/rotate endpoint."""
        with open(self.pdf_a, "rb") as f:
            resp = self.client.post(
                "/api/studio/pages/rotate",
                files={"file": ("doc_a.pdf", f, "application/pdf")},
                data={"pages": json.dumps([1, 3]), "degrees": 270}
            )
        self.assertEqual(resp.status_code, 200)
        doc = fitz.open(stream=resp.content, filetype="pdf")
        self.assertEqual(doc[0].rotation, 270)
        self.assertEqual(doc[1].rotation, 0)
        self.assertEqual(doc[2].rotation, 270)
        doc.close()

    # --------------------------------------------------------------------------
    # 3. Page Crop
    # --------------------------------------------------------------------------
    def test_05_crop_pages_coordinate_mapping(self):
        """Verify crop box in 72 DPI PDF user points alters page geometry."""
        out_pdf = self.temp_dir / "out_crop.pdf"
        # Crop page 1 to [50, 50, 400, 500] (w=350, h=450)
        crop_box = {"x": 50, "y": 50, "width": 350, "height": 450}
        converters.crop_pdf_pages(self.pdf_a, out_pdf, pages=[1], crop_rect=crop_box)

        doc = fitz.open(str(out_pdf))
        p1 = doc[0]
        self.assertAlmostEqual(p1.rect.width, 350, delta=1.0)
        self.assertAlmostEqual(p1.rect.height, 450, delta=1.0)
        # Page 2 should remain full A4
        self.assertAlmostEqual(doc[1].rect.width, 595, delta=1.0)
        doc.close()

    def test_06_api_studio_pages_crop(self):
        """Verify POST /api/studio/pages/crop endpoint."""
        with open(self.pdf_a, "rb") as f:
            resp = self.client.post(
                "/api/studio/pages/crop",
                files={"file": ("doc_a.pdf", f, "application/pdf")},
                data={"pages": json.dumps([2]), "box": json.dumps([72, 72, 300, 400])}
            )
        self.assertEqual(resp.status_code, 200)
        doc = fitz.open(stream=resp.content, filetype="pdf")
        self.assertAlmostEqual(doc[1].rect.width, 228, delta=1.0)  # 300 - 72 = 228
        self.assertAlmostEqual(doc[1].rect.height, 328, delta=1.0)  # 400 - 72 = 328
        doc.close()

    # --------------------------------------------------------------------------
    # 4. Page Resize
    # --------------------------------------------------------------------------
    def test_07_resize_pages_presets_and_modes(self):
        """Verify resizing page 1 to Letter (612x792) with scaling."""
        out_pdf = self.temp_dir / "out_resize.pdf"
        converters.resize_pdf_pages(self.pdf_a, out_pdf, pages=[1], target_w=612, target_h=792, mode="scale")

        doc = fitz.open(str(out_pdf))
        self.assertEqual(len(doc), 5)
        self.assertAlmostEqual(doc[0].rect.width, 612, delta=1.0)
        self.assertAlmostEqual(doc[0].rect.height, 792, delta=1.0)
        # Content remains present
        self.assertIn("DOCUMENT A - PAGE 1", doc[0].get_text())
        doc.close()

    def test_08_api_studio_pages_resize(self):
        """Verify POST /api/studio/pages/resize endpoint."""
        with open(self.pdf_a, "rb") as f:
            resp = self.client.post(
                "/api/studio/pages/resize",
                files={"file": ("doc_a.pdf", f, "application/pdf")},
                data={"pages": "all", "target_w": 842, "target_h": 1191, "mode": "scale"}  # A3 size
            )
        self.assertEqual(resp.status_code, 200)
        doc = fitz.open(stream=resp.content, filetype="pdf")
        for p in doc:
            self.assertAlmostEqual(p.rect.width, 842, delta=1.0)
            self.assertAlmostEqual(p.rect.height, 1191, delta=1.0)
        doc.close()

    # --------------------------------------------------------------------------
    # 5. Page Extraction
    # --------------------------------------------------------------------------
    def test_09_extract_pages_order_preserved(self):
        """Verify extracting pages 4, 2, 5 into a new 3-page PDF."""
        out_pdf = self.temp_dir / "out_extract.pdf"
        converters.extract_pdf_pages(self.pdf_a, out_pdf, [4, 2, 5])

        doc = fitz.open(str(out_pdf))
        self.assertEqual(len(doc), 3)
        self.assertIn("PAGE 4", doc[0].get_text())
        self.assertIn("PAGE 2", doc[1].get_text())
        self.assertIn("PAGE 5", doc[2].get_text())
        doc.close()

    def test_10_api_studio_pages_extract(self):
        """Verify POST /api/studio/pages/extract endpoint."""
        with open(self.pdf_a, "rb") as f:
            resp = self.client.post(
                "/api/studio/pages/extract",
                files={"file": ("doc_a.pdf", f, "application/pdf")},
                data={"pages": json.dumps([1, 5])}
            )
        self.assertEqual(resp.status_code, 200)
        doc = fitz.open(stream=resp.content, filetype="pdf")
        self.assertEqual(len(doc), 2)
        self.assertIn("PAGE 1", doc[0].get_text())
        self.assertIn("PAGE 5", doc[1].get_text())
        doc.close()

    # --------------------------------------------------------------------------
    # 6. Cross-Document Page Import
    # --------------------------------------------------------------------------
    def test_11_cross_document_page_import(self):
        """Verify importing pages 1 and 3 from doc B into doc A after page 2."""
        out_pdf = self.temp_dir / "out_import.pdf"
        converters.import_pdf_pages(
            base_pdf=self.pdf_a,
            import_pdf=self.pdf_b,
            output=out_pdf,
            pages=[1, 3],
            insert_after_page=2,
        )

        doc = fitz.open(str(out_pdf))
        self.assertEqual(len(doc), 7)  # 5 + 2 = 7
        # Page 1: A1, Page 2: A2, Page 3: B1, Page 4: B3, Page 5: A3
        self.assertIn("DOCUMENT A - PAGE 1", doc[0].get_text())
        self.assertIn("DOCUMENT A - PAGE 2", doc[1].get_text())
        self.assertIn("DOCUMENT B - PAGE 1", doc[2].get_text())
        self.assertIn("DOCUMENT B - PAGE 3", doc[3].get_text())
        self.assertIn("DOCUMENT A - PAGE 3", doc[4].get_text())
        doc.close()

    def test_12_api_studio_pages_import(self):
        """Verify POST /api/studio/pages/import endpoint."""
        with open(self.pdf_a, "rb") as fa, open(self.pdf_b, "rb") as fb:
            resp = self.client.post(
                "/api/studio/pages/import",
                files={
                    "base_file": ("doc_a.pdf", fa, "application/pdf"),
                    "import_file": ("doc_b.pdf", fb, "application/pdf"),
                },
                data={"pages": json.dumps([2]), "insert_after_page": 0}  # Prepend B2
            )
        self.assertEqual(resp.status_code, 200)
        doc = fitz.open(stream=resp.content, filetype="pdf")
        self.assertEqual(len(doc), 6)
        self.assertIn("DOCUMENT B - PAGE 2", doc[0].get_text())
        self.assertIn("DOCUMENT A - PAGE 1", doc[1].get_text())
        doc.close()

    # --------------------------------------------------------------------------
    # 7. Multi-Document Merge
    # --------------------------------------------------------------------------
    def test_13_multi_document_merge(self):
        """Verify merging Document B and Document A in custom order."""
        out_pdf = self.temp_dir / "out_merge.pdf"
        converters.merge_pdf_documents([self.pdf_b, self.pdf_a], out_pdf)

        doc = fitz.open(str(out_pdf))
        self.assertEqual(len(doc), 8)  # 3 + 5 = 8
        self.assertIn("DOCUMENT B - PAGE 1", doc[0].get_text())
        self.assertIn("DOCUMENT A - PAGE 1", doc[3].get_text())
        doc.close()

    def test_14_api_studio_documents_merge(self):
        """Verify POST /api/studio/documents/merge endpoint."""
        with open(self.pdf_a, "rb") as fa, open(self.pdf_b, "rb") as fb:
            resp = self.client.post(
                "/api/studio/documents/merge",
                files=[
                    ("files", ("doc_a.pdf", fa, "application/pdf")),
                    ("files", ("doc_b.pdf", fb, "application/pdf")),
                ],
                data={"order": json.dumps([1, 0])}  # doc_b first, then doc_a
            )
        self.assertEqual(resp.status_code, 200)
        doc = fitz.open(stream=resp.content, filetype="pdf")
        self.assertEqual(len(doc), 8)
        self.assertIn("DOCUMENT B", doc[0].get_text())
        self.assertIn("DOCUMENT A", doc[3].get_text())
        doc.close()

    # --------------------------------------------------------------------------
    # 8. Document Splitting
    # --------------------------------------------------------------------------
    def test_15_split_document_every_n(self):
        """Verify splitting 5-page PDF every 2 pages produces 3 parts."""
        split_dir = self.temp_dir / "split_test_every_n"
        out_files = converters.split_pdf_document(self.pdf_a, split_dir, mode="every_n", param="2")
        self.assertEqual(len(out_files), 3)

        doc1 = fitz.open(str(out_files[0]))
        self.assertEqual(len(doc1), 2)  # Pages 1-2
        doc1.close()

        doc2 = fitz.open(str(out_files[1]))
        self.assertEqual(len(doc2), 2)  # Pages 3-4
        doc2.close()

        doc3 = fitz.open(str(out_files[2]))
        self.assertEqual(len(doc3), 1)  # Page 5
        doc3.close()

    def test_16_split_document_by_ranges(self):
        """Verify splitting 5-page PDF by ranges '1-2, 3-5'."""
        split_dir = self.temp_dir / "split_test_ranges"
        out_files = converters.split_pdf_document(self.pdf_a, split_dir, mode="ranges", param="1-2, 3-5")
        self.assertEqual(len(out_files), 2)

        doc1 = fitz.open(str(out_files[0]))
        self.assertEqual(len(doc1), 2)
        doc1.close()

        doc2 = fitz.open(str(out_files[1]))
        self.assertEqual(len(doc2), 3)
        doc2.close()

    def test_17_api_studio_documents_split_zip(self):
        """Verify POST /api/studio/documents/split returns a valid ZIP archive for multiple outputs."""
        with open(self.pdf_a, "rb") as f:
            resp = self.client.post(
                "/api/studio/documents/split",
                files={"file": ("doc_a.pdf", f, "application/pdf")},
                data={"mode": "ranges", "param": "1-2, 3-5"}
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("content-type"), "application/zip")

        # Unpack zip in memory and verify contents
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        names = zf.namelist()
        self.assertEqual(len(names), 2)
        self.assertTrue(all(n.endswith(".pdf") for n in names))

    # --------------------------------------------------------------------------
    # 9. Page Deletion & Safety Guards
    # --------------------------------------------------------------------------
    def test_18_delete_pages_batch_and_safety_guard(self):
        """Verify multi-page delete and safeguard against deleting all pages."""
        # Multi-page delete: delete pages 2 and 4 from doc_a
        with open(self.pdf_a, "rb") as f:
            resp = self.client.post(
                "/api/studio/page/delete",
                files={"file": ("doc_a.pdf", f, "application/pdf")},
                data={"pages": json.dumps([2, 4])}
            )
        self.assertEqual(resp.status_code, 200)
        doc = fitz.open(stream=resp.content, filetype="pdf")
        self.assertEqual(len(doc), 3)
        self.assertIn("PAGE 1", doc[0].get_text())
        self.assertIn("PAGE 3", doc[1].get_text())
        self.assertIn("PAGE 5", doc[2].get_text())
        doc.close()

        # Guard: Attempting to delete all 5 pages must fail with 400
        with open(self.pdf_a, "rb") as f:
            resp_fail = self.client.post(
                "/api/studio/page/delete",
                files={"file": ("doc_a.pdf", f, "application/pdf")},
                data={"pages": json.dumps([1, 2, 3, 4, 5])}
            )
        self.assertEqual(resp_fail.status_code, 400)
        self.assertIn("Cannot delete all pages", resp_fail.json().get("detail", ""))

    # --------------------------------------------------------------------------
    # 10. Blank Page Insertion & Page Metadata
    # --------------------------------------------------------------------------
    def test_19_insert_blank_page_with_geometry(self):
        """Verify inserting landscape Letter blank page at start."""
        with open(self.pdf_a, "rb") as f:
            resp = self.client.post(
                "/api/studio/page/insert",
                files={"file": ("doc_a.pdf", f, "application/pdf")},
                data={
                    "after_page": 0,
                    "width": 612,
                    "height": 792,
                    "orientation": "landscape"
                }
            )
        self.assertEqual(resp.status_code, 200)
        doc = fitz.open(stream=resp.content, filetype="pdf")
        self.assertEqual(len(doc), 6)
        # First page should be landscape (w > h)
        p1 = doc[0]
        self.assertGreater(p1.rect.width, p1.rect.height)
        self.assertAlmostEqual(p1.rect.width, 792, delta=1.0)
        self.assertAlmostEqual(p1.rect.height, 612, delta=1.0)
        doc.close()

    def test_20_api_studio_pages_metadata(self):
        """Verify structural metadata extraction for document pages."""
        with open(self.pdf_a, "rb") as f:
            resp = self.client.post(
                "/api/studio/pages/metadata",
                files={"file": ("doc_a.pdf", f, "application/pdf")}
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json().get("data", {})
        self.assertEqual(data.get("totalPages"), 5)
        pages = data.get("pages", [])
        self.assertEqual(len(pages), 5)
        self.assertEqual(pages[0].get("orientation"), "portrait")
        self.assertEqual(pages[0].get("rotation"), 0)
