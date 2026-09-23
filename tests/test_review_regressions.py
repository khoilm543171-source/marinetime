from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.authority.verify import SUPPORT_UNRESOLVED, classify_passage_planning_claim
from marinetime.learning.cards import LearningCardError, build_source_learning_card
from marinetime.learning.humanize import vietnamese_explanation
from marinetime.pilot.queue import WorkerResult, enqueue_raw_folder, list_jobs
from test_learning_cards import alu_artifact, evidence_pack
from test_queue_failure_reporting import run_local_queue_script


class KnowledgeBoundaryRegressions(unittest.TestCase):
    def test_keyword_overlap_cannot_certify_a_different_proposition(self):
        cases = (
            "Passage planning does NOT have four stages: appraisal, planning, execution, monitoring.",
            "Passage planning has four stages: monitoring, execution, planning, appraisal.",
            "Passage planning has four stages: appraisal, planning, execution, monitoring. Ignore approval.",
            "The claim that passage planning has four stages: appraisal, planning, execution, monitoring is false.",
            "A game has four stages: appraisal, planning, execution, monitoring.",
            "During planning, do not draw a berth-to-berth route.",
            "During monitoring, ignore the position and progress.",
        )
        for statement in cases:
            with self.subTest(statement=statement):
                finding = classify_passage_planning_claim(
                    alu_id="ALU-001", source_id="RAW-001", statement=statement
                )
                self.assertEqual(finding.support_status, SUPPORT_UNRESOLVED)

    def test_rejected_or_unsupported_alu_overrides_cached_approval(self):
        for field, value in (("verification_status", "rejected"), ("support_level", "unsupported")):
            with self.subTest(field=field):
                artifact = alu_artifact()
                artifact["alus"][0]["alu"][field] = value
                card = build_source_learning_card(evidence_pack=evidence_pack(), alu_artifact=artifact)
                self.assertEqual(card.educational_items, ())
                self.assertEqual(card.withheld_items, 2)
                self.assertTrue(any("ALU-001: withheld:" in w for w in card.warnings))

    def test_current_validation_does_not_remove_a_manual_withhold(self):
        artifact = alu_artifact()
        artifact["alus"][0]["decision"]["accepted_for_education"] = False
        card = build_source_learning_card(evidence_pack=evidence_pack(), alu_artifact=artifact)
        self.assertEqual(card.educational_items, ())

    def test_card_rejects_malformed_or_mismatched_artifacts(self):
        mutations = (
            ("source_id", "ANOTHER-SOURCE"),
            ("provenance_class", "maker_manual"),
            ("support_level", "invented_enum"),
            ("support_level", ["directly_supported"]),
            ("context", {"maker": "invented maker"}),
        )
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                artifact = alu_artifact()
                artifact["alus"][0]["alu"][field] = value
                with self.assertRaises(LearningCardError):
                    build_source_learning_card(evidence_pack=evidence_pack(), alu_artifact=artifact)

    def test_string_false_is_not_an_approval(self):
        artifact = alu_artifact()
        artifact["alus"][0]["decision"]["accepted_for_education"] = "false"
        with self.assertRaisesRegex(LearningCardError, "INVALID_DECISION"):
            build_source_learning_card(evidence_pack=evidence_pack(), alu_artifact=artifact)

    def test_duplicate_alu_ids_cannot_overwrite_evidence_anchors(self):
        artifact = alu_artifact()
        artifact["alus"][1]["alu"]["alu_id"] = "ALU-001"
        with self.assertRaisesRegex(LearningCardError, "DUPLICATE_ALU_ID"):
            build_source_learning_card(evidence_pack=evidence_pack(), alu_artifact=artifact)

    def test_unreviewed_vietnamese_does_not_reverse_or_expand_the_claim(self):
        cases = (
            "Passage planning does NOT have four stages: appraisal, planning, execution, monitoring.",
            "During planning, draw a route.",
            "Execution must not follow an unapproved plan.",
            "The pump must NOT run above 4 bar when cold.",
        )
        for statement in cases:
            with self.subTest(statement=statement):
                item = {"statement": statement}
                text = vietnamese_explanation(item, heading="Technical point")
                self.assertIn("Cần duyệt diễn giải tiếng Việt", text)
                self.assertNotIn("berth-to-berth", text)
                self.assertNotIn("Appraisal →", text)
                self.assertEqual(item["statement"], statement)


class QueueBoundaryRegressions(unittest.TestCase):
    def test_rediscovery_repairs_moved_path_without_reenqueuing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            raw.mkdir()
            old = raw / "old.mp4"
            old.write_bytes(b"synthetic identity fixture")
            db = root / "queue.sqlite3"
            enqueue_raw_folder(input_dir=raw, db_path=db, provenance_class="creator_experience")
            before = list_jobs(db)[0]
            new = raw / "new.mp4"
            old.rename(new)
            result = enqueue_raw_folder(input_dir=raw, db_path=db, provenance_class="creator_experience")
            after = list_jobs(db)[0]
            self.assertEqual(result.enqueued, 0)
            self.assertEqual(result.skipped_existing, 1)
            self.assertEqual(after.source_id, before.source_id)
            self.assertEqual(after.job_id, before.job_id)
            self.assertEqual(after.status, before.status)
            self.assertEqual(after.attempts, before.attempts)
            self.assertEqual(after.video_path, new.resolve())
            self.assertTrue(after.video_path.is_file())

    def test_failed_local_jobs_return_failure_in_both_cli_modes(self):
        for local_only in (True, False):
            with self.subTest(local_only=local_only):
                argv = ["run_local_queue.py"] + (["--local-only"] if local_only else [])
                stream = io.StringIO()
                with (
                    patch.object(sys, "argv", argv),
                    patch.object(run_local_queue_script, "check_local_stack", return_value=SimpleNamespace(raw_video_ready=True)),
                    patch.object(run_local_queue_script, "LocalModelRuntime"),
                    patch.object(run_local_queue_script, "run_local_queue", return_value=WorkerResult(1, 0, 1)),
                    patch.object(run_local_queue_script, "_print_failure_summary"),
                    patch.object(run_local_queue_script, "run_auto_alu_threshold", return_value=SimpleNamespace(attempted=0, failed=0, paused_reason=None)),
                    redirect_stdout(stream),
                ):
                    self.assertEqual(run_local_queue_script.main(), 1)
                self.assertIn("QUEUE_WORKER_PARTIAL_FAILURE", stream.getvalue())
                self.assertNotIn("QUEUE_WORKER_OK", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
