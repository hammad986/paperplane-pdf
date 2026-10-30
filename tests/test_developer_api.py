from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
import fitz

import config
from persistence import (
    init_db, create_user, create_api_key, revoke_api_key,
    get_developer_api_usage, check_and_consume_developer_quota
)
from server import app


class TestDeveloperAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

        # Create isolated developer test accounts
        cls.user_a_email = f"dev_test_a_{uuid.uuid4().hex[:8]}@paperplane.test"
        cls.user_a_id = create_user(cls.user_a_email, "SecureDevPass123!")
        cls.key_a_id, cls.key_a_raw = create_api_key(cls.user_a_id, name="Test Key Alpha")

        cls.user_b_email = f"dev_test_b_{uuid.uuid4().hex[:8]}@paperplane.test"
        cls.user_b_id = create_user(cls.user_b_email, "SecureDevPass456!")
        cls.key_b_id, cls.key_b_raw = create_api_key(cls.user_b_id, name="Test Key Beta")

        # Create a small valid test PDF
        cls.temp_dir = Path(tempfile.mkdtemp())
        cls.sample_pdf = cls.temp_dir / "sample.pdf"
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text(fitz.Point(72, 72), "Paperplane Developer API Test Document\nTesting operations.", fontsize=14)
        doc.save(str(cls.sample_pdf))
        doc.close()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_01_v1_operations_catalog(self):
        """Verifies GET /api/v1/operations lists all 37 tools with capabilities and categories."""
        res = self.client.get("/api/v1/operations")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("total_operations", data)
        self.assertGreaterEqual(data["total_operations"], 35)
        self.assertIn("operations", data)

        op_names = [op["operation"] for op in data["operations"]]
        for required_op in ["merge", "compress", "word_to_pdf", "pdf_to_word", "protect", "unlock", "summarize", "ai_chat"]:
            self.assertIn(required_op, op_names)

        first_op = data["operations"][0]
        self.assertIn("operation", first_op)
        self.assertIn("label", first_op)
        self.assertIn("category", first_op)
        self.assertIn("accepts", first_op)
        self.assertIn("implemented", first_op)
        self.assertIn("description", first_op)

    def test_02_api_key_lifecycle(self):
        """Verifies creating, listing, and revoking API keys."""
        # 1. Create a third key for User A
        res = self.client.post(
            "/api/v1/keys",
            data={"name": "Temporary Worker Key"},
            headers={"Authorization": f"Bearer {self.key_a_raw}"}
        )
        self.assertEqual(res.status_code, 200)
        key_data = res.json()
        self.assertTrue(key_data["api_key"].startswith("sk_live_"))
        self.assertEqual(key_data["name"], "Temporary Worker Key")
        self.assertIn("warning", key_data)
        temp_key_id = key_data["id"]
        temp_raw_key = key_data["api_key"]

        # 2. List keys - full secret must never be returned in list
        list_res = self.client.get(
            "/api/v1/keys",
            headers={"Authorization": f"Bearer {self.key_a_raw}"}
        )
        self.assertEqual(list_res.status_code, 200)
        keys_list = list_res.json()["keys"]
        self.assertTrue(any(k["id"] == temp_key_id for k in keys_list))
        for k in keys_list:
            self.assertNotIn("api_key", k)  # Raw secret must not be stored/listed
            self.assertIn("key_prefix", k)

        # 3. Authenticate with the new temporary key
        auth_test_res = self.client.get(
            "/api/v1/account/usage",
            headers={"Authorization": f"Bearer {temp_raw_key}"}
        )
        self.assertEqual(auth_test_res.status_code, 200)

        # 4. Revoke the key
        del_res = self.client.delete(
            f"/api/v1/keys/{temp_key_id}",
            headers={"Authorization": f"Bearer {self.key_a_raw}"}
        )
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.json()["revoked"])

        # 5. Revoked key must immediately fail authentication
        revoked_auth_res = self.client.get(
            "/api/v1/account/usage",
            headers={"Authorization": f"Bearer {temp_raw_key}"}
        )
        self.assertEqual(revoked_auth_res.status_code, 401)

    def test_03_auth_header_required(self):
        """Verifies missing or invalid authentication returns 401."""
        res_no_auth = self.client.get("/api/v1/account/usage")
        self.assertEqual(res_no_auth.status_code, 401)

        res_bad_auth = self.client.get(
            "/api/v1/account/usage",
            headers={"Authorization": "Bearer sk_live_completely_fake_invalid_key_9999"}
        )
        self.assertEqual(res_bad_auth.status_code, 401)

    def test_04_query_param_key_strictly_rejected(self):
        """Verifies that API keys in query parameters are strictly rejected with HTTP 400."""
        res_query = self.client.get(f"/api/v1/account/usage?api_key={self.key_a_raw}")
        self.assertEqual(res_query.status_code, 400)
        self.assertIn("query parameters", res_query.json()["detail"].lower())

    def test_05_developer_account_usage_endpoint(self):
        """Verifies GET /api/v1/account/usage returns quota statistics and rate limit headers."""
        res = self.client.get(
            "/api/v1/account/usage",
            headers={"Authorization": f"Bearer {self.key_a_raw}"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["daily_limit"], 10)
        self.assertEqual(data["ai_limit"], 3)
        self.assertEqual(data["max_file_size_mb"], 10)
        self.assertEqual(data["concurrent_jobs_limit"], 2)
        self.assertIn("reset_time_utc", data)

        # Check response headers
        self.assertEqual(res.headers.get("X-RateLimit-Limit"), "10")
        self.assertEqual(res.headers.get("X-RateLimit-AI-Limit"), "3")
        self.assertIsNotNone(res.headers.get("X-RateLimit-Remaining"))

    def test_06_job_creation_and_quota_consumption(self):
        """Verifies POST /api/v1/jobs queues a job, returns 202 Accepted, and decrements quota."""
        # Check usage before
        usage_before = self.client.get(
            "/api/v1/account/usage",
            headers={"Authorization": f"Bearer {self.key_a_raw}"}
        ).json()

        with open(self.sample_pdf, "rb") as f:
            res = self.client.post(
                "/api/v1/jobs",
                headers={"Authorization": f"Bearer {self.key_a_raw}"},
                data={"operation": "compress", "options": json.dumps({"preset": "balanced"})},
                files={"files": ("test.pdf", f, "application/pdf")}
            )

        self.assertEqual(res.status_code, 202)
        body = res.json()
        self.assertIn("job_id", body)
        self.assertEqual(body["status"], "queued")
        self.assertEqual(body["operation"], "compress")
        self.assertTrue(body["status_url"].startswith("/api/v1/jobs/"))
        self.assertTrue(body["download_url"].startswith("/api/v1/jobs/"))

        # Rate limit header must reflect remaining count
        self.assertIn("X-RateLimit-Remaining", res.headers)

        # Verify quota decremented
        usage_after = self.client.get(
            "/api/v1/account/usage",
            headers={"Authorization": f"Bearer {self.key_a_raw}"}
        ).json()
        self.assertEqual(usage_after["calls_used"], usage_before["calls_used"] + 1)
        self.assertEqual(usage_after["calls_remaining"], usage_before["calls_remaining"] - 1)

    def test_07_idempotency_key_prevents_duplicate_processing(self):
        """Verifies submitting with an Idempotency-Key returns existing job without double charging quota."""
        idem_key = f"idem_test_{uuid.uuid4().hex}"

        # 1. First submission
        with open(self.sample_pdf, "rb") as f:
            res1 = self.client.post(
                "/api/v1/jobs",
                headers={
                    "Authorization": f"Bearer {self.key_a_raw}",
                    "Idempotency-Key": idem_key
                },
                data={"operation": "compress"},
                files={"files": ("test.pdf", f, "application/pdf")}
            )
        self.assertEqual(res1.status_code, 202)
        job_id_1 = res1.json()["job_id"]

        usage_after_first = self.client.get(
            "/api/v1/account/usage",
            headers={"Authorization": f"Bearer {self.key_a_raw}"}
        ).json()["calls_used"]

        # 2. Second submission with the exact same Idempotency-Key
        with open(self.sample_pdf, "rb") as f:
            res2 = self.client.post(
                "/api/v1/jobs",
                headers={
                    "Authorization": f"Bearer {self.key_a_raw}",
                    "Idempotency-Key": idem_key
                },
                data={"operation": "compress"},
                files={"files": ("test.pdf", f, "application/pdf")}
            )
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()["job_id"], job_id_1)
        self.assertTrue(res2.json()["idempotent"])

        usage_after_second = self.client.get(
            "/api/v1/account/usage",
            headers={"Authorization": f"Bearer {self.key_a_raw}"}
        ).json()["calls_used"]

        # Usage must NOT increase on idempotent replay
        self.assertEqual(usage_after_first, usage_after_second)

    def test_08_daily_quota_exhaustion_429(self):
        """Verifies that exceeding the 10 daily operations limit returns HTTP 429."""
        user_c_email = f"dev_quota_{uuid.uuid4().hex[:8]}@paperplane.test"
        user_c_id = create_user(user_c_email, "SecureQuotaPass123!")
        _, key_c_raw = create_api_key(user_c_id, name="Quota Exhauster Key")

        # Consume all 10 free quota units
        for i in range(10):
            allowed, _, usage = check_and_consume_developer_quota(user_c_id, is_ai=False, file_size_bytes=100)
            self.assertTrue(allowed, f"Failed at call {i+1}")

        # The 11th call must return 429
        with open(self.sample_pdf, "rb") as f:
            res = self.client.post(
                "/api/v1/jobs",
                headers={"Authorization": f"Bearer {key_c_raw}"},
                data={"operation": "compress"},
                files={"files": ("test.pdf", f, "application/pdf")}
            )
        self.assertEqual(res.status_code, 429)
        detail = res.json()["detail"]
        self.assertEqual(detail["code"], "QUOTA_EXHAUSTED")
        self.assertIn("exceeded", detail["message"].lower())
        self.assertEqual(res.headers.get("X-RateLimit-Remaining"), "0")

    def test_09_ai_operations_cap_enforcement(self):
        """Verifies that AI operations are capped at 3 calls/day within the 10 total allowance."""
        user_d_email = f"dev_ai_{uuid.uuid4().hex[:8]}@paperplane.test"
        user_d_id = create_user(user_d_email, "SecureAIPass123!")
        _, key_d_raw = create_api_key(user_d_id, name="AI Tester Key")

        # Consume 3 AI calls
        for _ in range(3):
            allowed, _, usage = check_and_consume_developer_quota(user_d_id, is_ai=True, file_size_bytes=100)
            self.assertTrue(allowed)

        # 4th AI call must be rejected with 429
        with open(self.sample_pdf, "rb") as f:
            res_ai = self.client.post(
                "/api/v1/ai/summarize",
                headers={"Authorization": f"Bearer {key_d_raw}"},
                files={"file": ("test.pdf", f, "application/pdf")}
            )
        self.assertEqual(res_ai.status_code, 429)

        # But a deterministic operation can still proceed because 3 < 10 total!
        with open(self.sample_pdf, "rb") as f:
            res_det = self.client.post(
                "/api/v1/jobs",
                headers={"Authorization": f"Bearer {key_d_raw}"},
                data={"operation": "compress"},
                files={"files": ("test.pdf", f, "application/pdf")}
            )
        self.assertEqual(res_det.status_code, 202)

    def test_10_file_size_limit_enforcement(self):
        """Verifies that files larger than 10MB are rejected for the free developer tier."""
        oversized_bytes = b"%PDF-" + b"0" * (11 * 1024 * 1024)  # 11 MB
        res = self.client.post(
            "/api/v1/jobs",
            headers={"Authorization": f"Bearer {self.key_a_raw}"},
            data={"operation": "compress"},
            files={"files": ("oversized.pdf", oversized_bytes, "application/pdf")}
        )
        self.assertEqual(res.status_code, 429)
        self.assertIn("10 mb", res.json()["detail"]["message"].lower())

    def test_11_tenant_isolation(self):
        """Verifies strict cross-account isolation: Dev B cannot access Dev A's jobs."""
        # User A creates a job
        with open(self.sample_pdf, "rb") as f:
            res_a = self.client.post(
                "/api/v1/jobs",
                headers={"Authorization": f"Bearer {self.key_a_raw}"},
                data={"operation": "compress"},
                files={"files": ("test.pdf", f, "application/pdf")}
            )
        job_id_a = res_a.json()["job_id"]

        # Dev B tries to read Dev A's job status -> 404
        res_b_get = self.client.get(
            f"/api/v1/jobs/{job_id_a}",
            headers={"Authorization": f"Bearer {self.key_b_raw}"}
        )
        self.assertEqual(res_b_get.status_code, 404)

        # Dev B tries to download Dev A's job -> 404
        res_b_dl = self.client.get(
            f"/api/v1/jobs/{job_id_a}/download",
            headers={"Authorization": f"Bearer {self.key_b_raw}"}
        )
        self.assertEqual(res_b_dl.status_code, 404)

        # Dev B tries to delete Dev A's job -> 404
        res_b_del = self.client.delete(
            f"/api/v1/jobs/{job_id_a}",
            headers={"Authorization": f"Bearer {self.key_b_raw}"}
        )
        self.assertEqual(res_b_del.status_code, 404)

    def test_12_direct_ai_endpoints(self):
        """Verifies direct developer AI endpoints: summarize, extract, and chat."""
        # 1. Summarize
        with open(self.sample_pdf, "rb") as f:
            res_sum = self.client.post(
                "/api/v1/ai/summarize",
                headers={"Authorization": f"Bearer {self.key_b_raw}"},
                files={"file": ("test.pdf", f, "application/pdf")}
            )
        self.assertEqual(res_sum.status_code, 200)
        self.assertIn("summary", res_sum.json())

        # 2. Extract
        with open(self.sample_pdf, "rb") as f:
            res_ext = self.client.post(
                "/api/v1/ai/extract",
                headers={"Authorization": f"Bearer {self.key_b_raw}"},
                files={"file": ("test.pdf", f, "application/pdf")},
                data={"doc_type": "auto"}
            )
        self.assertEqual(res_ext.status_code, 200)
        self.assertIn("document_type", res_ext.json())

        # 3. Chat
        with open(self.sample_pdf, "rb") as f:
            res_chat = self.client.post(
                "/api/v1/ai/chat",
                headers={"Authorization": f"Bearer {self.key_b_raw}"},
                files={"file": ("test.pdf", f, "application/pdf")},
                data={"question": "What is this document about?"}
            )
        self.assertEqual(res_chat.status_code, 200)
        chat_data = res_chat.json()
        self.assertIn("answer", chat_data)
        self.assertIn("citations", chat_data)

    def test_13_agentrouter_connectivity_diagnostics(self):
        """Verifies GET /api/v1/ai/test-connection returns diagnostic probe without exposing secrets."""
        res = self.client.get(
            "/api/v1/ai/test-connection",
            headers={"Authorization": f"Bearer {self.key_a_raw}"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["provider"], "AgentRouter")
        self.assertIn("status", data)
        # Secret key must NEVER be in response
        self.assertNotIn(config.AGENTROUTER_API_KEY, json.dumps(data))

    def test_14_developers_page_route(self):
        """Verifies GET /developers route returns 200 HTML."""
        res = self.client.get("/developers")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/html", res.headers.get("content-type", ""))
        self.assertIn("Paperplane PDF", res.text)

    def test_15_job_based_ai_operations(self):
        """Verifies asynchronous job creation, completion, and download for ai_extract and ai_chat."""
        # 1. Job-based ai_extract
        with open(self.sample_pdf, "rb") as f:
            res_ext = self.client.post(
                "/api/v1/jobs",
                headers={"Authorization": f"Bearer {self.key_a_raw}"},
                data={"operation": "ai_extract", "options": json.dumps({"document_type": "auto"})},
                files={"files": ("invoice.pdf", f, "application/pdf")}
            )
        self.assertEqual(res_ext.status_code, 202)
        job_ext_id = res_ext.json()["job_id"]

        # Poll status
        max_retries = 20
        completed = False
        for _ in range(max_retries):
            status_res = self.client.get(
                f"/api/v1/jobs/{job_ext_id}",
                headers={"Authorization": f"Bearer {self.key_a_raw}"}
            )
            if status_res.json()["status"] == "completed":
                completed = True
                break
            time.sleep(0.2)
        self.assertTrue(completed, "Job ai_extract did not complete in time")

        # Download result
        dl_res = self.client.get(
            f"/api/v1/jobs/{job_ext_id}/download",
            headers={"Authorization": f"Bearer {self.key_a_raw}"}
        )
        self.assertEqual(dl_res.status_code, 200)
        ext_json = json.loads(dl_res.content.decode("utf-8"))
        self.assertIn("document_type", ext_json)


if __name__ == "__main__":
    unittest.main()

