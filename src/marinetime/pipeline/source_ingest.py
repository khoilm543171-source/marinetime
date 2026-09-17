from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SourceIngestError(ValueError):
    """Raised when a local source cannot be represented safely."""


PROVENANCE_CLASSES = {
    "standard",
    "maker_manual",
    "regulatory",
    "textbook",
    "onboard_heuristic",
    "creator_experience",
    "case_specific",
    "unverified",
}


def sha256_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    source = Path(path)
    if not source.is_file():
        raise SourceIngestError("SOURCE_FILE_NOT_FOUND")
    if chunk_size <= 0:
        raise ValueError("CHUNK_SIZE_MUST_BE_POSITIVE")

    digest = hashlib.sha256()
    with source.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def build_local_video_source(
    *,
    path: str | Path,
    source_id: str,
    provenance_class: str,
    license_status: str | None = None,
    owner: str | None = None,
) -> dict[str, Any]:
    """Build a Source record without inventing identity or provenance.

    `source_id` and provenance are explicit caller inputs. Marinetime computes
    content identity from bytes but deliberately does not derive semantic source
    identity, ownership, or license status from the filename or file contents.
    """
    source = Path(path)
    if not source.is_file():
        raise SourceIngestError("SOURCE_FILE_NOT_FOUND")
    if not isinstance(source_id, str) or not source_id.strip():
        raise SourceIngestError("INVALID_SOURCE_ID")
    if source_id != source_id.strip():
        raise SourceIngestError("NONCANONICAL_SOURCE_ID")
    if provenance_class not in PROVENANCE_CLASSES:
        raise SourceIngestError(f"INVALID_PROVENANCE_CLASS:{provenance_class}")

    modified_time = datetime.fromtimestamp(source.stat().st_mtime, tz=timezone.utc).isoformat()
    record: dict[str, Any] = {
        "schema_version": "1.0",
        "source_id": source_id,
        "media_type": "video",
        "provenance_class": provenance_class,
        "content_hash": f"sha256:{sha256_file(source)}",
        "modified_time": modified_time,
        "license_status": license_status,
        "owner": owner,
    }
    return record
