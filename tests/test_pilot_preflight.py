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
    _python_runtime_capability,
    check_local_stack,
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

    def test_python_311_is_supported_for_ml_pilot(self) -> None:
        result = _python_runtime_capability((3, 11, 9))
        self.assertTrue(result.available)
        self.assertIn("recommended=3.11", result.detail or "")

    def test_python_314_is_blocked_for_ml_pilot(self) -> None:
        result = _python_runtime_capability((3, 14, 0))
        self.assertFalse(result.available)
        self.assertEqual(result.name, "python_ml_runtime")
        self.assertTrue(result.required_for_raw_video)

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

    @patch("marinetime.pilot.preflight._python_runtime_capability")
    @patch("marinetime.pilot.preflight._python_module_capability")
    @patch("marinetime.pilot.preflight._executable_capability")
    def test_gpu_probe_requests_useful_device_details(self, executable, module, runtime) -> None:
        runtime.return_value = Capability("python_ml_runtime", "python_runtime", True, True, "ok")
        executable.side_effect = lambda name, args, required: Capability(
            name, "executable", required, True, "ok"
        )
        module.side_effect = lambda name, required: Capability(
            name, "python_module", required, True, "ok"
        )

        check_local_stack()

        self.assertEqual(
            executable.call_args_list[-1].args,
            (
                "nvidia-smi",
                [
                    "--query-gpu=name,driver_version,memory.total",
                    "--format=csv,noheader",
                ],
            ),
        )
        self.assertFalse(executable.call_args_list[-1].kwargs["required"])


if __name__ == "__main__":
    unittest.main()
