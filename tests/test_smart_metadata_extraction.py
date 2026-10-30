import csv
import io
import unittest
from pathlib import Path
import fitz
from fastapi.testclient import TestClient

from persistence import init_db
from server import app
import ai_engine


class TestSmartMetadataExtraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        cls.test_dir = Path(__file__).parent / "fixtures"
        cls.test_dir.mkdir(parents=True, exist_ok=True)

        # 1. Build Ground-Truth Invoice PDF
        cls.invoice_pdf = cls.test_dir / "sample_invoice.pdf"
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        invoice_text = """Acme Software Systems Inc.
100 Innovation Way, Suite 400
San Francisco, CA 94105
Email: billing@acmecorp.com | Phone: (555) 839-2001

TAX INVOICE

Invoice Number: INV-2026-8891
Invoice Date: 2026-10-14
Due Date: 2026-11-14
Payment Terms: Net 30 Days

Bill To: Globex International LLC
742 Evergreen Terrace
Springfield, OR 97477

Description                     Quantity  Unit Price  Total Amount
Cloud Hosting Enterprise Tier          2     $150.00       $300.00
Dedicated Engineering SLA              1     $200.00       $200.00

Subtotal: $500.00
Sales Tax: $50.00
Grand Total: $550.00

Thank you for your business! Please remit payment via ACH or Wire.
"""
        page.insert_text(fitz.Point(50, 60), invoice_text, fontsize=10)
        doc.save(str(cls.invoice_pdf))
        doc.close()

        # 2. Build Ground-Truth Resume PDF
        cls.resume_pdf = cls.test_dir / "sample_resume.pdf"
        doc2 = fitz.open()
        page2 = doc2.new_page(width=595, height=842)
        resume_text = """Jane Doe
Senior Full-Stack Cloud Architect
Email: jane.doe@example.com | Phone: (555) 234-5678
San Francisco, CA

PROFESSIONAL SUMMARY
Experienced architect with 10+ years specializing in distributed systems, FastAPI, and Kubernetes.

TECHNICAL SKILLS
Languages & Frameworks: Python, TypeScript, React, Node.js, FastAPI, SQL, Go
Infrastructure: Docker, Kubernetes, AWS, PostgreSQL, MongoDB, Git, CI/CD

WORK EXPERIENCE
Principal Engineer - Enterprise Cloud Solutions (2021 - Present)
- Architected high-throughput microservices using FastAPI and Docker.

Senior Developer - Tech Innovators Corp (2017 - 2021)
- Built modern React interfaces and PostgreSQL relational database schemas.

EDUCATION
Bachelor of Science in Computer Science - University of California (2013 - 2017)
"""
        page2.insert_text(fitz.Point(50, 60), resume_text, fontsize=10)
        doc2.save(str(cls.resume_pdf))
        doc2.close()

    def test_01_extract_invoice_ground_truth(self):
        """Verifies canonical schema, invoice fields, line items, and contacts from ground-truth invoice."""
        res = ai_engine.extract_metadata_entities(self.invoice_pdf, doc_type="auto")
        self.assertEqual(res["document_type"], "invoice")
        self.assertEqual(res["total_pages"], 1)

        inv = res["invoice_data"]
        self.assertEqual(inv["invoice_number"], "INV-2026-8891")
        self.assertEqual(inv["invoice_date"], "2026-10-14")
        self.assertEqual(inv["due_date"], "2026-11-14")
        self.assertEqual(inv["currency"], "USD")
        self.assertEqual(inv["total_amount"], 550.0)
        self.assertEqual(inv["subtotal"], 500.0)
        self.assertEqual(inv["tax_amount"], 50.0)
        self.assertIn("Globex International", inv["customer"])

        # Line items verification
        self.assertGreaterEqual(len(inv["line_items"]), 2)
        self.assertIn("Cloud Hosting", inv["line_items"][0]["description"])
        self.assertEqual(inv["line_items"][0]["amount"], 300.0)
        self.assertIn("Dedicated Engineering", inv["line_items"][1]["description"])
        self.assertEqual(inv["line_items"][1]["amount"], 200.0)

        # Contact info
        self.assertIn("billing@acmecorp.com", res["contact"]["emails"])
        self.assertTrue(any("839" in p for p in res["contact"]["phones"]))

        # RFC-4180 CSV export
        self.assertIn("csv_export", res)
        reader = list(csv.reader(io.StringIO(res["csv_export"])))
        self.assertGreater(len(reader), 1)
        self.assertIn("InvoiceNumber", reader[0])
        self.assertIn("INV-2026-8891", reader[1])

    def test_02_extract_resume_ground_truth(self):
        """Verifies candidate name, skills, contact, and experience from ground-truth resume."""
        res = ai_engine.extract_metadata_entities(self.resume_pdf, doc_type="auto")
        self.assertEqual(res["document_type"], "resume")

        resume = res["resume_data"]
        self.assertEqual(resume["candidate_name"], "Jane Doe")
        self.assertIn("Python", resume["skills"])
        self.assertIn("FastAPI", resume["skills"])
        self.assertIn("Docker", resume["skills"])
        self.assertIn("Kubernetes", resume["skills"])
        self.assertIn("React", resume["skills"])
        self.assertIn("jane.doe@example.com", res["contact"]["emails"])

        # CSV export
        self.assertIn("csv_export", res)
        reader = list(csv.reader(io.StringIO(res["csv_export"])))
        self.assertEqual(reader[0][0], "CandidateName")
        self.assertEqual(reader[1][0], "Jane Doe")

    def test_03_extract_api_endpoint(self):
        """Verifies HTTP POST /api/ai/extract returns valid canonical payload."""
        with open(self.invoice_pdf, "rb") as f:
            resp = self.client.post(
                "/api/ai/extract",
                files={"file": ("invoice.pdf", f, "application/pdf")},
                data={"doc_type": "invoice"}
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "success")
        data = body["data"]
        self.assertEqual(data["document_type"], "invoice")
        self.assertEqual(data["invoice_data"]["invoice_number"], "INV-2026-8891")
        self.assertEqual(data["invoice_data"]["total_amount"], 550.0)

    def test_04_extract_scanned_or_empty_pdf_warning(self):
        """Verifies that an empty or scanned PDF triggers an honest digital text warning."""
        empty_pdf = self.test_dir / "empty_doc.pdf"
        doc = fitz.open()
        doc.new_page(width=595, height=842)  # Blank page
        doc.save(str(empty_pdf))
        doc.close()

        res = ai_engine.extract_metadata_entities(empty_pdf, doc_type="auto")
        self.assertTrue(len(res["warnings"]) > 0)
        self.assertTrue(any("scanned" in w.lower() or "no extractable digital text" in w.lower() for w in res["warnings"]))

    def test_05_extract_general_document(self):
        """Verifies canonical fallback schema and CSV for non-invoice, non-resume general documents."""
        general_pdf = self.test_dir / "general_spec.pdf"
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text(fitz.Point(50, 60), "Paperplane Architecture Whitepaper\nDate: 2026-10-14\nContact: dev@paperplane.test\n\nSecurity Architecture and Microservice Deployment Guidelines.", fontsize=11)
        doc.save(str(general_pdf))
        doc.close()

        res = ai_engine.extract_metadata_entities(general_pdf, doc_type="auto")
        self.assertEqual(res["document_type"], "general")
        self.assertIn("general_data", res)
        self.assertIn("Paperplane Architecture", res["general_data"]["title"])
        self.assertIn("dev@paperplane.test", res["contact"]["emails"])

        # CSV export validity
        reader = list(csv.reader(io.StringIO(res["csv_export"])))
        self.assertEqual(reader[0][0], "DocumentTitle")
        self.assertIn("Paperplane Architecture", reader[1][0])

    def test_06_chat_supported_vs_unsupported_queries(self):
        """Verifies grounded answers and verified citations for supported questions, and honest zero citations for unsupported questions."""
        # 1. Supported question
        res_sup = ai_engine.chat_with_pdf(self.invoice_pdf, "What is the invoice number and total amount?")
        self.assertEqual(res_sup["citations"], [1])
        self.assertTrue("INV-2026-8891" in res_sup["answer"] or "550" in res_sup["answer"])

        # 2. Unsupported question: Must say no relevant info found and cite NOTHING
        res_unsup = ai_engine.chat_with_pdf(self.invoice_pdf, "What is the atmospheric composition of Mars and Saturn?")
        self.assertEqual(res_unsup["citations"], [])
        self.assertIn("no relevant information", res_unsup["answer"].lower())

    def test_07_executive_summarizer_structured(self):
        """Verifies executive summarizer returns structured brief on real document."""
        summary = ai_engine.summarize_pdf(self.invoice_pdf)
        self.assertIn("Executive Summary", summary)
        self.assertTrue(len(summary) > 50)


if __name__ == "__main__":
    unittest.main()
