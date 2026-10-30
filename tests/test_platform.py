from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

import fitz
import docx
import openpyxl
import pptx
from fastapi.testclient import TestClient
from PIL import Image

# Import platform modules
import config
from persistence import init_db
from server import app
import converters
import ai_engine


class TestPaperplanePlatform(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        cls.sample_pdf = Path(__file__).parent.parent / "UG" / "CSE.pdf"
        if not cls.sample_pdf.exists():
            cls.sample_pdf.parent.mkdir(parents=True, exist_ok=True)
            import fitz
            doc = fitz.open()
            for p in range(3):
                page = doc.new_page(width=595, height=842)
                page.insert_text(fitz.Point(72, 72), f"Paperplane Test Document - Page {p+1}\nThis is a sample document for automated verification.", fontsize=14)
            doc.save(str(cls.sample_pdf))
            doc.close()
        assert cls.sample_pdf.exists(), f"Sample PDF missing at {cls.sample_pdf}"

    def test_01_operations_catalog(self):
        """Verifies that all operations are available and marked implemented."""
        response = self.client.get("/api/operations")
        self.assertEqual(response.status_code, 200)
        ops = response.json()
        required_ops = [
            "merge", "split", "remove", "rotate", "compress", "repair",
            "jpg_to_pdf", "word_to_pdf", "excel_to_pdf", "powerpoint_to_pdf",
            "pdf_to_jpg", "pdf_to_word", "pdf_to_excel", "pdf_to_powerpoint",
            "pdf_to_pdfa", "pdf_to_text", "pdf_to_markdown", "protect", "unlock",
            "watermark", "page_numbers", "edit", "redact", "sign", "ai_chat", "ai_extract"
        ]
        for op in required_ops:
            self.assertIn(op, ops, f"Operation {op} missing in catalog")
            self.assertTrue(ops[op]["implemented"], f"Operation {op} should be implemented")

    def test_02_auth_and_developer_keys(self):
        """Verifies user registration, login, profile check, and API key generation."""
        test_email = f"test_{os.urandom(4).hex()}@example.com"
        password = "SecurePassword123!"

        # Register
        reg_res = self.client.post("/api/auth/register", data={"email": test_email, "password": password})
        self.assertEqual(reg_res.status_code, 200)
        token = reg_res.json()["token"]
        self.assertTrue(token)

        # Login
        login_res = self.client.post("/api/auth/login", data={"email": test_email, "password": password})
        self.assertEqual(login_res.status_code, 200)
        self.assertEqual(login_res.json()["email"], test_email)

        # Profile
        me_res = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me_res.status_code, 200)
        self.assertTrue(me_res.json()["authenticated"])
        self.assertEqual(me_res.json()["email"], test_email)

        # Generate API key
        key_res = self.client.post("/api/developer/keys", data={"name": "Test Key"}, headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(key_res.status_code, 200)
        api_key = key_res.json()["api_key"]
        key_id = key_res.json()["key_id"]
        self.assertTrue(api_key.startswith("sk_live_"))

        # Verify API key works on guarded endpoint
        list_res = self.client.get("/api/developer/keys", headers={"X-API-Key": api_key})
        self.assertEqual(list_res.status_code, 200)
        keys = list_res.json()["keys"]
        self.assertTrue(any(k["id"] == key_id for k in keys))

        # Revoke API key
        del_res = self.client.delete(f"/api/developer/keys/{key_id}", headers={"X-API-Key": api_key})
        self.assertEqual(del_res.status_code, 200)

    def test_03_word_and_office_converters(self):
        """Tests Word (.docx), Excel (.xlsx), and PPTX (.pptx) converters."""
        temp_dir = Path(tempfile.mkdtemp())
        try:
            # 1. Word to PDF
            doc = docx.Document()
            doc.add_heading("Paperplane Test Document", level=1)
            doc.add_paragraph("This is a paragraph created for conversion testing.")
            table = doc.add_table(rows=2, cols=2)
            table.cell(0, 0).text = "Item"
            table.cell(0, 1).text = "Price"
            table.cell(1, 0).text = "Widget A"
            table.cell(1, 1).text = "$100"
            docx_path = temp_dir / "sample.docx"
            doc.save(str(docx_path))

            pdf_from_word = temp_dir / "sample_word.pdf"
            converters.word_to_pdf(docx_path, pdf_from_word)
            self.assertTrue(pdf_from_word.exists())
            self.assertGreater(pdf_from_word.stat().st_size, 500)

            # 2. PDF to Word
            back_to_docx = temp_dir / "converted_back.docx"
            converters.pdf_to_word(pdf_from_word, back_to_docx)
            self.assertTrue(back_to_docx.exists())
            self.assertGreater(back_to_docx.stat().st_size, 500)

            # 3. Excel to PDF & PDF to Excel
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Financials"
            ws.append(["Quarter", "Revenue", "Profit"])
            ws.append(["Q1", 50000, 12000])
            ws.append(["Q2", 75000, 20000])
            xlsx_path = temp_dir / "financials.xlsx"
            wb.save(str(xlsx_path))

            pdf_from_excel = temp_dir / "financials.pdf"
            converters.excel_to_pdf(xlsx_path, pdf_from_excel)
            self.assertTrue(pdf_from_excel.exists())

            back_to_excel = temp_dir / "extracted_table.xlsx"
            converters.pdf_to_excel(pdf_from_excel, back_to_excel)
            self.assertTrue(back_to_excel.exists())

            # 4. PowerPoint to PDF & PDF to PowerPoint
            prs = pptx.Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[0])
            slide.shapes.title.text = "Presentation Title"
            slide.placeholders[1].text = "Subtitle text here"
            pptx_path = temp_dir / "slides.pptx"
            prs.save(str(pptx_path))

            pdf_from_pptx = temp_dir / "slides.pdf"
            converters.powerpoint_to_pdf(pptx_path, pdf_from_pptx)
            self.assertTrue(pdf_from_pptx.exists())

            back_to_pptx = temp_dir / "slides_from_pdf.pptx"
            converters.pdf_to_powerpoint(pdf_from_pptx, back_to_pptx)
            self.assertTrue(back_to_pptx.exists())

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_04_core_pdf_operations(self):
        """Tests PDF Merge, Split, Compression, and Repair."""
        temp_dir = Path(tempfile.mkdtemp())
        try:
            # 1. Merge
            with open(self.sample_pdf, "rb") as f1, open(self.sample_pdf, "rb") as f2:
                res = self.client.post(
                    "/api/jobs",
                    data={"operation": "merge", "options": "{}"},
                    files=[("files", ("c1.pdf", f1, "application/pdf")), ("files", ("c2.pdf", f2, "application/pdf"))]
                )
            self.assertEqual(res.status_code, 202)
            job_id = res.json()["job_id"]
            
            # Poll status
            import time
            for _ in range(30):
                poll = self.client.get(f"/api/jobs/{job_id}")
                if poll.json()["status"] in ["completed", "failed"]:
                    break
                time.sleep(0.3)
            self.assertEqual(poll.json()["status"], "completed")

            # Download merged
            dl = self.client.get(f"/api/jobs/{job_id}/download")
            self.assertEqual(dl.status_code, 200)
            self.assertGreater(len(dl.content), 1000)

            # 2. Split
            with open(self.sample_pdf, "rb") as f:
                res = self.client.post(
                    "/api/jobs",
                    data={"operation": "split", "options": json.dumps({"pages": "1-2"})},
                    files=[("files", ("doc.pdf", f, "application/pdf"))]
                )
            self.assertEqual(res.status_code, 202)

            # 3. Compression
            comp_out = temp_dir / "compressed.pdf"
            stat = converters.compress_pdf(self.sample_pdf, comp_out, quality=50, max_dpi=100)
            self.assertTrue(comp_out.exists())
            self.assertIn("percent_saved", stat)

            # 4. Repair
            repaired = temp_dir / "repaired.pdf"
            converters.repair_pdf(self.sample_pdf, repaired)
            self.assertTrue(repaired.exists())

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_05_ai_rag_and_metadata_extraction(self):
        """Tests RAG PDF Chat and Invoice/Resume metadata extraction."""
        # 1. AI Chat RAG
        chat_res = ai_engine.chat_with_pdf(self.sample_pdf, "What is the course structure or syllabus?")
        self.assertIn("answer", chat_res)
        self.assertTrue(len(chat_res["answer"]) > 10)

        # 2. AI Metadata Extraction
        meta_res = ai_engine.extract_metadata_entities(self.sample_pdf, doc_type="auto")
        self.assertIn("document_type", meta_res)
        self.assertIn("csv_export", meta_res)

    def test_06_page_organizer_thumbnails(self):
        """Tests thumbnail generation for the visual drag-and-drop page organizer."""
        with open(self.sample_pdf, "rb") as f:
            res = self.client.post(
                "/api/organize/thumbnails",
                files={"file": ("test.pdf", f, "application/pdf")}
            )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("pages", data)
        self.assertTrue(len(data["pages"]) > 0)
        self.assertTrue(data["pages"][0]["thumbnail"].startswith("data:image/png;base64,"))

    def test_07_advanced_ai_and_collaboration(self):
        """Tests Layout-Preserving Translation, Annotations, Image Watermark, and Encrypted Batch Merge."""
        temp_dir = Path(tempfile.mkdtemp())
        try:
            # 1. Layout-Preserving Translation
            trans_out = temp_dir / "translated_es.pdf"
            ai_engine.translate_pdf_layout(self.sample_pdf, trans_out, target_lang="es")
            self.assertTrue(trans_out.exists())
            self.assertGreater(trans_out.stat().st_size, 500)

            # 2. Executive Document Summarization
            summary_text = ai_engine.summarize_pdf(self.sample_pdf)
            self.assertTrue(len(summary_text) > 30)
            self.assertIn("EXECUTIVE SUMMARY", summary_text.upper())

            # 3. PDF Annotations (Highlight, Underline, Sticky Note, Rect)
            annot_out = temp_dir / "annotated.pdf"
            annots = [
                {"type": "highlight", "page": 0, "text": "Computer", "content": "Important Term"},
                {"type": "note", "page": 0, "rect": [100, 100, 200, 200], "content": "Review this chapter"},
                {"type": "rect", "page": 0, "rect": [50, 50, 150, 150], "color": [0, 0.5, 1]}
            ]
            converters.annotate_pdf(self.sample_pdf, annot_out, annotations=annots)
            self.assertTrue(annot_out.exists())

            # 4. Image Watermark
            wm_img = temp_dir / "test_wm.png"
            Image.new("RGBA", (120, 120), (255, 0, 0, 150)).save(wm_img)
            wm_out = temp_dir / "watermarked_img.pdf"
            converters.apply_image_watermark(self.sample_pdf, wm_out, wm_img, opacity=0.3)
            self.assertTrue(wm_out.exists())

            # 5. Encrypted File in Batch Merge
            enc_pdf = temp_dir / "encrypted.pdf"
            writer = fitz.open(str(self.sample_pdf))
            writer.save(str(enc_pdf), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="SecretPassword123!")
            writer.close()

            with open(self.sample_pdf, "rb") as f1, open(enc_pdf, "rb") as f2:
                res = self.client.post(
                    "/api/jobs",
                    data={"operation": "merge", "options": json.dumps({"password": "SecretPassword123!"})},
                    files=[("files", ("plain.pdf", f1, "application/pdf")), ("files", ("locked.pdf", f2, "application/pdf"))]
                )
            self.assertEqual(res.status_code, 202)
            job_id = res.json()["job_id"]
            
            import time
            for _ in range(30):
                poll = self.client.get(f"/api/jobs/{job_id}")
                if poll.json()["status"] in ["completed", "failed"]:
                    break
                time.sleep(0.3)
            self.assertEqual(poll.json()["status"], "completed")

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
