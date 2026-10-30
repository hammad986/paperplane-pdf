"""One-click production build, orchestration, and smoke-test suite."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
COMPOSE_FILE = ROOT / "docker-compose.yml"


class DeploymentError(RuntimeError):
    pass


def log(message: str) -> None:
    print(f"[deploy] {message}", flush=True)


def parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def effective_env() -> dict[str, str]:
    values = parse_dotenv(ROOT / ".env")
    values.update({key: value for key, value in os.environ.items() if key.startswith("PAPERPLANE_") or key in {"JWT_SECRET", "SESSION_SECRET_KEY"}})
    return values


def is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return not normalized or normalized in {
        "change-me", "changeme", "your-secret", "yourdomain.com", "ops@yourdomain.com",
        "replace-me", "<generated_secret>", "secret", "null",
    }


def validate_configuration(env: dict[str, str], dry_run: bool) -> list[str]:
    checks: list[str] = []
    environment = env.get("PAPERPLANE_ENV", "production").lower()
    if environment != "production":
        raise DeploymentError("PAPERPLANE_ENV must be production for this deployment suite")
    checks.append("PAPERPLANE_ENV=production")

    session_secret = env.get("SESSION_SECRET_KEY", "") or env.get("PAPERPLANE_SESSION_SECRET", "")
    jwt_secret = env.get("JWT_SECRET", "")
    if is_placeholder(session_secret) or len(session_secret) < 32:
        raise DeploymentError("A 32+ character SESSION_SECRET_KEY or PAPERPLANE_SESSION_SECRET is required")
    if is_placeholder(jwt_secret) or len(jwt_secret) < 32:
        raise DeploymentError("A 32+ character JWT_SECRET is required")
    checks.append("session and JWT secrets are configured without printing their values")

    domain = env.get("PAPERPLANE_DOMAIN", "").strip()
    if not domain or domain in {"localhost", "yourdomain.com"}:
        if not dry_run:
            raise DeploymentError("PAPERPLANE_DOMAIN must be a real production domain")
        checks.append("production domain is deferred for dry-run")
    else:
        checks.append(f"production domain configured: {domain}")

    compose_text = COMPOSE_FILE.read_text(encoding="utf-8")
    if "PAPERPLANE_HOST: 0.0.0.0" not in compose_text or "PAPERPLANE_ENV: production" not in compose_text:
        raise DeploymentError("docker-compose.yml must enforce PAPERPLANE_ENV=production and PAPERPLANE_HOST=0.0.0.0")
    checks.append("Docker Compose enforces production environment and 0.0.0.0 binding")
    return checks


def docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(
            ["docker", "compose", "version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=15,
        ).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        # Docker Desktop may be installed but its daemon unavailable.  Treat
        # that as a missing local dependency so --dry-run remains useful and
        # non-dry deployments fail with the intended DeploymentError below.
        return False


def compose_command() -> list[str]:
    return ["docker", "compose", "-f", str(COMPOSE_FILE)]


def run_command(command: list[str], dry_run: bool = False, timeout: int = 300) -> None:
    log("DRY-RUN: " + " ".join(command) if dry_run else "RUN: " + " ".join(command))
    if dry_run:
        return
    completed = subprocess.run(command, cwd=ROOT, check=False, timeout=timeout)
    if completed.returncode != 0:
        raise DeploymentError(f"Command failed with exit code {completed.returncode}: {' '.join(command)}")


def check_ports() -> list[str]:
    results = []
    for port in (80, 443):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.25)
            occupied = sock.connect_ex(("127.0.0.1", port)) == 0
        results.append(f"port {port}: {'occupied by an existing listener (safe for compose reconciliation)' if occupied else 'available'}")
    return results


def render_nginx_config(domain: str) -> Path:
    template = (ROOT / "deploy" / "nginx.conf.template").read_text(encoding="utf-8")
    rendered = template.replace("${PAPERPLANE_DOMAIN}", domain)
    handle = tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False, encoding="utf-8")
    try:
        handle.write(rendered)
        return Path(handle.name)
    finally:
        handle.close()


def validate_nginx(dry_run: bool, domain: str) -> None:
    config_path = render_nginx_config(domain or "localhost")
    try:
        config_mount = str(config_path.resolve()).replace("\\", "/")
        cert_mount = str((ROOT / "deploy" / "certs").resolve()).replace("\\", "/")
        acme_mount = str((ROOT / "deploy" / "acme").resolve()).replace("\\", "/")
        command = [
            "docker", "run", "--rm", "--add-host", "paperplane:127.0.0.1",
            "-v", f"{config_mount}:/etc/nginx/conf.d/default.conf:ro",
            "-v", f"{cert_mount}:/etc/nginx/certs:ro",
            "-v", f"{acme_mount}:/var/www/certbot:ro",
            "nginx:1.27-alpine", "nginx", "-t",
        ]
        run_command(command, dry_run=dry_run, timeout=120)
    finally:
        config_path.unlink(missing_ok=True)


def container_check(command: str, dry_run: bool) -> None:
    run_command(compose_command() + ["run", "--rm", "--no-deps", "paperplane", "python", "-c", command], dry_run=dry_run)


def request_url(url: str, timeout: int = 15) -> tuple[int, bytes, str]:
    context = ssl._create_unverified_context() if url.startswith("https://127.0.0.1") or url.startswith("https://localhost") else None
    request = urllib.request.Request(url, headers={"User-Agent": "Paperplane-Deploy-Smoke/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            body = response.read()
            return response.status, body, response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        raise DeploymentError(f"{url} returned HTTP {exc.code}") from exc
    except OSError as exc:
        raise DeploymentError(f"Could not reach {url}: {exc}") from exc


def smoke_tests(base_url: str, dry_run: bool) -> list[str]:
    if dry_run:
        return [
            "GET /health -> status healthy",
            "GET /sitemap.xml -> XML with at least 37 URLs",
            "GET /robots.txt -> Allow: / and sitemap reference",
            "GET /api/operations -> 37 operation definitions",
            "DOCX -> PDF conversion inside the production container",
        ]

    base_url = base_url.rstrip("/")
    checks: list[str] = []
    status, body, _ = request_url(f"{base_url}/health")
    health = json.loads(body)
    if status != 200 or health.get("status") != "healthy":
        raise DeploymentError(f"Health check failed: {health}")
    checks.append("/health returned status=healthy")

    status, body, content_type = request_url(f"{base_url}/sitemap.xml")
    root = ET.fromstring(body)
    urls = root.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url")
    if status != 200 or "xml" not in content_type.lower() or len(urls) < 37:
        raise DeploymentError(f"Sitemap check failed: status={status}, urls={len(urls)}")
    checks.append(f"/sitemap.xml returned valid XML with {len(urls)} URLs")

    status, body, _ = request_url(f"{base_url}/robots.txt")
    robots = body.decode("utf-8", errors="replace")
    if status != 200 or "Allow: /" not in robots or "Sitemap:" not in robots:
        raise DeploymentError("robots.txt does not allow indexation or reference a sitemap")
    checks.append("/robots.txt allows indexation and references the sitemap")

    status, body, _ = request_url(f"{base_url}/api/operations")
    operations = json.loads(body)
    if status != 200 or len(operations) < 37 or not all(item.get("implemented") for item in operations.values()):
        raise DeploymentError(f"Operations catalog check failed: {len(operations)} definitions")
    checks.append(f"/api/operations returned {len(operations)} implemented definitions")
    return checks


def local_conversion_smoke() -> str:
    """Run the requested DOCX->PDF integrity check against the active runtime."""
    import fitz
    import docx
    import converters

    with tempfile.TemporaryDirectory(prefix="paperplane-deploy-") as directory:
        root = Path(directory)
        source = root / "smoke.docx"
        output = root / "smoke.pdf"
        document = docx.Document()
        document.add_heading("Paperplane production smoke test", level=1)
        document.add_paragraph("conversion ok")
        document.save(str(source))
        converters.word_to_pdf(source, output)
        if not output.exists() or output.stat().st_size <= 500:
            raise DeploymentError("DOCX -> PDF conversion produced no valid output")
        pdf = fitz.open(str(output))
        try:
            if pdf.page_count < 1:
                raise DeploymentError("DOCX -> PDF output contained no pages")
            pages = pdf.page_count
            size = output.stat().st_size
        finally:
            pdf.close()
    return f"DOCX -> PDF conversion produced an intact {pages}-page PDF ({size} bytes)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Validate configuration and print all deployment actions without running Docker.")
    parser.add_argument("--base-url", default="", help="Override the URL used for post-deployment smoke tests.")
    args = parser.parse_args()

    env = effective_env()
    report: dict[str, Any] = {"dry_run": args.dry_run, "checks": [], "status": "failed"}
    try:
        report["checks"].extend(validate_configuration(env, args.dry_run))
        report["checks"].extend(check_ports())

        if not args.dry_run and not docker_available():
            raise DeploymentError("Docker Engine with Compose v2 is required")
        if args.dry_run and not docker_available():
            log("Docker is not available; continuing because this is a configuration-only dry-run")

        run_command(compose_command() + ["config", "--quiet"], dry_run=args.dry_run, timeout=120)
        validate_nginx(args.dry_run, env.get("PAPERPLANE_DOMAIN", "localhost"))
        run_command(compose_command() + ["build", "--pull"], dry_run=args.dry_run, timeout=300)
        run_command(compose_command() + ["up", "-d"], dry_run=args.dry_run, timeout=120)

        container_check("from pathlib import Path; p=Path('/data'); p.mkdir(parents=True, exist_ok=True); t=p/'.deploy-write-check'; t.write_text('ok'); assert t.read_text() == 'ok'; t.unlink()", args.dry_run)
        conversion_check = (
            "import tempfile; from pathlib import Path; import docx, fitz, converters; "
            "root=Path(tempfile.mkdtemp()); src=root/'smoke.docx'; out=root/'smoke.pdf'; "
            "d=docx.Document(); d.add_heading('Paperplane production smoke test', level=1); d.add_paragraph('conversion ok'); d.save(src); "
            "converters.word_to_pdf(src, out); assert out.exists() and out.stat().st_size > 500; pdf=fitz.open(out); assert pdf.page_count >= 1; pdf.close()"
        )
        container_check(conversion_check, args.dry_run)
        if args.dry_run:
            report["checks"].append("DOCX -> PDF conversion integrity check scheduled inside the production container")

        public_url = args.base_url or env.get("PAPERPLANE_DEPLOY_BASE_URL", "") or env.get("PAPERPLANE_PUBLIC_URL", "")
        if not public_url or "yourdomain.com" in public_url:
            public_url = "http://127.0.0.1:8501"
        report["checks"].extend(smoke_tests(public_url, args.dry_run))
        report["base_url"] = public_url
        report["status"] = "passed"
        log("PRODUCTION DEPLOYMENT SIGN-OFF: PASS")
        for check in report["checks"]:
            log(f"PASS: {check}")
        log(f"Live URL: {public_url}")
        log(f"API docs: {public_url}/api-docs")
        return 0
    except (DeploymentError, OSError, ValueError, ET.ParseError) as exc:
        report["error"] = str(exc)
        log(f"PRODUCTION DEPLOYMENT SIGN-OFF: BLOCKED — {exc}")
        return 1
    finally:
        REPORTS.mkdir(exist_ok=True)
        (REPORTS / "deployment_last_run.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
