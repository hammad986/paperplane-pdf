"""
Paperplane PDF — Phase 4 Automated Test Suite
================================================
Comprehensive tests for:
1. OCR Engine (scanned, hybrid, multilingual, selectable text layer injection, API)
2. Compression Engine (all 5 presets: extreme, high, balanced, high_quality, lossless, target size, analyze, API)
3. Repair Engine (validate-only, xref rebuild, truncated recovery, unrecoverable safe error, API)
4. Security & Resource Integrity (magic byte enforcement, temp cleanup, memory safety)
"""

import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import fitz  # PyMuPDF
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

import converters
import server


class TestPhase4Engine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(server.app)
        cls.temp_dir = Path(tempfile.mkdtemp())

        # Create a synthetic pure scanned PDF (image only, 0 native text)
        cls.scanned_pdf = cls.temp_dir / "scanned_doc.pdf"
        img1 = Image.new("RGB", (600, 200), color="white")
        draw1 = ImageDraw.Draw(img1)
        draw1.text((30, 40), "Paperplane Scanned Document OCR Test", fill="black")
        draw1.text((30, 90), "First line of high fidelity scanned text", fill="black")
        img_path1 = cls.temp_dir / "scan1.png"
        img1.save(img_path1)

        doc = fitz.open()
        p1 = doc.new_page(width=600, height=200)
        p1.insert_image(p1.rect, filename=str(img_path1))

        # Page 2: another scan
        img2 = Image.new("RGB", (600, 200), color="white")
        draw2 = ImageDraw.Draw(img2)
        draw2.text((30, 50), "Second Page Scanned Content For Testing", fill="black")
        img_path2 = cls.temp_dir / "scan2.png"
        img2.save(img_path2)
        p2 = doc.new_page(width=600, height=200)
        p2.insert_image(p2.rect, filename=str(img_path2))

        doc.save(str(cls.scanned_pdf))
        doc.close()

        # Create a pure text PDF (native searchable text, 0 images)
        cls.text_pdf = cls.temp_dir / "native_text.pdf"
        tdoc = fitz.open()
        tp = tdoc.new_page(width=600, height=400)
        tp.insert_text(fitz.Point(50, 100), "This is pure native searchable PDF text without images.", fontsize=14)
        tdoc.save(str(cls.text_pdf))
        tdoc.close()

        # Create an image-heavy PDF for compression benchmarks
        cls.heavy_pdf = cls.temp_dir / "heavy_images.pdf"
        hdoc = fitz.open()
        for i in range(3):
            hp = hdoc.new_page(width=800, height=1000)
            # Create a 2000x2500 high-res image
            big_img = Image.new("RGB", (1800, 2200), color=(200, 220, 240))
            bdraw = ImageDraw.Draw(big_img)
            bdraw.rectangle([(100, 100), (1700, 2100)], fill=(50, 100, 150), outline="black", width=10)
            bdraw.text((200, 300), f"High Resolution Heavy Page {i+1}", fill="white")
            bpath = cls.temp_dir / f"big_{i}.jpg"
            big_img.save(bpath, format="JPEG", quality=95)
            hp.insert_image(hp.rect, filename=str(bpath))
        hdoc.save(str(cls.heavy_pdf))
        hdoc.close()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    # =========================================================================
    # 1. OCR ENGINE TESTS
    # =========================================================================

    def test_01_installed_ocr_languages_discovery(self):
        """Verify that installed OCR languages are discovered from tessdata and returned."""
        langs = converters.get_installed_ocr_languages()
        self.assertIsInstance(langs, list)
        self.assertGreater(len(langs), 0)
        codes = [l["code"] for l in langs]
        self.assertIn("eng", codes)
        for l in langs:
            self.assertTrue(l["installed"])
            self.assertIn("name", l)

    def test_02_api_studio_ocr_languages_endpoint(self):
        """Verify GET /api/studio/ocr/languages endpoint returns installed languages."""
        resp = self.client.get("/api/studio/ocr/languages")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        codes = [l["code"] for l in data["languages"]]
        self.assertIn("eng", codes)

    def test_03_ocr_scanned_pdf_produces_searchable_text_layer(self):
        """CRITICAL: Test that a pure image PDF gains real searchable and selectable text."""
        out_pdf = self.temp_dir / "ocr_output_full.pdf"

        # Check before OCR: native text must be empty
        pre_doc = fitz.open(str(self.scanned_pdf))
        self.assertEqual(pre_doc[0].get_text().strip(), "")
        pre_doc.close()

        # Run OCR
        report = converters.ocr_pdf(self.scanned_pdf, out_pdf, language="eng", dpi=150)
        self.assertTrue(report["success"])
        self.assertEqual(report["pages_processed"], 2)
        self.assertEqual(report["pages_ocrd"], 2)
        self.assertGreater(report["extracted_chars"], 20)

        # Inspect resulting PDF
        post_doc = fitz.open(str(out_pdf))
        self.assertEqual(len(post_doc), 2)
        p1_text = post_doc[0].get_text()
        p2_text = post_doc[1].get_text()
        post_doc.close()

        # Verify real searchable text exists on both pages
        self.assertIn("Paperplane", p1_text)
        self.assertIn("Scanned", p1_text)
        self.assertIn("Second", p2_text)

    def test_04_ocr_hybrid_detection_and_scanned_only_mode(self):
        """Test that in scanned_only mode, existing native text pages are not redundantly OCR'd."""
        out_pdf = self.temp_dir / "ocr_hybrid_test.pdf"
        report = converters.ocr_pdf(self.text_pdf, out_pdf, language="eng", mode="scanned_only")
        self.assertEqual(report["pages_processed"], 1)
        self.assertEqual(report["pages_ocrd"], 0)
        self.assertEqual(report["pages_already_searchable"], 1)

    def test_05_ocr_selected_pages(self):
        """Verify that only specified pages are processed when requested."""
        out_pdf = self.temp_dir / "ocr_page2_only.pdf"
        report = converters.ocr_pdf(self.scanned_pdf, out_pdf, language="eng", pages=[2])
        self.assertEqual(report["pages_processed"], 1)
        self.assertEqual(report["pages_ocrd"], 1)

        post_doc = fitz.open(str(out_pdf))
        # Page 1 was not OCR'd
        self.assertEqual(post_doc[0].get_text().strip(), "")
        # Page 2 was OCR'd
        self.assertIn("Second", post_doc[1].get_text())
        post_doc.close()

    def test_06_ocr_missing_language_safety(self):
        """Verify that requesting an uninstalled OCR language fails cleanly without silent fallback."""
        out_pdf = self.temp_dir / "ocr_bad_lang.pdf"
        with self.assertRaises(ValueError) as ctx:
            converters.ocr_pdf(self.scanned_pdf, out_pdf, language="non_existent_lang")
        self.assertIn("Required OCR language data", str(ctx.exception))

    def test_07_api_studio_ocr_endpoint(self):
        """Test POST /api/studio/ocr returns valid PDF with detailed diagnostic headers."""
        with open(self.scanned_pdf, "rb") as f:
            resp = self.client.post(
                "/api/studio/ocr",
                files={"file": ("scanned.pdf", f, "application/pdf")},
                data={"language": "eng", "pages": "all", "mode": "all", "dpi": "150"}
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["content-type"], "application/pdf")
        self.assertIn("X-Pages-OCRed", resp.headers)
        self.assertEqual(resp.headers["X-Pages-OCRed"], "2")
        self.assertIn("X-Extracted-Chars", resp.headers)

        doc = fitz.open(stream=resp.content, filetype="pdf")
        self.assertEqual(len(doc), 2)
        self.assertIn("Paperplane", doc[0].get_text())
        doc.close()

    # =========================================================================
    # 2. COMPRESSION ENGINE TESTS
    # =========================================================================

    def test_08_analyze_pdf_compression(self):
        """Verify pre-compression analysis reports images and opportunities."""
        analysis = converters.analyze_pdf_compression(self.heavy_pdf)
        self.assertEqual(analysis["page_count"], 3)
        self.assertEqual(analysis["total_images"], 3)
        self.assertGreater(analysis["high_res_images"], 0)
        self.assertIn("estimated_reduction", analysis)

    def test_09_api_studio_compress_analyze_endpoint(self):
        """Verify POST /api/studio/compress/analyze returns JSON structure."""
        with open(self.heavy_pdf, "rb") as f:
            resp = self.client.post(
                "/api/studio/compress/analyze",
                files={"file": ("heavy.pdf", f, "application/pdf")}
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["analysis"]["page_count"], 3)
        self.assertEqual(data["analysis"]["total_images"], 3)

    def test_10_compress_extreme_preset(self):
        """Verify extreme preset significantly reduces image-heavy PDF size."""
        out_pdf = self.temp_dir / "compressed_extreme.pdf"
        rep = converters.compress_pdf(self.heavy_pdf, out_pdf, preset="extreme")
        self.assertTrue(rep["validation_passed"])
        self.assertEqual(rep["preset_used"], "extreme")
        self.assertEqual(rep["page_count"], 3)
        self.assertGreater(rep["saved_bytes"], 0)
        self.assertGreater(rep["percent_saved"], 20.0)

        # Output must be a valid PDF
        doc = fitz.open(str(out_pdf))
        self.assertEqual(len(doc), 3)
        doc.close()

    def test_11_compress_all_presets_and_lossless(self):
        """Verify balanced, high_quality, and lossless presets maintain integrity."""
        for preset in ["balanced", "high_quality", "lossless"]:
            out_pdf = self.temp_dir / f"compressed_{preset}.pdf"
            rep = converters.compress_pdf(self.heavy_pdf, out_pdf, preset=preset)
            self.assertTrue(rep["validation_passed"])
            self.assertEqual(rep["preset_used"], preset)
            self.assertEqual(rep["page_count"], 3)

            doc = fitz.open(str(out_pdf))
            self.assertEqual(len(doc), 3)
            doc.close()

    def test_12_compress_target_size_mode(self):
        """Verify target-size mode adapts compression to approach target byte limit."""
        out_pdf = self.temp_dir / "compressed_target.pdf"
        orig_size = self.heavy_pdf.stat().st_size
        target_bytes = orig_size // 3

        rep = converters.compress_pdf(
            self.heavy_pdf, out_pdf,
            preset="balanced",
            target_size_bytes=target_bytes
        )
        self.assertIsNotNone(rep["target_size_requested"])
        self.assertTrue(rep["validation_passed"])
        self.assertLess(out_pdf.stat().st_size, orig_size)

    def test_13_api_studio_compress_endpoint(self):
        """Verify POST /api/studio/compress returns streaming PDF with size metrics."""
        with open(self.heavy_pdf, "rb") as f:
            resp = self.client.post(
                "/api/studio/compress",
                files={"file": ("heavy.pdf", f, "application/pdf")},
                data={"preset": "high"}
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["content-type"], "application/pdf")
        self.assertIn("X-Saved-Bytes", resp.headers)
        self.assertIn("X-Percent-Saved", resp.headers)
        self.assertEqual(resp.headers["X-Preset-Used"], "high")

        doc = fitz.open(stream=resp.content, filetype="pdf")
        self.assertEqual(len(doc), 3)
        doc.close()

    # =========================================================================
    # 3. PDF REPAIR ENGINE TESTS
    # =========================================================================

    def test_14_repair_validate_only_healthy_document(self):
        """Verify repair validate_only correctly identifies a healthy well-formed PDF."""
        rep = converters.repair_pdf_advanced(self.text_pdf, self.temp_dir / "rep_none.pdf", mode="validate_only")
        self.assertTrue(rep["valid"])
        self.assertFalse(rep["repaired"])
        self.assertEqual(len(rep["detected_issues"]), 0)
        self.assertEqual(rep["recovered_pages"], 1)

    def test_15_api_studio_repair_validate_only_endpoint(self):
        """Verify POST /api/studio/repair with mode=validate_only returns JSON diagnostic report."""
        with open(self.text_pdf, "rb") as f:
            resp = self.client.post(
                "/api/studio/repair",
                files={"file": ("test.pdf", f, "application/pdf")},
                data={"mode": "validate_only"}
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["report"]["valid"])

    def test_16_repair_corrupted_xref_pdf(self):
        """Verify repair rebuilds and recovers a document with corrupted XREF structure."""
        # Create a corrupted PDF by corrupting the xref table
        raw_bytes = bytearray(self.text_pdf.read_bytes())
        # Corrupt xref offset keyword
        xref_pos = raw_bytes.rfind(b"startxref")
        if xref_pos != -1:
            raw_bytes[xref_pos:xref_pos+9] = b"startxxxx"

        corrupted_path = self.temp_dir / "corrupted_xref.pdf"
        corrupted_path.write_bytes(raw_bytes)

        repaired_path = self.temp_dir / "repaired_xref.pdf"
        rep = converters.repair_pdf_advanced(corrupted_path, repaired_path, mode="automatic")
        self.assertTrue(rep["valid"])
        self.assertTrue(rep["repaired"])
        self.assertGreaterEqual(rep["recovered_pages"], 1)

        # Verify output opens cleanly
        doc = fitz.open(str(repaired_path))
        self.assertEqual(len(doc), 1)
        self.assertIn("searchable", doc[0].get_text())
        doc.close()

    def test_17_repair_truncated_pdf_stream_salvage(self):
        """Verify repair recovers surviving pages from a truncated multi-page document."""
        # Create 3-page document and truncate the last 30%
        temp_multi = self.temp_dir / "multi_doc.pdf"
        mdoc = fitz.open()
        for i in range(3):
            p = mdoc.new_page(width=400, height=300)
            p.insert_text(fitz.Point(30, 50), f"Surviving Page Number {i+1}", fontsize=16)
        mdoc.save(str(temp_multi))
        mdoc.close()

        multi_bytes = temp_multi.read_bytes()
        truncated_bytes = multi_bytes[:int(len(multi_bytes) * 0.75)]
        truncated_path = self.temp_dir / "truncated.pdf"
        truncated_path.write_bytes(truncated_bytes)

        repaired_path = self.temp_dir / "repaired_truncated.pdf"
        rep = converters.repair_pdf_advanced(truncated_path, repaired_path, mode="advanced")
        self.assertTrue(rep["repaired"])
        self.assertGreaterEqual(rep["recovered_pages"], 1)

        # Output must open and contain surviving text
        doc = fitz.open(str(repaired_path))
        self.assertGreaterEqual(len(doc), 1)
        self.assertIn("Surviving Page", doc[0].get_text())
        doc.close()

    def test_18_repair_unrecoverable_garbage_safely_errors(self):
        """Verify that total binary garbage cannot be repaired and raises an informative error."""
        junk_path = self.temp_dir / "junk.pdf"
        junk_path.write_bytes(b"RANDOM NON-PDF BINARY JUNK DATA THAT CANNOT BE SALVAGED AT ALL")
        rep_out = self.temp_dir / "repaired_junk.pdf"

        with self.assertRaises(ValueError):
            converters.repair_pdf_advanced(junk_path, rep_out, mode="automatic")

    # =========================================================================
    # 4. SECURITY & INTEGRATION TESTS
    # =========================================================================

    def test_19_api_studio_invalid_file_rejected(self):
        """Verify non-PDF uploads are rejected by Phase 4 endpoints with HTTP 422."""
        junk_bytes = b"Plain text not a PDF"
        for endpoint in ["/api/studio/ocr", "/api/studio/compress", "/api/studio/compress/analyze"]:
            resp = self.client.post(
                endpoint,
                files={"file": ("test.txt", io.BytesIO(junk_bytes), "text/plain")}
            )
            self.assertEqual(resp.status_code, 422, f"Endpoint {endpoint} should return 422 for non-PDF")

    def test_20_process_job_queue_integration(self):
        """Verify server.process() correctly handles compress, repair, and ocr operations."""
        job_out_dir = self.temp_dir / "job_test_dir"
        job_out_dir.mkdir(parents=True, exist_ok=True)

        # 1. Test compress in job queue
        res_comp = server.process("compress", [self.heavy_pdf], {"preset": "balanced"}, job_out_dir)
        self.assertTrue(res_comp.exists())
        self.assertGreater(res_comp.stat().st_size, 0)

        # 2. Test repair in job queue
        res_rep = server.process("repair", [self.text_pdf], {"mode": "automatic"}, job_out_dir)
        self.assertTrue(res_rep.exists())
        self.assertGreater(res_rep.stat().st_size, 0)

        # 3. Test OCR in job queue
        res_ocr = server.process("ocr", [self.scanned_pdf], {"language": "eng", "mode": "all"}, job_out_dir)
        self.assertTrue(res_ocr.exists())
        self.assertGreater(res_ocr.stat().st_size, 0)

        # Verify real searchable text was added in job queue OCR
        doc_q = fitz.open(str(res_ocr))
        self.assertIn("Paperplane", doc_q[0].get_text())
        doc_q.close()


if __name__ == "__main__":
    unittest.main()
