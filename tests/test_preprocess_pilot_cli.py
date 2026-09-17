from __future__ import annotations

import contextlib
import importlib.util
import io
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "preprocess_pilot_video.py"
SPEC = importlib.util.spec_from_file_location("preprocess_pilot_video", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PilotPreprocessCliTests(unittest.TestCase):
    def test_heartbeat_reports_elapsed_time_until_stopped(self) -> None:
        stop_event = threading.Event()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            thread = threading.Thread(
                target=MODULE._heartbeat,
                args=(stop_event,),
                kwargs={"interval_seconds": 0.01},
                daemon=True,
            )
            thread.start()
            time.sleep(0.03)
            stop_event.set()
            thread.join(timeout=1)

        self.assertIn("PILOT_PREPROCESS_RUNNING elapsed_seconds=", output.getvalue())
        self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
