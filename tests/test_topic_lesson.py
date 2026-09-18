from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.learning.topic_lesson import (
    TopicLessonError,
    build_topic_lesson,
    render_topic_lesson,
    validate_topic_lesson,
    write_topic_lesson_artifacts,
)


def topic_packet() -> dict:
    claims = []
    raw = [
        ("TC-001", "ALU-003", "The creator describes collecting information before drawing the route during appraisal.", True),
        ("TC-002", "ALU-005", "The creator reports that during execution, the bridge team follows the approved plan.", True),
        ("TC-003", "ALU-007", "The creator states that during monitoring, position should be checked against the plan and cross-checked.", True),
        ("TC-004", "ALU-004", "The creator states that during planning, the officer draws the berth-to-berth route and validates it.", True),
        ("TC-005", "ALU-002", "The creator recommends explaining passage planning rather than reading a checklist in an interview.", False),
        ("TC-006", "ALU-006", "The creator recommends never relying on GPS alone during monitoring.", True),
        ("TC-007", "ALU-001", "The creator states that passage planning consists of four stages: appraisal, planning, execution, and monitoring.", False),
    ]
    for tc, alu, statement, safety in raw:
        claims.append(
            {
                "topic_claim_id": tc,
                "statement": statement,
                "statement_type": "creator_statement",
                "support_level": "directly_supported",
                "safety_critical": safety,
                "numeric_claim": False,
                "occurrences": [{"source_id": "RAW-1", "alu_id": alu}],
                "source_support_count": 1,
            }
        )
    return {
        "schema_version": "1.0",
        "artifact_type": "topic_packet",
        "topic_id": "passage-planning",
        "display_title": "Passage Planning",
        "source_count": 1,
        "source_ids": ["RAW-1"],
        "mental_model": [
            "Appraisal → gather voyage information before drawing the route",
            "Planning → build the berth-to-berth route",
            "Execution → follow the approved plan",
            "Monitoring → check progress and cross-check position",
        ],
        "claims": claims,
    }


def _ref(source_id: str, locator: str, summary: str) -> dict:
    return {
        "authority_source_id": source_id,
        "organization": "Official authority",
        "title": "Official source",
        "source_type": "primary",
        "url": "https://example.invalid",
        "locator": locator,
        "support_summary": summary,
    }


def authority_review() -> dict:
    findings = [
        {
            "source_id": "RAW-1",
            "alu_id": "ALU-001",
            "statement": "The creator states that passage planning consists of four stages: appraisal, planning, execution, and monitoring.",
            "support_status": "direct_support",
            "authority_refs": [
                _ref("IMO-A893-21", "Annex 1.3", "Defines the four-stage voyage-planning framework.")
            ],
            "rationale": "Explicitly supported.",
        },
        {
            "source_id": "RAW-1",
            "alu_id": "ALU-002",
            "statement": "The creator recommends explaining passage planning rather than reading a checklist in an interview.",
            "support_status": "not_applicable",
            "authority_refs": [],
            "rationale": "Interview advice is not a navigational authority claim.",
        },
        {
            "source_id": "RAW-1",
            "alu_id": "ALU-003",
            "statement": "The creator describes collecting information before drawing the route during appraisal.",
            "support_status": "partial_support",
            "authority_refs": [
                _ref("IMO-A893-21", "Annex 2.1–2.2", "Requires consideration of relevant voyage information.")
            ],
            "rationale": "Core appraisal principle supported, exact list remains creator wording.",
        },
        {
            "source_id": "RAW-1",
            "alu_id": "ALU-004",
            "statement": "The creator states that during planning, the officer draws the berth-to-berth route and validates it.",
            "support_status": "partial_support",
            "authority_refs": [
                _ref("IMO-A893-21", "Annex 3.1–3.4", "Requires a detailed berth-to-berth plan and master approval.")
            ],
            "rationale": "Core planning principle supported, exact wording remains creator-specific.",
        },
        {
            "source_id": "RAW-1",
            "alu_id": "ALU-005",
            "statement": "The creator reports that during execution, the bridge team follows the approved plan.",
            "support_status": "partial_support",
            "authority_refs": [
                _ref("IMO-A893-21", "Annex 4.1", "Requires execution in accordance with the finalized plan.")
            ],
            "rationale": "Execution principle supported.",
        },
        {
            "source_id": "RAW-1",
            "alu_id": "ALU-006",
            "statement": "The creator recommends never relying on GPS alone during monitoring.",
            "support_status": "partial_support",
            "authority_refs": [
                _ref("IMO-A893-21", "Annex 3.2.6", "Requires primary and secondary position-fixing options.")
            ],
            "rationale": "Redundancy supported, exact absolute wording is not an official quote.",
        },
        {
            "source_id": "RAW-1",
            "alu_id": "ALU-007",
            "statement": "The creator states that during monitoring, position should be checked against the plan and cross-checked.",
            "support_status": "partial_support",
            "authority_refs": [
                _ref("IMO-A893-21", "Annex 5.1–5.2", "Requires close and continuous monitoring of progress.")
            ],
            "rationale": "Monitoring principle supported.",
        },
    ]
    return {
        "schema_version": "1.0",
        "artifact_type": "authority_review",
        "topic_id": "passage-planning",
        "verification_method": "curated_official_source_rules_v1",
        "findings": findings,
        "counts": {
            "direct_support": 1,
            "partial_support": 5,
            "not_applicable": 1,
            "unresolved": 0,
        },
    }


