"""Controlled child process used to prove timeout termination end to end."""
from __future__ import annotations

import os
import json
from pathlib import Path
import time
import psutil


def block_after_start(result_pipe, source, output, operation, options, image_path):
    del output, operation, options
    source_path = Path(source)
    marker = source_path.parent / ".watermark-worker-started"
    marker.write_text(json.dumps({"pid": os.getpid(), "created": psutil.Process().create_time()}), encoding="ascii")
    if image_path:
        with Path(image_path).open("rb"):
            time.sleep(30)
    else:
        time.sleep(30)

