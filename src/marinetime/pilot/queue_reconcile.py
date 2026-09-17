from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from marinetime.pipeline.evidence_pack import validate_evidence_pack
from marinetime.pilot.queue import EVIDENCE_READY, FAILED_PREPROCESS, PENDING, init_queue


@dataclass(frozen=True)
class ExistingEvidence:
    source_id: str
    content_hash: str
    provenance_class: str
    context: dict[str, Any]


@dataclass(frozen=True)
class ReconcileResult:
    scanned_artifacts: int
    adopted_jobs: int
    skipped_invalid_artifacts: int
    skipped_conflicts: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_sha256(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if text.startswith("sha256:"):
        text = text[7:]
    if len(text) != 64:
        return None
    try:
        int(text, 16)
    except ValueError:
        return None
    return text


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON_NOT_OBJECT")
    return payload


def discover_existing_evidence(evidence_root: str | Path) -> tuple[dict[str, ExistingEvidence], int, int]:
    """Index complete local evidence by original video content hash.

    Only artifacts with both a valid source.json and a valid EvidencePack are eligible.
    Ambiguous duplicate hashes are intentionally omitted from the index.
    """
    root = Path(evidence_root)
    if not root.is_dir():
        return {}, 0, 0

    scanned = 0
    invalid = 0
    candidates: dict[str, ExistingEvidence] = {}
    ambiguous: set[str] = set()

    for directory in sorted(root.iterdir(), key=lambda value: value.name.lower()):
        if not directory.is_dir():
            continue
        source_path = directory / "source.json"
        evidence_path = directory / "evidence_pack.json"
        if not source_path.is_file() or not evidence_path.is_file():
            continue
        scanned += 1
        try:
            source = _load_json_object(source_path)
            pack = _load_json_object(evidence_path)
            summary = validate_evidence_pack(pack)
            source_id = source.get("source_id")
            digest = _normalize_sha256(source.get("content_hash"))
            provenance = source.get("provenance_class")
            context = pack.get("context")
            if (
                not isinstance(source_id, str)
                or source_id != summary.source_id
                or digest is None
                or not isinstance(provenance, str)
                or provenance != summary.provenance_class
                or not isinstance(context, dict)
            ):
                raise ValueError("ARTIFACT_IDENTITY_MISMATCH")
        except (OSError, ValueError, json.JSONDecodeError):
            invalid += 1
            continue

        record = ExistingEvidence(
            source_id=source_id,
            content_hash=digest,
            provenance_class=provenance,
            context=context,
        )
        previous = candidates.get(digest)
        if previous is not None and previous.source_id != source_id:
            ambiguous.add(digest)
            continue
        candidates[digest] = record

    for digest in ambiguous:
        candidates.pop(digest, None)

    return candidates, scanned, invalid


def reconcile_queue_with_existing_evidence(
    *,
    db_path: str | Path,
    evidence_root: str | Path,
) -> ReconcileResult:
    """Adopt already-processed raw videos instead of preprocessing them again.

    This is intentionally limited to queued/failed jobs. A currently processing job is
    left untouched so a live worker cannot have its identity changed underneath it.
    """
    init_queue(db_path)
    existing, scanned, invalid = discover_existing_evidence(evidence_root)
    if not existing:
        return ReconcileResult(scanned, 0, invalid, 0)

    adopted = 0
    conflicts = 0
    path = Path(db_path)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT job_id, source_id, content_hash, status FROM raw_video_jobs ORDER BY job_id"
        ).fetchall()
        for row in rows:
            if row["status"] not in {PENDING, FAILED_PREPROCESS}:
                continue
            record = existing.get(str(row["content_hash"]).lower())
            if record is None:
                continue

            conflict = conn.execute(
                "SELECT job_id FROM raw_video_jobs WHERE source_id = ? AND job_id <> ?",
                (record.source_id, row["job_id"]),
            ).fetchone()
            if conflict is not None:
                conflicts += 1
                continue

            now = _utc_now()
            conn.execute(
                """
                UPDATE raw_video_jobs
                SET source_id = ?, provenance_class = ?, context_json = ?,
                    status = ?, stage = ?, last_error = NULL,
                    started_at = NULL, finished_at = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (
                    record.source_id,
                    record.provenance_class,
                    json.dumps(record.context, ensure_ascii=False, sort_keys=True),
                    EVIDENCE_READY,
                    "WAITING_FOR_ALU",
                    now,
                    now,
                    row["job_id"],
                ),
            )
            adopted += 1
        conn.commit()
    finally:
        conn.close()

    return ReconcileResult(scanned, adopted, invalid, conflicts)
