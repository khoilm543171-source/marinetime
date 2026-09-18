from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.learning.blueprint import LearningObjective, LessonBlueprint
from marinetime.learning.course import (
    build_learning_course,
    classify_course_track,
    course_to_json,
    render_course_markdown,
)


def _blueprint(
    source_id: str,
    title: str,
    statement: str,
    *,
    safety: bool = False,
) -> LessonBlueprint:
    return LessonBlueprint(
        schema_version="1.1",
        source_id=source_id,
        original_title=title,
        display_title=title,
        provenance_class="creator_experience",
        learning_objectives=(
            LearningObjective("LO-01", "Explain the idea.", ("ALU-001",)),
        ),
        key_items=(
            {
                "alu_id": "ALU-001",
                "statement": statement,
                "statement_type": "creator_statement",
                "support_level": "directly_supported",
                "safety_critical": safety,
                "numeric_claim": False,
            },
        ),
        mental_model=("One idea",),
        quick_check=(
            {
                "question_id": "Q-01",
                "prompt": "Explain it.",
                "answer_anchor": statement,
                "alu_id": "ALU-001",
            },
        ),
        oral_exam_prompt="Explain it aloud.",
        authority_targets=("ALU-001",),
        authoritative_verification_required=True,
        warnings=(),
    )


class LearningCourseTests(unittest.TestCase):
    def test_classifies_engine_and_navigation_tracks(self) -> None:
        engine = _blueprint(
            "RAW-ENGINE",
            "Purifier basics",
            "The purifier separates contaminants from fuel oil.",
        )
        nav = _blueprint(
            "RAW-NAV",
            "Passage Planning",
            "Passage planning includes appraisal, planning, execution and monitoring.",
        )

        self.assertEqual(classify_course_track(engine)[0], "engine-machinery")
        self.assertEqual(classify_course_track(nav)[0], "navigation")

    def test_builds_course_without_hiding_deferred_sources(self) -> None:
        blueprint = _blueprint(
            "RAW-001",
            "Engine Room Pump",
            "A pump moves liquid through the system.",
            safety=True,
        )
        course = build_learning_course(
            blueprints=[blueprint],
            source_cards_built=2,
            educational_alu_items=5,
            withheld_alu_items=1,
            sources_without_lesson=["RAW-002"],
            missing_alu_sources=["RAW-003"],
        )
        payload = course_to_json(course)
        markdown = render_course_markdown(course)

        self.assertEqual(payload["source_cards_built"], 2)
        self.assertEqual(payload["source_lessons_built"], 1)
        self.assertEqual(payload["educational_alu_items"], 5)
        self.assertEqual(payload["sources_without_lesson"], ["RAW-002"])
        self.assertEqual(payload["missing_alu_sources"], ["RAW-003"])
        self.assertIn("RAW-003", markdown)
        self.assertIn("chưa có ALU, nên chưa tạo lesson", markdown)
        self.assertIn("## Bắt đầu ở đây", markdown)
        self.assertIn("Tiếng Việt dùng để giải thích", markdown)
        self.assertIn("Seen → Understood → Recalled → Explained → Applied → Retained", markdown)
        self.assertIn("LESSON.md", payload["tracks"][0]["lessons"][0]["lesson_path"])


if __name__ == "__main__":
    unittest.main()
