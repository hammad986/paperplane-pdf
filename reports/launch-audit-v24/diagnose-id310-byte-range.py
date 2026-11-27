from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import converters

results = []
with TemporaryDirectory(prefix="paperplane-id310-range-") as temporary:
    root = Path(temporary)
    pixels = 350 * 450 * 3
    for seed in range(310, 350):
        source = root / f"source-{seed}.jpg"
        Image.frombytes("RGB", (350, 450), random.Random(seed).randbytes(pixels)).save(
            source, format="JPEG", quality=86, optimize=True)
        output = converters.resize_exam_image(source, root / f"out-{seed}.jpg", preset="ssc_photo")
        item = {"seed": seed, "source_bytes": source.stat().st_size, "output_bytes": output.stat().st_size}
        results.append(item)
        if 50_000 < output.stat().st_size <= 51_200:
            break
print(json.dumps({"samples": results, "boundary_fixture_found": any(50_000 < x["output_bytes"] <= 51_200 for x in results)}, indent=2))
