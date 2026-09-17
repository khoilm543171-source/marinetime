from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.pilot.preflight import (
    Capability,
    LocalStackReport,
    _executable_capability,
    _python_module_capability,
)


class PilotPreflightTests(unittest.TestCase):
    def test_report_lists_only_missing_required_capabilities(self) -> None:
        report = LocalStackReport(
            capabilities=(
                Capability("ffmpeg", "executable", True, True, "ffmpeg version test"),
                Capability("whisperx", "python_module", True, False),
                Capability("nvidia-smi", "executable", False, False),
            )
        )
        self.assertFalse(report.raw_video_ready)
        self.assertEqual(report.missing_required, ("whisperx",))

    def test_ready_when_every_required_capability_exists(self) -> None:
        report = LocalStackReport(
            capabilities=(
                Capability("ffmpeg", "executable", True, True),
                Capability("whisperx", "python_module", True, True),
                Capability("nvidia-smi", "executable", False, False),
            )
        )
        self.assertTrue(report.raw_video_ready)
        self.assertEqual(report.missing_required, ())

    @patch("marinetime.pilot.preflight.shutil.which", return_value=None)
    def test_missing_executable_is_reported_without_running_command(self, mocked_which) -> None:
        result = _executable_capability("ffmpeg", ["-version"], required=True)
        self.assertFalse(result.available)
        self.assertTrue(result.required_for_raw_video)
        mocked_which.assert_called_once_with("ffmpeg")

    @patch("marinetime.pilot.preflight.importlib.util.find_spec", return_value=object())
    def test_python_module_detection_uses_import_spec_without_importing_module(self, mocked) -> None:
        result = _python_module_capability("whisperx", required=True)
        self.assertTrue(result.available)
        mocked.assert_called_once_with("whisperx")


if __name__ == "__main__":
    unittest.main()
