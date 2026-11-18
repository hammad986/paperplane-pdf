"""Isolated container/browser check of the production Nginx security edge."""
from __future__ import annotations

import json
import ipaddress
import socket
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
STAMP = f"{int(time.time())}-{socket.gethostname().lower()[:10]}"
NETWORK = f"pp-id246-{STAMP}"
APP = f"pp-id246-app-{STAMP}"
NGINX = f"pp-id246-nginx-{STAMP}"
SUBNET = "192.168.254.0/24"
APP_IP = "192.168.254.3"
NGINX_IP = "192.168.254.2"


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], text=True, capture_output=True, check=check)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def make_certificate(cert_path: Path, key_path: Path) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject).issuer_name(subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([
            x509.DNSName("localhost"), x509.IPAddress(__import__("ipaddress").ip_address("127.0.0.1")),
        ]), critical=False)
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


results: dict[str, object] = {}
with tempfile.TemporaryDirectory(prefix="paperplane-id246-") as temporary:
    temp = Path(temporary)
    certs = temp / "certs"
    certs.mkdir()
    make_certificate(certs / "fullchain.pem", certs / "privkey.pem")
    existing = docker("network", "ls", "--format", "{{.Name}}").stdout.splitlines()
    if NETWORK in existing:
        raise RuntimeError("unique audit network unexpectedly already exists")
    # Docker rejects overlapping IPAM ranges, so let it choose a subnet if this
    # uncommon isolated test subnet is already occupied.
    created_network = docker("network", "create", "--driver", "bridge", "--subnet", SUBNET, NETWORK, check=False)
    if created_network.returncode:
        docker("network", "create", "--driver", "bridge", NETWORK)
        subnet_info = json.loads(docker("network", "inspect", NETWORK).stdout)[0]["IPAM"]["Config"][0]
        gateway = subnet_info["Gateway"]
        base = gateway.rsplit(".", 1)[0]
        APP_IP, NGINX_IP = f"{base}.3", f"{base}.2"
        SUBNET = subnet_info["Subnet"]
    else:
        pass
    https_port, http_port = free_port(), free_port()
    while http_port == https_port:
        http_port = free_port()
    app_args = [
        "run", "-d", "--name", APP, "--network", NETWORK, "--ip", APP_IP,
        "--network-alias", "paperplane", "--tmpfs", "/data:size=512m,mode=1777",
        "--tmpfs", "/tmp:size=256m,mode=1777",
        "-e", "PAPERPLANE_ENV=production", "-e", "PAPERPLANE_DATA_DIR=/data",
        "-e", "PAPERPLANE_PUBLIC_URL=https://paperplane.qd.je",
        "-e", "PAPERPLANE_REQUIRE_AUTH=false", "-e", "PAPERPLANE_SECURE_COOKIES=false",
        "-e", "PAPERPLANE_HOST=0.0.0.0", "-e", "PAPERPLANE_PORT=8501",
        "-e", "PAPERPLANE_SKIP_DOTENV=1", "-e", "PAPERPLANE_ADMIN_CODE=local-only-synthetic-code",
        "-e", f"PAPERPLANE_ADMIN_KEY={'k' * 64}",
        "-e", "PAPERPLANE_SESSION_SECRET=local-only-synthetic-session-secret-0123456789",
        "-e", f"PAPERPLANE_TRUSTED_HOSTS=localhost,127.0.0.1,paperplane",
        "-e", f"PAPERPLANE_TRUSTED_PROXY_HOSTS={NGINX_IP}",
    ]
    current_source_mounts = [
        (ROOT / "server.py", "/app/server.py"),
        (ROOT / "persistence.py", "/app/persistence.py"),
        (ROOT / "converters.py", "/app/converters.py"),
        (ROOT / "ai_engine.py", "/app/ai_engine.py"),
        (ROOT / "security_forms_engine.py", "/app/security_forms_engine.py"),
        (ROOT / "email_service.py", "/app/email_service.py"),
        (ROOT / "config.py", "/app/config.py"),
        (ROOT / "deploy/fonts", "/app/deploy/fonts"),
        (ROOT / "web", "/app/web"),
    ]
    for source_path, target_path in current_source_mounts:
        app_args.extend(["-v", f"{source_path.resolve().as_posix()}:{target_path}:ro"])
    app_args.append("paperplane-v23-audit:local")
    docker(*app_args)
    try:
        for _ in range(150):
            state = json.loads(docker("inspect", "--format", "{{json .State}}", APP).stdout)
            if state.get("Health", {}).get("Status") == "healthy":
                break
            if state.get("Status") == "exited":
                raise RuntimeError(docker("logs", APP, check=False).stdout[-4000:])
            time.sleep(1)
        else:
            raise RuntimeError("isolated production app did not become healthy")

        nginx_args = [
            "run", "-d", "--name", NGINX, "--network", NETWORK, "--ip", NGINX_IP,
            "-e", "PAPERPLANE_DOMAIN=localhost", "-v", f"{(ROOT / 'deploy/nginx.conf.template').resolve()}:/etc/nginx/templates/default.conf.template:ro",
            "-v", f"{certs.resolve()}:/etc/nginx/certs:ro",
            "-p", f"127.0.0.1:{http_port}:80", "-p", f"127.0.0.1:{https_port}:443",
            "nginx:1.27-alpine",
        ]
        docker(*nginx_args)
        for _ in range(60):
            state = json.loads(docker("inspect", "--format", "{{json .State}}", NGINX).stdout)
            if state.get("Status") == "running":
                logs = docker("logs", NGINX, check=False).stderr
                if "emerg" in logs.lower() or "failed" in logs.lower():
                    time.sleep(1)
                    continue
                break
            time.sleep(.5)
        else:
            raise RuntimeError(docker("logs", NGINX, check=False).stderr[-4000:])

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(ignore_https_errors=True, viewport={"width": 1366, "height": 900})
            page = context.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            url = f"https://localhost:{https_port}/"
            response = page.goto(url, wait_until="networkidle", timeout=60000)
            assert response and response.status == 200
            page.locator("#app-shell").wait_for(state="attached")
            asset = page.request.get(f"https://localhost:{https_port}/assets/app.js?v=75")
            api = page.request.get(f"https://localhost:{https_port}/api/health")
            assert asset.status == 200 and api.status == 200
            hsts_expected = "max-age=63072000; includeSubDomains; preload"
            csp = response.headers.get("content-security-policy", "")
            expected_headers = {
                "html_hsts": response.headers.get("strict-transport-security", "") == hsts_expected,
                "html_csp": "default-src 'self'" in csp and "object-src 'none'" in csp,
                "html_nosniff": response.headers.get("x-content-type-options") == "nosniff",
                "html_frame_options": response.headers.get("x-frame-options") == "SAMEORIGIN",
                "html_permissions_policy": response.headers.get("permissions-policy") == "camera=(self), microphone=(), geolocation=()",
                "html_server_version_hidden": "nginx/" not in response.headers.get("server", "").lower(),
                "asset_hsts": asset.headers.get("strict-transport-security", "") == hsts_expected,
                "asset_csp": "default-src 'self'" in asset.headers.get("content-security-policy", ""),
                "asset_cache_control": "public, no-transform" in asset.headers.get("cache-control", ""),
                "api_hsts": api.headers.get("strict-transport-security", "") == hsts_expected,
                "api_csp": "default-src 'self'" in api.headers.get("content-security-policy", ""),
                "health_json": api.json().get("status") == "ok",
            }
            assert all(expected_headers.values()), expected_headers
            http = page.request.get(f"http://localhost:{http_port}/", max_redirects=0)
            assert http.status == 301 and http.headers.get("location", "").startswith("https://localhost/"), {
                "status": http.status, "location": http.headers.get("location")
            }
            spoofed_ips = ["203.0.113.99", "198.51.100.77"]
            login_statuses = []
            for index, spoofed_ip in enumerate(spoofed_ips):
                attempt = page.request.post(
                    f"https://localhost:{https_port}/api/auth/login",
                    headers={"X-Forwarded-For": spoofed_ip},
                    data={"email": f"proxy-audit-{STAMP}-{index}@example.test", "password": "invalid synthetic password"},
                )
                login_statuses.append(attempt.status)
            assert login_statuses == [401, 401], login_statuses
            audit_query = (
                "import sqlite3,json; c=sqlite3.connect('/data/paperplane.sqlite3'); "
                f"r=c.execute(\"SELECT ip_address FROM audit_logs WHERE email LIKE 'proxy-audit-{STAMP}-%' "
                "AND event_type='login_failed' ORDER BY created_at\").fetchall(); print(json.dumps([x[0] for x in r]))"
            )
            audited_ips = json.loads(docker("exec", APP, "python", "-c", audit_query).stdout)
            assert len(audited_ips) == 2 and audited_ips[0] == audited_ips[1], audited_ips
            assert all(ipaddress.ip_address(value) for value in audited_ips), audited_ips
            assert not set(audited_ips).intersection(spoofed_ips), audited_ips
            admin_statuses = []
            admin_spoofs = ["192.0.2.44", "198.51.100.19", "203.0.113.72"]
            for spoofed_ip in admin_spoofs:
                attempt = page.request.post(
                    f"https://localhost:{https_port}/api/admin/auth/step1",
                    headers={"X-Forwarded-For": spoofed_ip},
                    data={"admin_key": "wrong-key", "admin_code": "wrong-code", "email": "mdhammad2906@gmail.com"},
                )
                admin_statuses.append(attempt.status)
            lockout_status = page.request.get(
                f"https://localhost:{https_port}/api/admin/auth/status",
                headers={"X-Forwarded-For": "203.0.113.200"},
            )
            assert admin_statuses == [401, 401, 423], admin_statuses
            assert lockout_status.status == 200 and lockout_status.json().get("locked") is True, lockout_status.text()
            lockout_query = (
                "import sqlite3,json; c=sqlite3.connect('/data/paperplane.sqlite3'); "
                "r=c.execute(\"SELECT client_ip,failed_attempts FROM admin_auth_attempts\").fetchall(); "
                "print(json.dumps(r))"
            )
            lockout_rows = json.loads(docker("exec", APP, "python", "-c", lockout_query).stdout)
            assert len(lockout_rows) == 1 and lockout_rows[0][1] == 3, lockout_rows
            assert lockout_rows[0][0] not in admin_spoofs, lockout_rows
            assert not errors, errors
            page.screenshot(path=str(OUT / "id246-nginx-proxy-home.png"), full_page=True)
            results.update({
                "network_subnet": SUBNET,
                "app_image": "paperplane-v23-audit:local",
                "nginx_image": "nginx:1.27-alpine",
                "html_status": response.status,
                "asset_status": asset.status,
                "api_status": api.status,
                "http_redirect_status": http.status,
                "http_redirect_location": http.headers.get("location"),
                "spoofed_xff_values": spoofed_ips,
                "failed_login_statuses": login_statuses,
                "audit_ips_recorded_by_app": audited_ips,
                "forwarded_ip_spoof_rejected": True,
                "admin_lockout_spoof_values": admin_spoofs,
                "admin_step1_statuses": admin_statuses,
                "admin_lockout_status_with_new_spoof": lockout_status.json(),
                "admin_lockout_rows": lockout_rows,
                "lockout_bucket_bound_to_actual_proxy_peer": True,
                "checks": expected_headers,
                "page_errors": errors,
            })
            context.close()
            browser.close()
    finally:
        docker("rm", "-f", NGINX, check=False)
        docker("rm", "-f", APP, check=False)
        docker("network", "rm", NETWORK, check=False)

result_path = OUT / "browser-id246-nginx-container-integration.json"
result_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
print(json.dumps(results, indent=2))
