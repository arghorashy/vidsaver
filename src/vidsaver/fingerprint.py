"""Sample-hash identity for a video file.

``content_id`` is ``size`` plus a SHA-256 of the first and last 1 MiB.
That is enough to treat rename/move as the same file without reading the
whole thing. A re-encode changes the samples and gets a new id.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

SAMPLE_BYTES = 1024 * 1024


class FingerprintError(Exception):
    """The file could not be read for hashing."""


def content_id_for(path: Path) -> str:
    """Return a stable id for *path*'s current bytes."""
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            digest = hashlib.sha256()
            handle.seek(0)
            digest.update(handle.read(SAMPLE_BYTES))
            if size > SAMPLE_BYTES:
                handle.seek(max(size - SAMPLE_BYTES, SAMPLE_BYTES))
                digest.update(handle.read(SAMPLE_BYTES))
    except OSError as exc:
        raise FingerprintError(f"Cannot read {path}: {exc}") from exc
    return f"{size}:{digest.hexdigest()}"
