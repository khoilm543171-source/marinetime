from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "record_assessment.py"
sys.path.insert(0, str(ROOT / "src"))

from marinetime.learning.mastery import (  # noqa: E402
    build_initial_learner_state,
    build_practice_session,
)


def topic_lesson() -> dict:
    return {
        "schema_version": "1.0",
        "artifact_type": "topic_lesson",
        "topic_id": "passage-planning",
        "title": "Passage Planning",
        "stage_lessons": [
            {"stage": "appraisal", "title": "Appraisal"},
            {"stage": "planning", "title": "Planning"},
            {"stage": "execution", "title": "Execution"},
            {"stage": "monitoring", "title": "Monitoring"},
        ],
        "assessment": {
            "retrieval_practice": [
                {"assessment_id": "Q-01", "type": "retrieval", "prompt": "List the four stages."},
                {"assessment_id": "Q-02", "type": "retrieval", "prompt": "Explain appraisal."},
                {"assessment_id": "Q-03", "type": "retrieval", "prompt": "Explain planning."},
                {"assessment_id": "Q-04", "type": "retrieval", "prompt": "Explain execution."},
                {"assessment_id": "Q-05", "type": "retrieval", "prompt": "Explain monitoring."},
                {"assessment_id": "Q-06", "type": "boundary_check", "prompt": "Explain authority boundary."},
            ],
            "oral_exam": {
                "assessment_id": "ORAL-01",
                "question": "How do you make a passage plan?",
                "rubric": [],
            },
        },
    }


class RecordAssessmentCliTests(unittest.TestCase):
    def _prepare(self, root: Path) -> Path:
        topic_root = root / "topics"
        out = topic_root / "passage-planning"
        out.mkdir(parents=True)
        lesson = topic_lesson()
        state = build_initial_learner_state(
            topic_lesson=lesson,
            created_at="2026-09-18T07:00:00+00:00",
        )
        practice = build_practice_session(lesson)
        (out / "learner_state.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (out / "practice_session.json").write_text(
            json.dumps(practice, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return topic_root

    def test_records_retrieval_evidence_and_updates_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            topic_root = self._prepare(root)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--topic-root",
                    str(topic_root),
                    "--topic",
                    "passage-planning",
                    "--assessment-id",
                    "Q-01",
                    "--score",
                    "0.9",
                    "--evidence-type",
                    "retrieval",
                    "--assessed-at",
                    "2026-09-18T08:00:00+00:00",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("ASSESSMENT_RECORD_OK", result.stdout)
            self.assertIn("provider_calls=0", result.stdout)
            self.assertIn(
                "stage=seen->recalled",
                result.stdout,
            )

            state = json.loads(
                (topic_root / "passage-planning" / "learner_state.json").read_text(
                    encoding="utf-8"
                )
            )
            concept = state["concepts"]["passage-planning:framework"]
            self.assertEqual(concept["ownership_stage"], "recalled")
            self.assertEqual(concept["mastery_score"], 0.9)
            self.assertTrue(
                (topic_root / "passage-planning" / "learner_state.md").is_file()
            )

    def test_unknown_assessment_fails_without_mutating_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            topic_root = self._prepare(root)
            state_path = topic_root / "passage-planning" / "learner_state.json"
            before = state_path.read_text(encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--topic-root",
                    str(topic_root),
                    "--assessment-id",
                    "Q-99",
                    "--score",
                    "0.9",
                    "--evidence-type",
                    "retrieval",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("UNKNOWN_ASSESSMENT_ID", result.stderr)
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
