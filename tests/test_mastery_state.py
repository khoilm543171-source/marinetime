from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.learning.mastery import (
    MasteryStateError,
    apply_assessment_result,
    build_initial_learner_state,
    build_practice_session,
    due_concepts,
    normalize_assessment_result,
    render_mastery_state,
    write_json_atomic,
)


def topic_lesson() -> dict:
    return {
        "schema_version": "1.0",
        "artifact_type": "topic_lesson",
        "topic_id": "passage-planning",
        "title": "Passage Planning — Learn, Explain, and Answer in an Interview",
        "source_count": 1,
        "source_ids": ["RAW-1"],
        "stage_lessons": [
            {"stage": "appraisal", "title": "Appraisal"},
            {"stage": "planning", "title": "Planning"},
            {"stage": "execution", "title": "Execution"},
            {"stage": "monitoring", "title": "Monitoring"},
        ],
        "assessment": {
            "retrieval_practice": [
                {"assessment_id": "Q-01", "type": "retrieval", "prompt": "List four stages."},
                {"assessment_id": "Q-02", "type": "retrieval", "prompt": "Explain appraisal."},
                {"assessment_id": "Q-03", "type": "retrieval", "prompt": "Explain planning."},
                {"assessment_id": "Q-04", "type": "retrieval", "prompt": "Explain execution."},
                {"assessment_id": "Q-05", "type": "retrieval", "prompt": "Explain monitoring."},
                {"assessment_id": "Q-06", "type": "boundary_check", "prompt": "Explain authority boundary."},
            ],
            "oral_exam": {
                "assessment_id": "ORAL-01",
                "question": "How do you make a passage plan?",
                "rubric": [
                    {"criterion": "stage_order", "pass_condition": "correct"},
                    {"criterion": "stage_explanation", "pass_condition": "correct"},
                ],
            },
        },
    }


