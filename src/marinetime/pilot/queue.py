from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from marinetime.pipeline.evidence_pack import validate_evidence_pack
from marinetime.pipeline.source_ingest import sha256_file

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}

PENDING = "PENDING"
PREPROCESSING = "PREPROCESSING"
EVIDENCE_READY = "EVIDENCE_READY"
FAILED_PREPROCESS = "FAILED_PREPROCESS"


@dataclass(frozen=True)
class QueueJob:
    job_id: int
    source_id: str
    video_path: Path
    content_hash: str
    provenance_class: str
    context: dict
    status: str
    stage: str
    attempts: int
    last_error: str | None


@dataclass(frozen=True)
class EnqueueResult:
    discovered: int
    enqueued: int
    skipped_existing: int


@dataclass(frozen=True)
class WorkerResult:
    processed: int
    ready: int
    failed: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_queue(db_path: str | Path) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_video_jobs (
                job_id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL UNIQUE,
                video_path TEXT NOT NULL,
                content_hash TEXT NOT NULL UNIQUE,
                provenance_class TEXT NOT NULL,
                context_json TEXT NOT NULL,
                status TEXT NOT NULL,
                stage TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_raw_video_jobs_status ON raw_video_jobs(status, job_id)"
        )


def _stable_source_id(content_hash: str) -> str:
    return f"RAW-{content_hash[:16].upper()}"


def _iter_videos(input_dir: Path, *, recursive: bool) -> Iterable[Path]:
    iterator = input_dir.rglob("*") if recursive else input_dir.iterdir()
    for path in sorted(iterator, key=lambda value: value.as_posix().lower()):
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            yield path


def enqueue_raw_folder(
    *,
    input_dir: str | Path,
    db_path: str | Path,
    provenance_class: str,
    context: dict | None = None,
    recursive: bool = False,
) -> EnqueueResult:
    root = Path(input_dir)
    if not root.is_dir():
        raise ValueError("RAW_INPUT_DIR_NOT_FOUND")
    if not provenance_class.strip():
        raise ValueError("PROVENANCE_REQUIRED")

    init_queue(db_path)
    discovered = 0
    enqueued = 0
    skipped = 0
    context_json = json.dumps(context or {}, ensure_ascii=False, sort_keys=True)

    with _connect(db_path) as conn:
        for video in _iter_videos(root, recursive=recursive):
            discovered += 1
            digest = sha256_file(video)
            now = _utc_now()
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO raw_video_jobs (
                    source_id, video_path, content_hash, provenance_class, context_json,
                    status, stage, attempts, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    _stable_source_id(digest),
                    str(video.resolve()),
                    digest,
                    provenance_class,
                    context_json,
                    PENDING,
                    "QUEUED",
                    now,
                    now,
                ),
            )
            if cursor.rowcount == 1:
                enqueued += 1
            else:
                skipped += 1

    return EnqueueResult(discovered=discovered, enqueued=enqueued, skipped_existing=skipped)


def _row_to_job(row: sqlite3.Row) -> QueueJob:
    context = json.loads(row["context_json"])
    if not isinstance(context, dict):
        raise ValueError("QUEUE_CONTEXT_NOT_OBJECT")
    return QueueJob(
        job_id=int(row["job_id"]),
        source_id=str(row["source_id"]),
        video_path=Path(row["video_path"]),
        content_hash=str(row["content_hash"]),
        provenance_class=str(row["provenance_class"]),
        context=context,
        status=str(row["status"]),
        stage=str(row["stage"]),
        attempts=int(row["attempts"]),
        last_error=row["last_error"],
    )


