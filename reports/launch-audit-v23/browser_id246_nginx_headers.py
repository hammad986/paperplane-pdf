"""Run current Paperplane source behind the project Nginx template and verify headers in Chromium."""
from __future__ import annotations

import json
import ssl
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
IMAGE = "pdf_splitter-paperplane:latest"
BASE = "https://127.0.0.1:18443"
SECURITY_HEADERS = {
    "strict-transport-security",
    "x-content-type-options",
    "x-frame-options",
    "x-xss-protection",
    "referrer-policy",
    "permissions-policy",
    "cross-origin-opener-policy",
    "content-security-policy",
}


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=True, text=True, capture_output=True, **kwargs)


def create_test_certificate(directory: Path) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(__import__("ipaddress").ip_address("127.0.0.1"))]), critical=False)
        .sign(key, hashes.SHA256())
    )
    (directory / "fullchain.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (directory / "privkey.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))


def main() -> None:
    suffix = uuid.uuid4().hex[:8]
    network = f"pp-id246-{suffix}"
    app_name = f"pp-id246-app-{suffix}"
    nginx_name = f"pp-id246-nginx-{suffix}"
    result_path = ROOT / "reports" / "launch-audit-v23" / "browser-id246-nginx-headers.json"
    errors: list[str] = []
    evidence: list[dict] = []

    with tempfile.TemporaryDirectory(prefix="paperplane-id246-") as tmp:
        cert_dir = Path(tmp) / "certs"
        cert_dir.mkdir()
        create_test_certificate(cert_dir)
        cert_dir = cert_dir.resolve()
        root = ROOT.resolve()
        run(["docker", "network", "create", network])
        try:
            run([
                "docker", "run", "-d", "--name", app_name, "--network", network,
                "--network-alias", "paperplane", "--tmpfs", "/data:rw,noexec,nosuid,size=256m,mode=1777",
                "-e", "PAPERPLANE_ENV=production", "-e", "PAPERPLANE_DATA_DIR=/data",
                "-e", "PAPERPLANE_SESSION_SECRET=id246-local-test-session-secret-32-bytes-minimum",
                "-e", "PAPERPLANE_HOST=0.0.0.0", "-e", "PAPERPLANE_PORT=8501",
                "-e", "PAPERPLANE_WORKERS=2", "-e", "PAPERPLANE_ADMIN_CODE=local-test-only",
                "-e", "PAPERPLANE_ADMIN_KEY=local-test-key-only", "-e", "PAPERPLANE_REQUIRE_AUTH=false",
                "-e", "PAPERPLANE_ALLOW_BILLING_SIMULATION=false", "-e", "PAPERPLANE_SECURE_COOKIES=true",
                "-e", "PAPERPLANE_PUBLIC_URL=https://paperplane.qd.je",
                "-e", "PAPERPLANE_TRUSTED_HOSTS=localhost,127.0.0.1,paperplane.qd.je",
                "-e", "PAPERPLANE_ALLOWED_ORIGINS=https://paperplane.qd.je,https://localhost,https://127.0.0.1:18443",
                "-v", f"{root / 'server.py'}:/app/server.py:ro",
                "-v", f"{root / 'persistence.py'}:/app/persistence.py:ro",
                "-v", f"{root / 'converters.py'}:/app/converters.py:ro",
                "-v", f"{root / 'ai_engine.py'}:/app/ai_engine.py:ro",
                "-v", f"{root / 'security_forms_engine.py'}:/app/security_forms_engine.py:ro",
                "-v", f"{root / 'email_service.py'}:/app/email_service.py:ro",
                "-v", f"{root / 'config.py'}:/app/config.py:ro",
                "-v", f"{root / 'web'}:/app/web:ro",
                IMAGE,
            ])
            run([
                "docker", "run", "-d", "--name", nginx_name, "--network", network,
                "-p", "127.0.0.1:18443:443", "-e", "PAPERPLANE_DOMAIN=localhost",
                "-v", f"{ROOT / 'deploy' / 'nginx.conf.template'}:/etc/nginx/templates/default.conf.template:ro",
                "-v", f"{cert_dir}:/etc/nginx/certs:ro", "nginx:1.27-alpine",
            ])

            deadline = time.time() + 90
            while time.time() < deadline:
                try:
                    response = __import__("urllib.request").request.urlopen(BASE + "/health", timeout=3, context=ssl._create_unverified_context())
                    response.close()
                    break
                except Exception:
                    time.sleep(1)
            else:
                logs_result = subprocess.run(["docker", "logs", app_name], text=True, capture_output=True)
                logs = logs_result.stdout + logs_result.stderr
                raise RuntimeError(f"Nginx/app readiness timed out. App logs: {logs[-4000:]}")

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                for round_no in (1, 2):
                    context = browser.new_context(ignore_https_errors=True, viewport={"width": 1366, "height": 900})
                    page = context.new_page()
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    statuses: dict[str, int] = {}
                    pages = (
                        ("home", "/"),
                        ("asset", "/assets/app.js"),
                        ("api-error", "/api/__id246_missing_route__"),
                    )
                    for label, path in pages:
                        response = page.goto(BASE + path, wait_until="domcontentloaded")
                        assert response is not None
                        headers = {key.lower(): value for key, value in response.all_headers().items()}
                        raw_headers = response.headers_array()
                        observed_security = [
                            entry["name"].lower()
                            for entry in raw_headers
                            if entry["name"].lower() in SECURITY_HEADERS
                        ]
                        assert set(observed_security) == SECURITY_HEADERS, (label, observed_security, headers)
                        assert all(observed_security.count(name) == 1 for name in SECURITY_HEADERS), (label, observed_security)
                        assert "nginx/" not in headers.get("server", "").lower(), headers.get("server")
                        assert "max-age=63072000" in headers["strict-transport-security"]
                        assert "default-src 'self'" in headers["content-security-policy"]
                        statuses[label] = response.status
                    assert statuses["home"] == 200 and statuses["asset"] == 200 and statuses["api-error"] == 404, statuses
                    evidence.append({"round": round_no, "statuses": statuses, "headers_once_on_success_asset_and_404": True, "server_version_hidden": True})
                    context.close()
                browser.close()
        finally:
            subprocess.run(["docker", "rm", "-f", nginx_name, app_name], check=False, capture_output=True, text=True)
            subprocess.run(["docker", "network", "rm", network], check=False, capture_output=True, text=True)

    assert errors == [], errors
    result_path.write_text(json.dumps({"base": BASE, "image": IMAGE, "nginx_template": "deploy/nginx.conf.template", "test_certificate": "ephemeral self-signed certificate", "rounds": evidence, "page_errors": errors}, indent=2), encoding="utf-8")
    print(json.dumps({"evidence": str(result_path), "rounds": evidence, "page_errors": errors}, indent=2))


if __name__ == "__main__":
    main()
