from __future__ import annotations

import os
import uvicorn


if __name__ == "__main__":
    configured_workers = int(os.getenv("PAPERPLANE_WORKERS", "4"))
    # Uvicorn's multi-process worker startup is not reliable on Windows with
    # Python 3.14/asyncio (it can fail with WinError 10022). Keep the Linux
    # container default at four workers, but always use one process on Windows.
    workers = 1 if os.name == "nt" else max(1, configured_workers)
    uvicorn.run(
        "server:app",
        host=os.getenv("PAPERPLANE_HOST", "127.0.0.1"),
        port=int(os.getenv("PAPERPLANE_PORT", "8501")),
        workers=workers,
        reload=False,
    )

