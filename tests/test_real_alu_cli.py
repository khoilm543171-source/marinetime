from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "extract_alus_from_evidence.py"


class RealALUCLITests(unittest.TestCase):
    def test_invalid_evidence_is_rejected_before_provider_call(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence = root / "evidence.json"
            output = root / "alus.json"
            evidence.write_text(json.dumps({"schema_version": "1.0"}), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--evidence",
                    str(evidence),
                    "--out",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("ALU_REAL_FAILED", result.stderr)
            self.assertNotIn("OPUS_ALU_EXTRACTION_START", result.stdout)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
