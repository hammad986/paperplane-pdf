from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
root_resolved = ROOT.resolve()
for cache_dir in ROOT.rglob("__pycache__"):
    if not cache_dir.is_dir() or not cache_dir.resolve().is_relative_to(root_resolved):
        continue
    for generated_file in cache_dir.iterdir():
        if generated_file.is_file() and generated_file.suffix == ".pyc" and generated_file.resolve().is_relative_to(root_resolved):
            generated_file.unlink()

entries = []
for path in sorted(ROOT.rglob("*")):
    if not path.is_file() or path.name == "manifest.json" or "__pycache__" in path.parts or path.suffix == ".pyc":
        continue
    entries.append({"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size})

(ROOT / "manifest.json").write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"manifest entries={len(entries)}")