class MasteryStateTests(unittest.TestCase):
    def test_initial_state_marks_all_concepts_seen_only(self) -> None:
        state = build_initial_learner_state(
            topic_lesson=topic_lesson(),
            created_at="2026-09-18T07:00:00+00:00",
        )
        self.assertEqual(len(state["concepts"]), 7)
        self.assertTrue(
            all(item["ownership_stage"] == "seen" for item in state["concepts"].values())
        )
        self.assertEqual(state["topic_mastery_score"], 0.0)

    def test_practice_session_maps_assessments_to_concepts(self) -> None:
        practice = build_practice_session(topic_lesson())
        q1 = next(item for item in practice["retrieval_items"] if item["assessment_id"] == "Q-01")
        q2 = next(item for item in practice["retrieval_items"] if item["assessment_id"] == "Q-02")
        self.assertEqual(q1["concept_ids"], ["passage-planning:framework"])
        self.assertEqual(q2["concept_ids"], ["passage-planning:appraisal"])
        self.assertIn("passage-planning:oral-answer", practice["oral_item"]["concept_ids"])

    def test_high_retrieval_score_moves_concept_to_recalled(self) -> None:
        lesson = topic_lesson()
        state = build_initial_learner_state(
            topic_lesson=lesson,
            created_at="2026-09-18T07:00:00+00:00",
        )
        practice = build_practice_session(lesson)
        result = normalize_assessment_result(
            practice_session=practice,
            assessment_id="Q-01",
            score=0.9,
            evidence_type="retrieval",
            assessed_at="2026-09-18T08:00:00+00:00",
        )
        apply_assessment_result(state=state, result=result)
        concept = state["concepts"]["passage-planning:framework"]
        self.assertEqual(concept["ownership_stage"], "recalled")
        self.assertEqual(concept["evidence_count"], 1)
        self.assertEqual(concept["mastery_score"], 0.9)

    def test_oral_result_moves_linked_concepts_to_explained(self) -> None:
        lesson = topic_lesson()
        state = build_initial_learner_state(
            topic_lesson=lesson,
            created_at="2026-09-18T07:00:00+00:00",
        )
        practice = build_practice_session(lesson)
        result = normalize_assessment_result(
            practice_session=practice,
            assessment_id="ORAL-01",
            score=0.8,
            evidence_type="oral",
            assessed_at="2026-09-18T08:00:00+00:00",
        )
        apply_assessment_result(state=state, result=result)
        self.assertEqual(
            state["concepts"]["passage-planning:oral-answer"]["ownership_stage"],
            "explained",
        )
        self.assertEqual(
            state["concepts"]["passage-planning:planning"]["ownership_stage"],
            "explained",
        )

    def test_delayed_recall_requires_24_hours_for_retained(self) -> None:
        lesson = topic_lesson()
        state = build_initial_learner_state(
            topic_lesson=lesson,
            created_at="2026-09-18T07:00:00+00:00",
        )
        practice = build_practice_session(lesson)

        too_soon = normalize_assessment_result(
            practice_session=practice,
            assessment_id="Q-01",
            score=0.9,
            evidence_type="delayed_recall",
            assessed_at="2026-09-18T12:00:00+00:00",
            delayed_hours=5,
        )
        apply_assessment_result(state=state, result=too_soon)
        self.assertEqual(
            state["concepts"]["passage-planning:framework"]["ownership_stage"],
            "recalled",
        )

        delayed = normalize_assessment_result(
            practice_session=practice,
            assessment_id="Q-01",
            score=0.9,
            evidence_type="delayed_recall",
            assessed_at="2026-09-19T12:00:00+00:00",
            delayed_hours=29,
        )
        apply_assessment_result(state=state, result=delayed)
        self.assertEqual(
            state["concepts"]["passage-planning:framework"]["ownership_stage"],
            "retained",
        )

    def test_low_score_never_downgrades_existing_ownership_stage(self) -> None:
        lesson = topic_lesson()
        state = build_initial_learner_state(
            topic_lesson=lesson,
            created_at="2026-09-18T07:00:00+00:00",
        )
        practice = build_practice_session(lesson)

        strong = normalize_assessment_result(
            practice_session=practice,
            assessment_id="Q-01",
            score=0.95,
            evidence_type="retrieval",
            assessed_at="2026-09-18T08:00:00+00:00",
        )
        apply_assessment_result(state=state, result=strong)

        weak = normalize_assessment_result(
            practice_session=practice,
            assessment_id="Q-01",
            score=0.2,
            evidence_type="retrieval",
            assessed_at="2026-09-18T09:00:00+00:00",
        )
        apply_assessment_result(state=state, result=weak)

        concept = state["concepts"]["passage-planning:framework"]
        self.assertEqual(concept["ownership_stage"], "recalled")
        self.assertEqual(concept["evidence_count"], 2)
        self.assertAlmostEqual(concept["mastery_score"], 0.575)

    def test_due_concepts_prioritize_lower_ownership_and_score(self) -> None:
        state = build_initial_learner_state(
            topic_lesson=topic_lesson(),
            created_at="2026-09-18T07:00:00+00:00",
        )
        due = due_concepts(state, now="2026-09-18T07:00:00+00:00")
        self.assertEqual(len(due), 7)
        self.assertTrue(all(item["ownership_stage"] == "seen" for item in due))

    def test_invalid_score_is_rejected(self) -> None:
        practice = build_practice_session(topic_lesson())
        with self.assertRaisesRegex(MasteryStateError, "SCORE_OUT_OF_RANGE"):
            normalize_assessment_result(
                practice_session=practice,
                assessment_id="Q-01",
                score=1.1,
                evidence_type="retrieval",
            )

    def test_render_explicitly_says_generated_lesson_is_not_mastery(self) -> None:
        state = build_initial_learner_state(
            topic_lesson=topic_lesson(),
            created_at="2026-09-18T07:00:00+00:00",
        )
        text = render_mastery_state(state)
        self.assertIn("Seen → Understood → Recalled → Explained → Applied → Retained", text)
        self.assertIn("generated lesson is not counted as mastery", text)

    def test_atomic_json_write(self) -> None:
        state = build_initial_learner_state(
            topic_lesson=topic_lesson(),
            created_at="2026-09-18T07:00:00+00:00",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_json_atomic(Path(temp_dir) / "learner_state.json", state)
            self.assertTrue(path.is_file())
            self.assertFalse(Path(str(path) + ".tmp").exists())


if __name__ == "__main__":
    unittest.main()
