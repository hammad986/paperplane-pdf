"""Fail deployment checks when the HTTP-served local PDF runtime is stale."""
from __future__ import annotations

import argparse
import urllib.error
import urllib.request


MIN_RUNTIME_BYTES = 2_500
REQUIRED_EXPORT = b"transformLocalPdf"


def verify_served_runtime(base_url: str) -> tuple[int, str]:
    url = base_url.rstrip("/") + "/assets/pdf_runtime.js?v=deployment-smoke"
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read(10 * 1024)
            status = response.status
    except (OSError, urllib.error.URLError) as error:
        raise RuntimeError("Could not fetch the served PDF runtime asset") from error

    if status != 200:
        raise RuntimeError(f"PDF runtime asset returned HTTP {status}")
    if len(body) < MIN_RUNTIME_BYTES:
        raise RuntimeError(f"Served PDF runtime is incomplete ({len(body)} bytes)")
    if REQUIRED_EXPORT not in body:
        raise RuntimeError("Served PDF runtime does not expose the local PDF worker API")
    return len(body), url


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="Local or deployed Paperplane base URL")
    args = parser.parse_args()
    try:
        size, url = verify_served_runtime(args.base_url)
    except RuntimeError as error:
        parser.exit(1, f"FAIL: {error}\n")
    print(f"PASS: HTTP served PDF runtime is {size}+ bytes and contains {REQUIRED_EXPORT}: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
