from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_local_artifacts.py"


def _write_source(
    root: Path,
    source_id: str,
    *,
    with_alu: bool,
    usage_tokens: int = 10,
) -> None:
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
                "text": "grounded text",
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
            "usage": {
                "input_tokens": usage_tokens,
                "output_tokens": 0,
            },
            "alus": [
                {
                    "alu": {
                        "alu_id": "ALU-001",
                        "source_id": source_id,
                        "statement": "Grounded claim.",
                        "evidence_refs": ["SEG-001"],
                        "safety": {
                            "safety_critical": False,
                            "numeric_claim": False,
                        },
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


class LocalArtifactAuditTests(unittest.TestCase):
    def test_audit_reports_real_counts_and_missing_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_source(root, "RAW-001", with_alu=True, usage_tokens=12)
            _write_source(root, "RAW-002", with_alu=False)

            result = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    str(SCRIPT),
                    "--evidence-root",
                    str(root),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("evidence_files=2", result.stdout)
            self.assertIn("valid_evidence=2", result.stdout)
            self.assertIn("alu_files=1", result.stdout)
            self.assertIn("valid_alus=1", result.stdout)
            self.assertIn("missing_alus=1", result.stdout)
            self.assertIn("missing=RAW-002", result.stdout)
            self.assertIn("provider_backed_artifacts=1", result.stdout)
            self.assertIn("audit_passed=true", result.stdout)

    def test_audit_fails_for_invalid_alu_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_source(root, "RAW-001", with_alu=True)
            alu_path = root / "RAW-001" / "alus.json"
            artifact = json.loads(alu_path.read_text(encoding="utf-8"))
            artifact["alus"][0]["alu"]["evidence_refs"] = ["SEG-NOT-REAL"]
            alu_path.write_text(json.dumps(artifact), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    str(SCRIPT),
                    "--evidence-root",
                    str(root),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("invalid_alus=1", result.stdout)
            self.assertIn("UNKNOWN_EVIDENCE_REFS", result.stdout)
            self.assertIn("audit_passed=false", result.stdout)


if __name__ == "__main__":
    unittest.main()
