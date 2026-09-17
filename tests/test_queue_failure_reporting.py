from __future__ import annotations

import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_local_queue.py"

spec = importlib.util.spec_from_file_location("run_local_queue_script", SCRIPT)
assert spec is not None and spec.loader is not None
run_local_queue_script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_local_queue_script)

from marinetime.pilot.queue import enqueue_raw_folder, run_local_queue  # noqa: E402


class QueueFailureReportingTests(unittest.TestCase):
    def test_format_error_is_single_line_and_bounded(self) -> None:
        error = run_local_queue_script._format_error(RuntimeError("boom\nwith details"))
        self.assertEqual(error, "RuntimeError:boom with details")
        long_error = run_local_queue_script._format_error(RuntimeError("x" * 700))
        self.assertLessEqual(len(long_error), len("RuntimeError:") + 500)

    def test_failure_summary_lists_failed_job_and_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            raw.mkdir()
            (raw / "bad.mp4").write_bytes(b"bad-video")
            db = root / "queue.sqlite3"
            evidence = root / "evidence"
            enqueue_raw_folder(
                input_dir=raw,
                db_path=db,
                provenance_class="creator_experience",
            )

            def fail_processor(job, output_dir):
                raise RuntimeError("synthetic failure")

            result = run_local_queue(
                db_path=db,
                evidence_root=evidence,
                processor=fail_processor,
            )
            self.assertEqual(result.failed, 1)

            stream = io.StringIO()
            with redirect_stdout(stream):
                run_local_queue_script._print_failure_summary(db)
            output = stream.getvalue()
            self.assertIn("QUEUE_FAILURE_SUMMARY", output)
            self.assertIn("failed_jobs=1", output)
            self.assertIn("bad.mp4", output)
            self.assertIn("RuntimeError:synthetic failure", output)


if __name__ == "__main__":
    unittest.main()
