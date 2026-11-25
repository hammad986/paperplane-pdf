"""Prepare an isolated, redacted mirror; never modify or push the source repo.

The known compromised value is obtained directly from the historical source
without printing it. The resulting mirror still needs owner review and a
coordinated force-push after credentials have been rotated.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, cwd: Path | None = None) -> bytes:
    result = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(f"Command failed: {args[0]} (exit {result.returncode}); details suppressed to protect credentials")
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path, help="New path for an isolated sanitized bare mirror")
    args = parser.parse_args()
    destination = args.destination.resolve()
    if destination.exists() or destination == ROOT or ROOT in destination.parents:
        raise SystemExit("Destination must be a new path outside the source worktree.")
    old_source = run("git", "show", "8dd50e6:server.py", cwd=ROOT)
    match = re.search(rb"PAPERPLANE_ADMIN_CODE[\"']\s*,\s*[\"']([^\"'\r\n]+)", old_source)
    if not match:
        raise SystemExit("Known historical fallback was not found; no mirror was created.")
    old_secret = match.group(1)
    message = run("git", "show", "-s", "--format=%B", "8dd50e6", cwd=ROOT)
    if old_secret not in message or b"=>" in old_secret:
        raise SystemExit("Historical value did not match the expected commit; no mirror was created.")
    run("git", "clone", "--mirror", "--no-local", str(ROOT), str(destination))
    warning = destination / "DO-NOT-PUBLISH-NOT-VERIFIED.txt"
    warning.write_text("This mirror has not passed the secret-removal verification. Do not publish it.\n", encoding="utf-8")
    # Codex's local checkpoint refs can point directly to trees or blobs, which
    # fast-export does not rewrite. They are local workspace snapshots, not
    # release branches; omit them from the isolated publishable mirror.
    local_refs = run("git", "for-each-ref", "--format=%(refname)", "refs/codex/", cwd=destination)
    for ref in local_refs.decode("ascii").splitlines():
        run("git", "update-ref", "-d", ref, cwd=destination)
    with tempfile.TemporaryDirectory(prefix="paperplane-history-redaction-") as temporary:
        replacements = Path(temporary) / "replacements.txt"
        replacements.write_bytes(old_secret + b"==>[REDACTED]\n")
        run(sys.executable, "-m", "git_filter_repo", "--force", "--replace-text", str(replacements),
            "--replace-message", str(replacements), cwd=destination)
    log = run("git", "log", "--all", "--format=%B", cwd=destination)
    if old_secret in log:
        raise SystemExit("Verification failed: the value remains in a reachable commit message; do not publish the mirror.")
    # Scan all objects remaining after filter-repo's cleanup, including blobs
    # excluded by its text heuristics and objects not reachable from a ref.
    process = subprocess.Popen(["git", "cat-file", "--batch-all-objects", "--batch"], cwd=destination,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    assert process.stdout is not None
    try:
        while header := process.stdout.readline():
            fields = header.split()
            if len(fields) != 3:
                raise RuntimeError("Unexpected git object header")
            size = int(fields[2])
            remaining = size
            tail = b""
            while remaining:
                block = process.stdout.read(min(1024 * 1024, remaining))
                if not block:
                    raise RuntimeError("Incomplete git object")
                if old_secret in tail + block:
                    raise RuntimeError("The value remains in the mirror; do not publish it")
                tail = (tail + block)[-max(1, len(old_secret) - 1):]
                remaining -= len(block)
            if process.stdout.read(1) != b"\n":
                raise RuntimeError("Unexpected git object delimiter")
        if process.wait() != 0:
            raise RuntimeError("Object verification failed")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    # Keep the result review-only. Never leave a rewritten mirror looking
    # publish-ready while credentials and the final source still need owner
    # review. filter-repo normally removes origin; strip any remote that remains
    # in the isolated destination so an accidental push cannot target a server.
    configured_remotes = run("git", "remote", cwd=destination).decode("utf-8").splitlines()
    for remote in configured_remotes:
        if remote.strip():
            run("git", "remote", "remove", remote.strip(), cwd=destination)
    warning.unlink()
    owner_review = destination / "OWNER-REVIEW-REQUIRED.txt"
    owner_review.write_text(
        "OWNER REVIEW REQUIRED\n\n"
        "This isolated mirror has had the known historical admin-code fallback removed "
        "and its objects scanned. It does not include current uncommitted source changes.\n\n"
        "Do not publish or push this mirror. The owner must rotate affected credentials, "
        "review the rewritten refs and full secret-scan results, then rebuild this mirror "
        "from the approved final source before any coordinated history rewrite.\n\n"
        "No source repository or remote was modified.\n",
        encoding="utf-8",
    )
    print(f"Prepared and scanned isolated mirror: {destination}")
    print("Owner review required; no destination remote or source remote was modified.")


if __name__ == "__main__":
    main()
