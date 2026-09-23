from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.pipeline.auto_alu import (  # noqa: E402
    AutoALUCandidate,
    discover_auto_alu_candidates,
    is_global_budget_pause,
    run_auto_alu_threshold,
    select_threshold_batch,
)
from test_alu_extract import base_alu


def _write_evidence(root: Path, source_id: str) -> Path:
    folder = root / source_id
    folder.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "source_id": source_id,
        "provenance_class": "creator_experience",
        "context": {},
        "transcript_segments": [
            {
                "evidence_id": "SEG-001",
                "start_ms": 0,
                "end_ms": 1000,
                "text": "test evidence",
            }
        ],
        "ocr_hits": [],
        "frames": [],
        "preprocess_version": "test_v1",
    }
    path = folder / "evidence_pack.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class AutoALUThresholdTests(unittest.TestCase):
    def test_selects_only_complete_threshold_groups(self) -> None:
        candidates = [
            AutoALUCandidate(
                source_id=f"VID-{index:03d}",
                evidence_path=Path(f"VID-{index:03d}/evidence_pack.json"),
                output_path=Path(f"VID-{index:03d}/alus.json"),
                created_order=(float(index), f"VID-{index:03d}"),
            )
            for index in range(40)
        ]

        self.assertEqual(len(select_threshold_batch(candidates[:19], threshold=20)), 0)
        self.assertEqual(len(select_threshold_batch(candidates[:20], threshold=20)), 20)
        self.assertEqual(len(select_threshold_batch(candidates[:39], threshold=20)), 20)
        self.assertEqual(len(select_threshold_batch(candidates[:40], threshold=20)), 40)

    def test_discovery_skips_sources_with_existing_alu_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_evidence(root, "VID-001")
            _write_evidence(root, "VID-002")
            (root / "VID-001" / "alus.json").write_text(
                json.dumps({"schema_version": "1.0", "source_id": "VID-001", "alus": [{
                    "alu": base_alu(),
                    "decision": {"accepted_for_reference": True, "accepted_for_education": True,
                                 "accepted_for_operational_use": False},
                }]}),
                encoding="utf-8",
            )

            candidates = discover_auto_alu_candidates(root)

            self.assertEqual([item.source_id for item in candidates], ["VID-002"])

    def test_placeholder_artifact_does_not_mark_a_source_completed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_evidence(root, "VID-001")
            (root / "VID-001" / "alus.json").write_text(
                json.dumps({"source_id": "VID-001", "alus": [{"alu": {}}]}), encoding="utf-8"
            )
            self.assertEqual([item.source_id for item in discover_auto_alu_candidates(root)], ["VID-001"])

    def test_below_threshold_never_requires_provider_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "evidence"
            for index in range(4):
                _write_evidence(evidence, f"VID-{index:03d}")

            result = run_auto_alu_threshold(
                evidence_root=evidence,
                repo_root=ROOT,
                usage_log_path=root / "token_ledger.jsonl",
                threshold=20,
            )

            self.assertFalse(result.triggered)
            self.assertEqual(result.eligible, 4)
            self.assertEqual(result.selected, 0)
            self.assertEqual(result.attempted, 0)
            self.assertEqual(result.waiting_after, 4)

    def test_threshold_must_be_positive(self) -> None:
        with self.assertRaisesRegex(ValueError, "AUTO_ALU_THRESHOLD_MUST_BE_POSITIVE"):
            select_threshold_batch([], threshold=0)

    def test_candidate_input_limit_does_not_count_as_global_pause(self) -> None:
        self.assertFalse(is_global_budget_pause("MAX_INPUT_TOKENS_PER_CALL"))
        self.assertFalse(is_global_budget_pause("MAX_TOKENS_PER_VIDEO"))
        self.assertTrue(is_global_budget_pause("MARINETIME_CLOSEOUT_MODE"))
        self.assertTrue(is_global_budget_pause("MAX_DAILY_TOKENS"))
        self.assertTrue(is_global_budget_pause("USAGE_LEDGER_INVALID_LINE:2"))
        self.assertTrue(is_global_budget_pause("USAGE_LEDGER_LOCKED"))
        self.assertFalse(is_global_budget_pause("MAX_LLM_CALLS_PER_VIDEO"))


if __name__ == "__main__":
    unittest.main()
