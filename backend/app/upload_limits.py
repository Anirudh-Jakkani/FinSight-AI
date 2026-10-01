"""Bounded-memory CSV upload reading (Phase 8.6). /transactions/upload and
/pipeline/run both used to read an uploaded file with a bare `file.file.read()`
— a single unbounded allocation that pulls the *entire* upload into memory
before the existing max_upload_mb check ever got a chance to reject it. A
large or malicious upload would force the server to buffer all of it in RAM
first and only discover it was too big afterward.

read_upload_within_limit reads in fixed-size chunks and aborts the instant the
running total exceeds the configured limit, so memory use for a rejected
upload is capped at roughly one chunk over the limit — never the full
attacker-controlled size — while a valid upload under the limit is read and
returned exactly as before.
"""
from __future__ import annotations

from fastapi import HTTPException, UploadFile

_CHUNK_BYTES = 1024 * 1024  # 1 MB per read() call


def read_upload_within_limit(file: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = file.file.read(_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"file exceeds max upload size of {max_bytes // (1024 * 1024)} MB",
            )
        chunks.append(chunk)
    return b"".join(chunks)
