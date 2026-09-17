from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.pilot.queue import (  # noqa: E402
    EVIDENCE_READY,
    FAILED_PREPROCESS,
    PENDING,
    PREPROCESSING,
    claim_next_job,
    enqueue_raw_folder,
    list_jobs,
    requeue_failed_jobs,
    run_local_queue,
)


def _write_valid_evidence(output_dir: Path, source_id: str, provenance: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "source_id": source_id,
        "provenance_class": provenance,
        "context": {},
        "transcript_segments": [
            {
                "evidence_id": "SEG-001",
                "start_ms": 0,
                "end_ms": 1000,
                "text": "test evidence",
            }
        ],
        "ocr_hits": [],
        "frames": [],
        "preprocess_version": "queue_test_v1",
    }
    (output_dir / "evidence_pack.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


class LocalQueueTests(unittest.TestCase):
    def test_enqueue_folder_adds_three_unique_videos_and_skips_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            raw.mkdir()
            for index in range(3):
                (raw / f"video_{index}.mp4").write_bytes(f"video-{index}".encode())
            (raw / "ignore.txt").write_text("not a video", encoding="utf-8")
            db = root / "queue.sqlite3"

            first = enqueue_raw_folder(
                input_dir=raw,
                db_path=db,
                provenance_class="creator_experience",
            )
            second = enqueue_raw_folder(
                input_dir=raw,
                db_path=db,
                provenance_class="creator_experience",
            )

            self.assertEqual((first.discovered, first.enqueued, first.skipped_existing), (3, 3, 0))
            self.assertEqual((second.discovered, second.enqueued, second.skipped_existing), (3, 0, 3))
            self.assertEqual([job.status for job in list_jobs(db)], [PENDING, PENDING, PENDING])

    def test_worker_processes_jobs_sequentially(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            raw.mkdir()
            for index in range(3):
                (raw / f"video_{index}.mp4").write_bytes(f"unique-{index}".encode())
            db = root / "queue.sqlite3"
            evidence = root / "evidence"
            enqueue_raw_folder(
                input_dir=raw,
                db_path=db,
                provenance_class="creator_experience",
            )

            active = 0
            max_active = 0
            seen: list[str] = []

            def processor(job, output_dir):
                nonlocal active, max_active
                active += 1
                max_active = max(max_active, active)
                seen.append(job.video_path.name)
                _write_valid_evidence(output_dir, job.source_id, job.provenance_class)
                active -= 1

            result = run_local_queue(
                db_path=db,
                evidence_root=evidence,
                processor=processor,
            )

            self.assertEqual(result.processed, 3)
            self.assertEqual(result.ready, 3)
            self.assertEqual(result.failed, 0)
            self.assertEqual(max_active, 1)
            self.assertEqual(seen, ["video_0.mp4", "video_1.mp4", "video_2.mp4"])
            self.assertTrue(all(job.status == EVIDENCE_READY for job in list_jobs(db)))

    def test_failed_job_does_not_stop_later_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            raw.mkdir()
            for index in range(3):
                (raw / f"video_{index}.mp4").write_bytes(f"payload-{index}".encode())
            db = root / "queue.sqlite3"
            evidence = root / "evidence"
            enqueue_raw_folder(
                input_dir=raw,
                db_path=db,
                provenance_class="creator_experience",
            )

            def processor(job, output_dir):
                if job.video_path.name == "video_1.mp4":
                    raise RuntimeError("synthetic failure")
                _write_valid_evidence(output_dir, job.source_id, job.provenance_class)

            result = run_local_queue(
                db_path=db,
                evidence_root=evidence,
                processor=processor,
            )
            jobs = list_jobs(db)

            self.assertEqual((result.processed, result.ready, result.failed), (3, 2, 1))
            self.assertEqual(
                [job.status for job in jobs],
                [EVIDENCE_READY, FAILED_PREPROCESS, EVIDENCE_READY],
            )
            self.assertIn("synthetic failure", jobs[1].last_error or "")

    def test_interrupted_processing_is_recovered_on_next_worker_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            raw.mkdir()
            (raw / "video.mp4").write_bytes(b"interrupted")
            db = root / "queue.sqlite3"
            evidence = root / "evidence"
            enqueue_raw_folder(
                input_dir=raw,
                db_path=db,
                provenance_class="creator_experience",
            )

            claimed = claim_next_job(db)
            self.assertIsNotNone(claimed)
            self.assertEqual(list_jobs(db)[0].status, PREPROCESSING)
            partial = evidence / claimed.source_id
            partial.mkdir(parents=True)
            (partial / "audio.wav").write_bytes(b"partial")

            calls = 0

            def processor(job, output_dir):
                nonlocal calls
                calls += 1
                self.assertFalse((output_dir / "audio.wav").exists())
                _write_valid_evidence(output_dir, job.source_id, job.provenance_class)

            result = run_local_queue(
                db_path=db,
                evidence_root=evidence,
                processor=processor,
            )

            self.assertEqual(calls, 1)
            self.assertEqual(result.ready, 1)
            self.assertEqual(list_jobs(db)[0].status, EVIDENCE_READY)
            self.assertEqual(list_jobs(db)[0].attempts, 2)

    def test_existing_valid_evidence_is_adopted_without_reprocessing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            raw.mkdir()
            (raw / "video.mp4").write_bytes(b"existing-evidence")
            db = root / "queue.sqlite3"
            evidence = root / "evidence"
            enqueue_raw_folder(
                input_dir=raw,
                db_path=db,
                provenance_class="creator_experience",
            )
            job = list_jobs(db)[0]
            _write_valid_evidence(
                evidence / job.source_id, job.source_id, job.provenance_class
            )

            def processor(job, output_dir):
                self.fail("processor should not run when valid evidence already exists")

            result = run_local_queue(
                db_path=db,
                evidence_root=evidence,
                processor=processor,
            )

            self.assertEqual((result.processed, result.ready, result.failed), (1, 1, 0))
            self.assertEqual(list_jobs(db)[0].status, EVIDENCE_READY)

    def test_failed_jobs_require_explicit_requeue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            raw.mkdir()
            (raw / "video.mp4").write_bytes(b"retry")
            db = root / "queue.sqlite3"
            enqueue_raw_folder(
                input_dir=raw,
                db_path=db,
                provenance_class="creator_experience",
            )

            def fail_processor(job, output_dir):
                raise RuntimeError("fail once")

            run_local_queue(
                db_path=db,
                evidence_root=root / "evidence",
                processor=fail_processor,
            )
            self.assertEqual(list_jobs(db)[0].status, FAILED_PREPROCESS)
            self.assertEqual(requeue_failed_jobs(db), 1)
            self.assertEqual(list_jobs(db)[0].status, PENDING)


if __name__ == "__main__":
    unittest.main()