class TopicLessonTests(unittest.TestCase):
    def test_builds_authority_aware_topic_lesson(self) -> None:
        lesson = build_topic_lesson(
            topic_packet=topic_packet(),
            authority_review=authority_review(),
        )
        payload = lesson.payload
        self.assertEqual(payload["artifact_type"], "topic_lesson")
        self.assertEqual(payload["topic_id"], "passage-planning")
        self.assertEqual(len(payload["stage_lessons"]), 4)
        self.assertEqual(
            [item["stage"] for item in payload["stage_lessons"]],
            ["appraisal", "planning", "execution", "monitoring"],
        )

    def test_partial_support_is_kept_separate_from_official_core(self) -> None:
        lesson = build_topic_lesson(
            topic_packet=topic_packet(),
            authority_review=authority_review(),
        )
        appraisal = lesson.payload["stage_lessons"][0]
        self.assertEqual(appraisal["official_core"][0]["support_status"], "partial_support")
        self.assertTrue(appraisal["creator_layer"])
        self.assertIn("why_separate", appraisal["creator_layer"][0])

    def test_interview_advice_stays_creator_insight(self) -> None:
        lesson = build_topic_lesson(
            topic_packet=topic_packet(),
            authority_review=authority_review(),
        )
        insights = lesson.payload["creator_insights"]
        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0]["support_status"], "not_applicable")
        self.assertIn("interview", insights[0]["source_statement"].lower())

    def test_assessment_includes_boundary_check_and_oral_rubric(self) -> None:
        lesson = build_topic_lesson(
            topic_packet=topic_packet(),
            authority_review=authority_review(),
        )
        assessment = lesson.payload["assessment"]
        ids = [item["assessment_id"] for item in assessment["retrieval_practice"]]
        self.assertIn("Q-06", ids)
        self.assertEqual(assessment["oral_exam"]["assessment_id"], "ORAL-01")
        self.assertGreaterEqual(len(assessment["oral_exam"]["rubric"]), 4)

    def test_qa_passes_and_blocks_operational_permission(self) -> None:
        lesson = build_topic_lesson(
            topic_packet=topic_packet(),
            authority_review=authority_review(),
        )
        report = validate_topic_lesson(lesson)
        self.assertTrue(report["passed"])
        self.assertTrue(
            any(
                item["check_id"] == "NO_OPERATIONAL_PERMISSION" and item["passed"]
                for item in report["checks"]
            )
        )

    def test_markdown_separates_official_and_creator_layers(self) -> None:
        lesson = build_topic_lesson(
            topic_packet=topic_packet(),
            authority_review=authority_review(),
        )
        text = render_topic_lesson(lesson)
        self.assertIn("## Official framework", text)
        self.assertIn("## Learn each stage", text)
        self.assertIn("Creator layer — keep separate", text)
        self.assertIn("## Oral interview practice", text)
        self.assertIn("## Trust boundary", text)

    def test_mismatched_topic_is_rejected(self) -> None:
        review = authority_review()
        review["topic_id"] = "other-topic"
        with self.assertRaisesRegex(TopicLessonError, "TOPIC_AUTHORITY_ID_MISMATCH"):
            build_topic_lesson(
                topic_packet=topic_packet(),
                authority_review=review,
            )

    def test_writes_lesson_and_qa_atomically(self) -> None:
        lesson = build_topic_lesson(
            topic_packet=topic_packet(),
            authority_review=authority_review(),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            lesson_json, lesson_md, qa_json, qa_md = write_topic_lesson_artifacts(
                lesson,
                output_dir=temp_dir,
            )
            for path in (lesson_json, lesson_md, qa_json, qa_md):
                self.assertTrue(path.is_file())
                self.assertFalse(Path(str(path) + ".tmp").exists())


if __name__ == "__main__":
    unittest.main()
