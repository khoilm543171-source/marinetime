from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class EvidencePackError(ValueError):
    """Raised when an EvidencePack cannot be safely used downstream."""


SUPPORTED_EVIDENCE_SCHEMA_VERSION = "1.0"
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
REQUIRED_TOP_LEVEL = (
    "schema_version",
    "source_id",
    "provenance_class",
    "context",
    "transcript_segments",
    "ocr_hits",
    "frames",
    "preprocess_version",
)
EVIDENCE_COLLECTIONS = ("transcript_segments", "ocr_hits", "frames")


@dataclass(frozen=True)
class EvidencePackSummary:
    source_id: str
    provenance_class: str
    evidence_ids: frozenset[str]
    transcript_count: int
    ocr_count: int
    frame_count: int


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_timestamp_ms(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value >= 0
    )


def validate_evidence_pack(pack: dict[str, Any]) -> EvidencePackSummary:
    """Validate traceability invariants before any semantic LLM call.

    This function rejects malformed evidence instead of repairing it. Stable ids,
    modality timestamps, source text, provenance, and context must already be
    present from deterministic preprocessing/upstream source handling.
    """
    if not isinstance(pack, dict):
        raise EvidencePackError("EVIDENCE_PACK_NOT_OBJECT")

    missing = [key for key in REQUIRED_TOP_LEVEL if key not in pack]
    if missing:
        raise EvidencePackError("MISSING_TOP_LEVEL:" + ",".join(missing))

    source_id = pack.get("source_id")
    if not _nonempty_string(source_id):
        raise EvidencePackError("INVALID_SOURCE_ID")
    if source_id != source_id.strip():
        raise EvidencePackError("NONCANONICAL_SOURCE_ID")

    schema_version = pack.get("schema_version")
    if not _nonempty_string(schema_version):
        raise EvidencePackError("INVALID_SCHEMA_VERSION")
    if schema_version != SUPPORTED_EVIDENCE_SCHEMA_VERSION:
        raise EvidencePackError(f"UNSUPPORTED_SCHEMA_VERSION:{schema_version}")

    preprocess_version = pack.get("preprocess_version")
    if not _nonempty_string(preprocess_version):
        raise EvidencePackError("INVALID_PREPROCESS_VERSION")

    provenance_class = pack.get("provenance_class")
    if provenance_class not in PROVENANCE_CLASSES:
        raise EvidencePackError(f"INVALID_PROVENANCE_CLASS:{provenance_class}")
    if not isinstance(pack.get("context"), dict):
        raise EvidencePackError("INVALID_CONTEXT")

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
            if evidence_id != evidence_id.strip():
                raise EvidencePackError(
                    f"{collection.upper()}_{index}_NONCANONICAL_EVIDENCE_ID"
                )
            if evidence_id in evidence_ids:
                raise EvidencePackError(f"DUPLICATE_EVIDENCE_ID:{evidence_id}")
            evidence_ids.add(evidence_id)

            if collection == "transcript_segments":
                start_ms = item.get("start_ms")
                end_ms = item.get("end_ms")
                if not _valid_timestamp_ms(start_ms) or not _valid_timestamp_ms(end_ms):
                    raise EvidencePackError(f"TRANSCRIPT_{index}_INVALID_TIMESTAMP")
                if end_ms < start_ms:
                    raise EvidencePackError(f"TRANSCRIPT_{index}_INVALID_TIMESTAMP_RANGE")
                if not _nonempty_string(item.get("text")):
                    raise EvidencePackError(f"TRANSCRIPT_{index}_MISSING_TEXT")

            elif collection == "ocr_hits":
                if not _valid_timestamp_ms(item.get("timestamp_ms")):
                    raise EvidencePackError(f"OCR_{index}_INVALID_TIMESTAMP")
                if not _nonempty_string(item.get("text")):
                    raise EvidencePackError(f"OCR_{index}_MISSING_TEXT")

            elif collection == "frames":
                timestamp_ms = item.get("timestamp_ms")
                if not _valid_timestamp_ms(timestamp_ms):
                    raise EvidencePackError(f"FRAME_{index}_INVALID_TIMESTAMP")

                requested_timestamp_ms = item.get("requested_timestamp_ms")
                fallback_reason = item.get("timestamp_fallback_reason")
                if requested_timestamp_ms is not None and not _valid_timestamp_ms(
                    requested_timestamp_ms
                ):
                    raise EvidencePackError(
                        f"FRAME_{index}_INVALID_REQUESTED_TIMESTAMP"
                    )
                if fallback_reason is not None:
                    if fallback_reason != "NO_FRAME_AT_REQUESTED_TIMESTAMP":
                        raise EvidencePackError(
                            f"FRAME_{index}_INVALID_TIMESTAMP_FALLBACK_REASON"
                        )
                    if requested_timestamp_ms is None:
                        raise EvidencePackError(
                            f"FRAME_{index}_FALLBACK_WITHOUT_REQUESTED_TIMESTAMP"
                        )
                    if timestamp_ms == requested_timestamp_ms:
                        raise EvidencePackError(
                            f"FRAME_{index}_FALLBACK_WITHOUT_TIMESTAMP_CHANGE"
                        )
                elif (
                    requested_timestamp_ms is not None
                    and timestamp_ms != requested_timestamp_ms
                ):
                    raise EvidencePackError(
                        f"FRAME_{index}_TIMESTAMP_CHANGED_WITHOUT_FALLBACK_REASON"
                    )

    if not evidence_ids:
        raise EvidencePackError("NO_EVIDENCE")

    return EvidencePackSummary(
        source_id=source_id,
        provenance_class=str(provenance_class),
        evidence_ids=frozenset(evidence_ids),
        transcript_count=counts["transcript_segments"],
        ocr_count=counts["ocr_hits"],
        frame_count=counts["frames"],
    )
