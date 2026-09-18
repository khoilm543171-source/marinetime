from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.learning.evidence_gate import validate_evidence_progression
from marinetime.learning.mastery import AssessmentResult, MasteryStateError


def state(stage: str) -> dict:
    return {
        "artifact_type": "learner_mastery_state",
        "concepts": {
            "topic:c1": {
                "concept_id": "topic:c1",
                "ownership_stage": stage,
            }
        },
    }


def result(kind: str, *, delay: float = 0.0) -> AssessmentResult:
    return AssessmentResult(
        assessment_id="Q-01",
        concept_ids=("topic:c1",),
        evidence_type=kind,
        score=0.9,
        assessed_at="2026-09-18T08:00:00+00:00",
        delayed_hours=delay,
    )


class EvidenceGateTests(unittest.TestCase):
    def test_retrieval_is_allowed_from_seen(self) -> None:
        validate_evidence_progression(state=state("seen"), result=result("retrieval"))

    def test_oral_requires_recalled(self) -> None:
        with self.assertRaisesRegex(MasteryStateError, "oral_requires_recalled"):
            validate_evidence_progression(state=state("understood"), result=result("oral"))
        validate_evidence_progression(state=state("recalled"), result=result("oral"))

    def test_scenario_requires_explained(self) -> None:
        with self.assertRaisesRegex(MasteryStateError, "scenario_requires_explained"):
            validate_evidence_progression(state=state("recalled"), result=result("scenario"))
        validate_evidence_progression(state=state("explained"), result=result("scenario"))

    def test_delayed_recall_requires_applied(self) -> None:
        with self.assertRaisesRegex(MasteryStateError, "delayed_recall_requires_applied"):
            validate_evidence_progression(
                state=state("explained"),
                result=result("delayed_recall", delay=48),
            )
        validate_evidence_progression(
            state=state("applied"),
            result=result("delayed_recall", delay=48),
        )

    def test_retention_requires_minimum_delay(self) -> None:
        with self.assertRaisesRegex(MasteryStateError, "RETENTION_DELAY_TOO_SHORT"):
            validate_evidence_progression(
                state=state("applied"),
                result=result("delayed_recall", delay=23.9),
            )


if __name__ == "__main__":
    unittest.main()
