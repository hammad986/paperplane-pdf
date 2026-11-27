import json, os, secrets, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
for key in list(os.environ):
    if any(marker in key.upper() for marker in ("KEY", "SECRET", "TOKEN", "PASSWORD", "PAPERPLANE_", "SMTP_", "RESEND_", "CASHFREE_", "AI_", "ADMIN_")):
        os.environ.pop(key, None)
os.environ.update(PAPERPLANE_SKIP_DOTENV="1", PAPERPLANE_ENV="development", PAPERPLANE_DATA_DIR=str(OUT / "runtime-current-catalog"), PAPERPLANE_ADMIN_KEY=secrets.token_urlsafe(64), PAPERPLANE_ADMIN_CODE=secrets.token_urlsafe(32), AI_PROVIDER="")
def main():
    sys.path.insert(0, str(ROOT))
    import server
    from tempfile import TemporaryDirectory
    import importlib.util
    spec_path = ROOT / "reports/launch-audit-v21/tool_content_audit.py"
    spec = importlib.util.spec_from_file_location("catalog", spec_path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    checks = mod.load_previous_checks()
    with TemporaryDirectory(prefix="paperplane-v24-catalog-") as folder:
        base = Path(folder)
        rounds = []
        for n in (1, 2):
            result = mod.round_result(n, server, checks, base)
            rounds.append(result)
            counts = {}
            for row in result["results"]: counts[row["status"]] = counts.get(row["status"], 0) + 1
            print(json.dumps({"round": n, "total": len(result["results"]), "counts": counts, "failed": [r for r in result["results"] if r["status"] == "failed"]}), flush=True)
        target = OUT / "local-v234-44-operation-content-audit.json"
        target.write_text(json.dumps({"runtime": "current local source, isolated temporary data, AI provider disabled", "rounds": rounds}, indent=2), encoding="utf-8")
        print(f"evidence={target}")

if __name__ == "__main__":
    main()
