from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class EvidencePackError(ValueError):
    """Raised when an EvidencePack cannot be safely used downstream."""


REQUIRED_TOP_LEVEL = (
    "schema_version",
    "source_id",
    "transcript_segments",
    "ocr_hits",
    "frames",
    "preprocess_version",
)
EVIDENCE_COLLECTIONS = ("transcript_segments", "ocr_hits", "frames")


@dataclass(frozen=True)
class EvidencePackSummary:
    source_id: str
    evidence_ids: frozenset[str]
    transcript_count: int
    ocr_count: int
    frame_count: int


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_evidence_pack(pack: dict[str, Any]) -> EvidencePackSummary:
    """Validate the traceability invariants required before any LLM call.

    This intentionally does not infer or repair missing evidence. Every reusable
    evidence item must already have a stable ``evidence_id`` produced by the
    deterministic preprocessing stage.
    """
    if not isinstance(pack, dict):
        raise EvidencePackError("EVIDENCE_PACK_NOT_OBJECT")

    missing = [key for key in REQUIRED_TOP_LEVEL if key not in pack]
    if missing:
        raise EvidencePackError("MISSING_TOP_LEVEL:" + ",".join(missing))

    if not _nonempty_string(pack.get("source_id")):
        raise EvidencePackError("INVALID_SOURCE_ID")
    if not _nonempty_string(pack.get("schema_version")):
        raise EvidencePackError("INVALID_SCHEMA_VERSION")
    if not _nonempty_string(pack.get("preprocess_version")):
        raise EvidencePackError("INVALID_PREPROCESS_VERSION")

    evidence_ids: set[str] = set()
    counts: dict[str, int] = {}

    for collection in EVIDENCE_COLLECTIONS:
        items = pack.get(collection)
        if not isinstance(items, list):
            raise EvidencePackError(f"{collection.upper()}_NOT_ARRAY")
        counts[collection] = len(items)

        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise EvidencePackError(f"{collection.upper()}_{index}_NOT_OBJECT")
            evidence_id = item.get("evidence_id")
            if not _nonempty_string(evidence_id):
                raise EvidencePackError(f"{collection.upper()}_{index}_MISSING_EVIDENCE_ID")
            evidence_id = str(evidence_id).strip()
            if evidence_id in evidence_ids:
                raise EvidencePackError(f"DUPLICATE_EVIDENCE_ID:{evidence_id}")
            evidence_ids.add(evidence_id)

            if collection == "transcript_segments":
                start_ms = item.get("start_ms")
                end_ms = item.get("end_ms")
                if start_ms is not None and end_ms is not None:
                    if not isinstance(start_ms, (int, float)) or not isinstance(end_ms, (int, float)):
                        raise EvidencePackError(f"TRANSCRIPT_{index}_INVALID_TIMESTAMP")
                    if start_ms < 0 or end_ms < start_ms:
                        raise EvidencePackError(f"TRANSCRIPT_{index}_INVALID_TIMESTAMP_RANGE")

    if not evidence_ids:
        raise EvidencePackError("NO_EVIDENCE")

    return EvidencePackSummary(
        source_id=str(pack["source_id"]).strip(),
        evidence_ids=frozenset(evidence_ids),
        transcript_count=counts["transcript_segments"],
        ocr_count=counts["ocr_hits"],
        frame_count=counts["frames"],
    )
