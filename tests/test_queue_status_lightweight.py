from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "queue_status.py"


class QueueStatusLightweightTests(unittest.TestCase):
    def test_status_runs_without_site_packages_or_llm_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db = root / "queue.sqlite3"
            evidence_root = root / "evidence"
            source_id = "RAW-TEST"

            with sqlite3.connect(db) as conn:
                conn.execute(
                    """
                    CREATE TABLE raw_video_jobs (
                        job_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        source_id TEXT NOT NULL UNIQUE,
                        video_path TEXT NOT NULL,
                        content_hash TEXT NOT NULL UNIQUE,
                        provenance_class TEXT NOT NULL,
                        context_json TEXT NOT NULL,
                        status TEXT NOT NULL,
                        stage TEXT NOT NULL,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        last_error TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO raw_video_jobs (
                        source_id, video_path, content_hash, provenance_class,
                        context_json, status, stage, attempts, last_error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source_id,
                        str(root / "video.mp4"),
                        "sha256:test",
                        "creator_experience",
                        "{}",
                        "EVIDENCE_READY",
                        "DONE",
                        1,
                        None,
                    ),
                )

            folder = evidence_root / source_id
            folder.mkdir(parents=True)
            (folder / "evidence_pack.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "source_id": source_id,
                        "provenance_class": "creator_experience",
                        "context": {},
                        "transcript_segments": [],
                        "ocr_hits": [],
                        "frames": [],
                        "preprocess_version": "test",
                    }
                ),
                encoding="utf-8",
            )
            (folder / "alus.json").write_text(
                json.dumps({"source_id": source_id, "alus": [{"alu": {}}]}),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    str(SCRIPT),
                    "--db",
                    str(db),
                    "--evidence-root",
                    str(evidence_root),
                    "--summary-only",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("QUEUE_STATUS", result.stdout)
            self.assertIn("evidence_ready=1", result.stdout)
            self.assertIn("ALU_STATUS", result.stdout)
            self.assertIn("evidence_packs=1", result.stdout)
            self.assertIn("alus_completed=1", result.stdout)
            self.assertIn("missing_alus=0", result.stdout)


if __name__ == "__main__":
    unittest.main()
