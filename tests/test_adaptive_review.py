from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.learning.adaptive_review import build_adaptive_review_plan
from marinetime.learning.mastery import MasteryStateError


def state() -> dict:
    return {
        "artifact_type": "learner_mastery_state",
        "topic_id": "passage-planning",
        "concepts": {
            "passage-planning:framework": {
                "concept_id": "passage-planning:framework",
                "label": "Four-stage framework",
                "ownership_stage": "seen",
                "mastery_score": 0.0,
                "next_review_at": "2026-09-18T07:00:00+00:00",
            },
            "passage-planning:appraisal": {
                "concept_id": "passage-planning:appraisal",
                "label": "Appraisal",
                "ownership_stage": "recalled",
                "mastery_score": 0.9,
                "next_review_at": "2026-09-18T07:00:00+00:00",
            },
            "passage-planning:planning": {
                "concept_id": "passage-planning:planning",
                "label": "Planning",
                "ownership_stage": "understood",
                "mastery_score": 0.6,
                "next_review_at": "2026-09-18T07:00:00+00:00",
            },
            "passage-planning:execution": {
                "concept_id": "passage-planning:execution",
                "label": "Execution",
                "ownership_stage": "retained",
                "mastery_score": 0.95,
                "next_review_at": "2026-10-01T07:00:00+00:00",
            },
        },
    }


def practice() -> dict:
    return {
        "artifact_type": "practice_session",
        "topic_id": "passage-planning",
        "retrieval_items": [
            {
                "assessment_id": "Q-01",
                "type": "retrieval",
                "prompt": "List the four stages.",
                "concept_ids": ["passage-planning:framework"],
            },
            {
                "assessment_id": "Q-02",
                "type": "retrieval",
                "prompt": "Explain appraisal.",
                "concept_ids": ["passage-planning:appraisal"],
            },
            {
                "assessment_id": "Q-03",
                "type": "retrieval",
                "prompt": "Explain planning.",
                "concept_ids": ["passage-planning:planning"],
            },
        ],
        "oral_item": {
            "assessment_id": "ORAL-01",
            "type": "oral_exam",
            "prompt": "How do you make a passage plan?",
            "concept_ids": [
                "passage-planning:framework",
                "passage-planning:appraisal",
                "passage-planning:planning",
            ],
        },
    }


class AdaptiveReviewTests(unittest.TestCase):
    def test_prioritizes_due_low_ownership_concepts(self) -> None:
        plan = build_adaptive_review_plan(
            state=state(),
            practice_session=practice(),
            now="2026-09-18T08:00:00+00:00",
            max_items=2,
        )
        self.assertEqual(plan["selected_count"], 2)
        self.assertEqual(plan["items"][0]["concept_id"], "passage-planning:framework")
        self.assertEqual(plan["items"][1]["concept_id"], "passage-planning:planning")

    def test_seen_and_understood_use_retrieval(self) -> None:
        plan = build_adaptive_review_plan(
            state=state(),
            practice_session=practice(),
            now="2026-09-18T08:00:00+00:00",
            max_items=2,
        )
        self.assertTrue(
            all(item["recommended_evidence_type"] == "retrieval" for item in plan["items"])
        )

    def test_recalled_prefers_oral_when_reached(self) -> None:
        s = state()
        s["concepts"]["passage-planning:framework"]["next_review_at"] = "2026-10-01T00:00:00+00:00"
        s["concepts"]["passage-planning:planning"]["next_review_at"] = "2026-10-01T00:00:00+00:00"
        plan = build_adaptive_review_plan(
            state=s,
            practice_session=practice(),
            now="2026-09-18T08:00:00+00:00",
            max_items=1,
        )
        self.assertEqual(plan["items"][0]["concept_id"], "passage-planning:appraisal")
        self.assertEqual(plan["items"][0]["assessment_id"], "ORAL-01")
        self.assertEqual(plan["items"][0]["recommended_evidence_type"], "oral")

    def test_future_concepts_are_not_selected(self) -> None:
        plan = build_adaptive_review_plan(
            state=state(),
            practice_session=practice(),
            now="2026-09-18T08:00:00+00:00",
            max_items=10,
        )
        ids = {item["concept_id"] for item in plan["items"]}
        self.assertNotIn("passage-planning:execution", ids)

    def test_does_not_invent_assessment_when_grounded_item_missing(self) -> None:
        s = state()
        s["concepts"]["passage-planning:monitoring"] = {
            "concept_id": "passage-planning:monitoring",
            "label": "Monitoring",
            "ownership_stage": "seen",
            "mastery_score": 0.0,
            "next_review_at": "2026-09-18T07:00:00+00:00",
        }
        plan = build_adaptive_review_plan(
            state=s,
            practice_session=practice(),
            now="2026-09-18T08:00:00+00:00",
            max_items=10,
        )
        self.assertTrue(
            any(
                item["concept_id"] == "passage-planning:monitoring"
                and item["reason"] == "NO_COMPATIBLE_GROUNDED_ASSESSMENT"
                for item in plan["skipped"]
            )
        )

    def test_topic_mismatch_is_rejected(self) -> None:
        p = practice()
        p["topic_id"] = "other-topic"
        with self.assertRaisesRegex(MasteryStateError, "STATE_PRACTICE_TOPIC_MISMATCH"):
            build_adaptive_review_plan(
                state=state(),
                practice_session=p,
                now="2026-09-18T08:00:00+00:00",
            )

    def test_invalid_max_items_is_rejected(self) -> None:
        with self.assertRaisesRegex(MasteryStateError, "INVALID_MAX_ITEMS"):
            build_adaptive_review_plan(
                state=state(),
                practice_session=practice(),
                now="2026-09-18T08:00:00+00:00",
                max_items=0,
            )


if __name__ == "__main__":
    unittest.main()
