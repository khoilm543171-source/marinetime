from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_learning_web import build_payload, write_bundle  # noqa: E402


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class LearningWebTests(unittest.TestCase):
    def _course_fixture(self, root: Path) -> None:
        _write(
            root / "course" / "course_catalog.json",
            {
                "schema_version": "2.0",
                "artifact_type": "learner_course_catalog",
                "course_id": "test-course",
                "title": "Test Course",
                "source_lessons_built": 1,
                "educational_alu_items": 1,
                "withheld_alu_items": 0,
                "missing_alu_sources": [],
                "tracks": [
                    {
                        "track_id": "engine-machinery",
                        "title": "Engine Room",
                        "lesson_count": 1,
                        "lessons": [
                            {
                                "source_id": "RAW-001",
                                "display_title": "Centrifugal pump basics",
                                "safety_critical_items": 0,
                                "numeric_items": 0,
                            }
                        ],
                        "modules": [
                            {
                                "module_id": "pumps-piping",
                                "title": "Pumps & Piping",
                                "description": "Pump foundations",
                                "lesson_count": 1,
                                "lessons": [{"source_id": "RAW-001"}],
                            }
                        ],
                    }
                ],
            },
        )
        _write(
            root / "lessons" / "RAW-001" / "lesson_blueprint.json",
            {
                "source_id": "RAW-001",
                "display_title": "Centrifugal pump basics",
                "original_title": "Pump video",
                "provenance_class": "creator_experience",
                "learning_objectives": [
                    {"objective_id": "LO-01", "text": "Explain the pump idea.", "alu_ids": ["ALU-001"]}
                ],
                "mental_model": ["Pump moves liquid through the system."],
                "key_items": [
                    {
                        "alu_id": "ALU-001",
                        "statement": "The creator states that this pump moves cooling water.",
                        "support_level": "directly_supported",
                        "safety_critical": False,
                        "numeric_claim": False,
                    }
                ],
                "quick_check": [
                    {
                        "question_id": "Q-01",
                        "prompt": "What does the pump move?",
                        "answer_anchor": "Cooling water.",
                        "alu_id": "ALU-001",
                    }
                ],
                "oral_exam_prompt": "Explain the pump in 60 seconds.",
                "authority_targets": ["ALU-001"],
                "authoritative_verification_required": True,
                "warnings": ["Creator experience only."],
            },
        )
        _write(
            root / "source_cards" / "RAW-001" / "learning_card.json",
            {
                "source_id": "RAW-001",
                "withheld_items": 0,
                "evidence_anchors": {
                    "ALU-001": ["SEG-001 · transcript 00:01–00:04 · cooling-water pump"]
                },
            },
        )

    def test_payload_combines_course_blueprint_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._course_fixture(root)
            payload = build_payload(root)

        session = payload["sessions"]["RAW-001"]
        self.assertEqual(session["module_id"], "pumps-piping")
        self.assertEqual(session["key_items"][0]["evidence"][0].split(" · ")[0], "SEG-001")
        self.assertIn("pump", session["key_items"][0]["explanation_vi"].lower())
        self.assertEqual(payload["tracks"][0]["lesson_count"], 1)

    def test_bundle_writes_static_assets_and_course_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            course_root = temp / "course-root"
            output_root = temp / "web-out"
            self._course_fixture(course_root)

            data_path = write_bundle(
                course_root=course_root,
                output_root=output_root,
                template_root=ROOT / "web" / "learning",
            )

            self.assertTrue((output_root / "index.html").is_file())
            self.assertTrue((output_root / "app.js").is_file())
            self.assertTrue((output_root / "styles.css").is_file())
            self.assertTrue(data_path.is_file())
            payload = json.loads(data_path.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["sessions"]), 1)


if __name__ == "__main__":
    unittest.main()
