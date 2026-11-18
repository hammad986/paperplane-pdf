from __future__ import annotations

import tracemalloc

import pytest

import server


class _GeneratedUpload:
    def __init__(self, size: int):
        self.remaining = size
        self.read_sizes: list[int] = []
        self.file = self

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if self.remaining <= 0:
            return b""
        chunk_size = min(size, self.remaining)
        self.remaining -= chunk_size
        return b"x" * chunk_size


def test_upload_spooling_reads_fixed_chunks_and_keeps_peak_heap_bounded(tmp_path):
    upload = _GeneratedUpload(8 * 1024 * 1024)
    destination = tmp_path / "large-upload.bin"

    tracemalloc.start()
    try:
        server.save_upload_spooled(upload, destination)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert destination.stat().st_size == 8 * 1024 * 1024
    assert max(upload.read_sizes) == 64 * 1024
    assert peak < 512 * 1024


def test_upload_spooling_removes_partial_file_when_limit_is_exceeded(tmp_path):
    upload = _GeneratedUpload(128 * 1024)
    destination = tmp_path / "too-large.bin"

    with pytest.raises(server.HTTPException) as error:
        server.save_upload_spooled(upload, destination, max_bytes=64 * 1024)

    assert error.value.status_code == 413
    assert not destination.exists()
