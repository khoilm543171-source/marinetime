from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from test_alu_extract import base_alu, base_pack

ROOT = Path(__file__).resolve().parents[1]


class CourseIntegrityCLITests(unittest.TestCase):
    def test_offline_course_export_excludes_rejected_claim_with_stale_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "evidence" / "VID-001"
            evidence.mkdir(parents=True)
            pack = base_pack()
            claim = "Passage planning has four stages: appraisal, planning, execution, monitoring."
            pack["transcript_segments"][0]["text"] = claim
            valid = base_alu()
            valid["statement"] = claim
            rejected = copy.deepcopy(valid)
            rejected.update(alu_id="ALU-REJECTED", verification_status="rejected",
                            statement="REJECTED_CLAIM_MUST_NOT_BE_TAUGHT")
            decision = {"accepted_for_reference": True, "accepted_for_education": True,
                        "accepted_for_operational_use": False, "reasons": []}
            artifact = {"schema_version": "1.0", "source_id": "VID-001", "alus": [
                {"alu": valid, "decision": decision}, {"alu": rejected, "decision": decision},
            ]}
            (evidence / "evidence_pack.json").write_text(json.dumps(pack), encoding="utf-8")
            (evidence / "alus.json").write_text(json.dumps(artifact), encoding="utf-8")
            out = root / "course"
            export = root / "course.zip"
            result = subprocess.run(
                [sys.executable, "-S", str(ROOT / "scripts" / "build_full_learning_course.py"),
                 "--evidence-root", str(evidence.parent), "--db", str(root / "empty.sqlite3"),
                 "--output-root", str(out), "--export", str(export)],
                cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30,
                env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["provider_calls"], 0)
            self.assertEqual(manifest["educational_alu_items"], 1)
            self.assertEqual(manifest["withheld_alu_items"], 1)
            lesson = (out / "lessons" / "VID-001" / "LESSON.md").read_text(encoding="utf-8")
            self.assertIn(claim, lesson)
            self.assertIn("4 giai đoạn", lesson)
            self.assertNotIn("REJECTED_CLAIM_MUST_NOT_BE_TAUGHT", lesson)
            with zipfile.ZipFile(export) as archive:
                self.assertIn("manifest.json", archive.namelist())
                self.assertEqual(
                    archive.read("lessons/VID-001/LESSON.md"),
                    (out / "lessons" / "VID-001" / "LESSON.md").read_bytes(),
                )


if __name__ == "__main__":
    unittest.main()
