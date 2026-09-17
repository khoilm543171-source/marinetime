from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.pilot.queue import EVIDENCE_READY, PENDING, enqueue_raw_folder, list_jobs  # noqa: E402
from marinetime.pilot.queue_reconcile import (  # noqa: E402
    discover_existing_evidence,
    reconcile_queue_with_existing_evidence,
)
from marinetime.pipeline.source_ingest import sha256_file  # noqa: E402


def _write_existing_artifacts(root: Path, video: Path, source_id: str) -> None:
    out = root / source_id
    out.mkdir(parents=True)
    digest = sha256_file(video)
    source = {
        "schema_version": "1.0",
        "source_id": source_id,
        "media_type": "video",
        "provenance_class": "creator_experience",
        "content_hash": f"sha256:{digest}",
        "modified_time": "2026-01-01T00:00:00+00:00",
        "license_status": None,
        "owner": None,
    }
    pack = {
        "schema_version": "1.0",
        "source_id": source_id,
        "provenance_class": "creator_experience",
        "context": {"equipment": "unknown"},
        "transcript_segments": [
            {
                "evidence_id": "SEG-001",
                "start_ms": 0,
                "end_ms": 1000,
                "text": "existing evidence",
            }
        ],
        "ocr_hits": [],
        "frames": [],
        "preprocess_version": "legacy_test_v1",
    }
    (out / "source.json").write_text(json.dumps(source), encoding="utf-8")
    (out / "evidence_pack.json").write_text(json.dumps(pack), encoding="utf-8")


class QueueReconcileTests(unittest.TestCase):
    def test_existing_pre_queue_video_is_adopted_and_not_left_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            raw.mkdir()
            old_video = raw / "old.mp4"
            new_video = raw / "new.mp4"
            old_video.write_bytes(b"already-processed-video")
            new_video.write_bytes(b"brand-new-video")
            evidence = root / "evidence"
            _write_existing_artifacts(evidence, old_video, "SMOKE-VID-001")
            db = root / "queue.sqlite3"

            enqueue_raw_folder(
                input_dir=raw,
                db_path=db,
                provenance_class="creator_experience",
            )
            before = list_jobs(db)
            self.assertEqual([job.status for job in before], [PENDING, PENDING])

            result = reconcile_queue_with_existing_evidence(
                db_path=db,
                evidence_root=evidence,
            )
            jobs = list_jobs(db)

            self.assertEqual(result.adopted_jobs, 1)
            old_job = next(job for job in jobs if job.video_path.name == "old.mp4")
            new_job = next(job for job in jobs if job.video_path.name == "new.mp4")
            self.assertEqual(old_job.source_id, "SMOKE-VID-001")
            self.assertEqual(old_job.status, EVIDENCE_READY)
            self.assertEqual(old_job.stage, "WAITING_FOR_ALU")
            self.assertEqual(old_job.context, {"equipment": "unknown"})
            self.assertEqual(new_job.status, PENDING)

    def test_invalid_or_hashless_artifacts_are_not_adopted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            raw.mkdir()
            video = raw / "video.mp4"
            video.write_bytes(b"video")
            evidence = root / "evidence" / "BROKEN"
            evidence.mkdir(parents=True)
            (evidence / "source.json").write_text("{}", encoding="utf-8")
            (evidence / "evidence_pack.json").write_text("{}", encoding="utf-8")
            db = root / "queue.sqlite3"
            enqueue_raw_folder(
                input_dir=raw,
                db_path=db,
                provenance_class="creator_experience",
            )

            result = reconcile_queue_with_existing_evidence(
                db_path=db,
                evidence_root=root / "evidence",
            )

            self.assertEqual(result.adopted_jobs, 0)
            self.assertEqual(result.skipped_invalid_artifacts, 1)
            self.assertEqual(list_jobs(db)[0].status, PENDING)

    def test_discovery_normalizes_sha256_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "video.mp4"
            video.write_bytes(b"normalized")
            evidence = root / "evidence"
            _write_existing_artifacts(evidence, video, "LEGACY-001")

            index, scanned, invalid = discover_existing_evidence(evidence)
            digest = sha256_file(video)

            self.assertEqual((scanned, invalid), (1, 0))
            self.assertIn(digest, index)
            self.assertEqual(index[digest].source_id, "LEGACY-001")


if __name__ == "__main__":
    unittest.main()
