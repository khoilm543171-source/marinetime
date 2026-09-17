from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.pilot.media import _run


class MediaEncodingTests(unittest.TestCase):
    @patch("marinetime.pilot.media.subprocess.run")
    def test_run_decodes_tool_output_as_utf8_with_replacement(self, mocked_run) -> None:
        mocked_run.return_value = subprocess.CompletedProcess(["tool"], 0, "ok", "")

        result = _run(["tool"])

        self.assertEqual(result.stdout, "ok")
        kwargs = mocked_run.call_args.kwargs
        self.assertEqual(kwargs["encoding"], "utf-8")
        self.assertEqual(kwargs["errors"], "replace")
        self.assertTrue(kwargs["text"])
        self.assertTrue(kwargs["capture_output"])


if __name__ == "__main__":
    unittest.main()