def list_jobs(db_path: str | Path) -> list[QueueJob]:
    init_queue(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM raw_video_jobs ORDER BY job_id").fetchall()
    return [_row_to_job(row) for row in rows]


def recover_interrupted_jobs(db_path: str | Path) -> int:
    init_queue(db_path)
    now = _utc_now()
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE raw_video_jobs
            SET status = ?, stage = ?, last_error = ?, updated_at = ?, started_at = NULL
            WHERE status = ?
            """,
            (PENDING, "QUEUED", "INTERRUPTED_PREVIOUS_RUN", now, PREPROCESSING),
        )
        return cursor.rowcount


def requeue_failed_jobs(db_path: str | Path) -> int:
    init_queue(db_path)
    now = _utc_now()
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE raw_video_jobs
            SET status = ?, stage = ?, last_error = NULL, updated_at = ?,
                started_at = NULL, finished_at = NULL
            WHERE status = ?
            """,
            (PENDING, "QUEUED", now, FAILED_PREPROCESS),
        )
        return cursor.rowcount


def claim_next_job(db_path: str | Path) -> QueueJob | None:
    init_queue(db_path)
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM raw_video_jobs WHERE status = ? ORDER BY job_id LIMIT 1",
            (PENDING,),
        ).fetchone()
        if row is None:
            conn.commit()
            return None
        now = _utc_now()
        conn.execute(
            """
            UPDATE raw_video_jobs
            SET status = ?, stage = ?, attempts = attempts + 1,
                last_error = NULL, started_at = ?, finished_at = NULL, updated_at = ?
            WHERE job_id = ? AND status = ?
            """,
            (PREPROCESSING, "LOCAL_PREPROCESS", now, now, row["job_id"], PENDING),
        )
        updated = conn.execute(
            "SELECT * FROM raw_video_jobs WHERE job_id = ?", (row["job_id"],)
        ).fetchone()
        conn.commit()
        return _row_to_job(updated)
    finally:
        conn.close()


def _finish_job(
    db_path: str | Path,
    *,
    job_id: int,
    status: str,
    stage: str,
    last_error: str | None,
) -> None:
    now = _utc_now()
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE raw_video_jobs
            SET status = ?, stage = ?, last_error = ?, finished_at = ?, updated_at = ?
            WHERE job_id = ?
            """,
            (status, stage, last_error, now, now, job_id),
        )


def _existing_evidence_is_valid(output_dir: Path, source_id: str) -> bool:
    path = output_dir / "evidence_pack.json"
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        summary = validate_evidence_pack(payload)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return summary.source_id == source_id


def _clear_partial_output(output_dir: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)


def run_local_queue(
    *,
    db_path: str | Path,
    evidence_root: str | Path,
    processor: Callable[[QueueJob, Path], object],
    limit: int | None = None,
) -> WorkerResult:
    """Process queued raw videos one at a time. This function never calls Opus itself."""
    if limit is not None and limit <= 0:
        raise ValueError("QUEUE_LIMIT_MUST_BE_POSITIVE")

    recover_interrupted_jobs(db_path)
    root = Path(evidence_root)
    root.mkdir(parents=True, exist_ok=True)

    processed = 0
    ready = 0
    failed = 0

    while limit is None or processed < limit:
        job = claim_next_job(db_path)
        if job is None:
            break
        processed += 1
        output_dir = root / job.source_id

        if _existing_evidence_is_valid(output_dir, job.source_id):
            _finish_job(
                db_path,
                job_id=job.job_id,
                status=EVIDENCE_READY,
                stage="WAITING_FOR_ALU",
                last_error=None,
            )
            ready += 1
            continue

        _clear_partial_output(output_dir)
        try:
            processor(job, output_dir)
            if not _existing_evidence_is_valid(output_dir, job.source_id):
                raise ValueError("PROCESSOR_DID_NOT_CREATE_VALID_EVIDENCE_PACK")
        except Exception as exc:
            detail = " ".join(str(exc).split())[:500]
            _finish_job(
                db_path,
                job_id=job.job_id,
                status=FAILED_PREPROCESS,
                stage="FAILED",
                last_error=f"{type(exc).__name__}:{detail}",
            )
            failed += 1
            continue

        _finish_job(
            db_path,
            job_id=job.job_id,
            status=EVIDENCE_READY,
            stage="WAITING_FOR_ALU",
            last_error=None,
        )
        ready += 1

    return WorkerResult(processed=processed, ready=ready, failed=failed)
