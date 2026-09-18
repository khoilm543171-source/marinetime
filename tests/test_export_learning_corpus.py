from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "export_learning_corpus.py"


def _write_source(root: Path, source_id: str, *, with_alu: bool) -> None:
    folder = root / source_id
    folder.mkdir(parents=True, exist_ok=True)
    evidence = {
        "schema_version": "1.0",
        "source_id": source_id,
        "provenance_class": "creator_experience",
        "context": {},
        "transcript_segments": [
            {
                "evidence_id": "SEG-001",
                "start_ms": 0,
                "end_ms": 1000,
                "text": "example",
            }
        ],
        "ocr_hits": [],
        "frames": [],
        "preprocess_version": "test",
    }
    (folder / "evidence_pack.json").write_text(
        json.dumps(evidence),
        encoding="utf-8",
    )
    if with_alu:
        artifact = {
            "schema_version": "1.0",
            "source_id": source_id,
            "model": "test-model",
            "prompt_version": "test-prompt",
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "alus": [
                {
                    "alu": {
                        "alu_id": "ALU-001",
                        "source_id": source_id,
                        "evidence_refs": ["SEG-001"],
                        "statement": "claim",
                    },
                    "decision": {
                        "accepted_for_reference": True,
                        "accepted_for_education": True,
                        "accepted_for_operational_use": False,
                        "reasons": [],
                    },
                }
            ],
        }
        (folder / "alus.json").write_text(
            json.dumps(artifact),
            encoding="utf-8",
        )


class ExportLearningCorpusTests(unittest.TestCase):
    def test_exports_json_only_with_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence_root = root / "evidence"
            out = root / "learning.zip"
            _write_source(evidence_root, "RAW-001", with_alu=True)
            _write_source(evidence_root, "RAW-002", with_alu=False)

            result = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    str(SCRIPT),
                    "--evidence-root",
                    str(evidence_root),
                    "--out",
                    str(out),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("evidence_packs=2", result.stdout)
            self.assertIn("alus_completed=1", result.stdout)
            self.assertIn("missing_alus=1", result.stdout)
            self.assertIn("total_alu_items=1", result.stdout)

            with zipfile.ZipFile(out) as archive:
                names = set(archive.namelist())
                self.assertIn("manifest.json", names)
                self.assertIn("evidence/RAW-001/evidence_pack.json", names)
                self.assertIn("evidence/RAW-001/alus.json", names)
                self.assertIn("evidence/RAW-002/evidence_pack.json", names)
                self.assertNotIn("evidence/RAW-002/alus.json", names)
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(manifest["evidence_packs"], 2)
                self.assertEqual(manifest["alus_completed"], 1)
                self.assertEqual(manifest["missing_alus"], ["RAW-002"])
                self.assertEqual(manifest["total_alu_items"], 1)

    def test_rejects_source_id_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence_root = root / "evidence"
            out = root / "learning.zip"
            _write_source(evidence_root, "RAW-001", with_alu=False)
            path = evidence_root / "RAW-001" / "evidence_pack.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["source_id"] = "RAW-WRONG"
            path.write_text(json.dumps(payload), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    str(SCRIPT),
                    "--evidence-root",
                    str(evidence_root),
                    "--out",
                    str(out),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("EVIDENCE_SOURCE_ID_MISMATCH", result.stderr)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
