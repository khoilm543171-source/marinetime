from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.learning.blueprint import (
    blueprint_to_json,
    build_lesson_blueprint,
    clean_display_title,
    render_lesson_preview,
    write_lesson_preview,
)
from marinetime.learning.cards import build_source_learning_card


def evidence_pack() -> dict:
    return {
        "schema_version": "1.0",
        "source_id": "RAW-PP",
        "provenance_class": "creator_experience",
        "context": {"creator_id": "nguyen-chi-hieu"},
        "transcript_segments": [
            {
                "evidence_id": "SEG-001",
                "start_ms": 0,
                "end_ms": 24000,
                "text": "Everyone says appraisal, planning, execution, monitoring.",
            },
            {
                "evidence_id": "SEG-002",
                "start_ms": 24000,
                "end_ms": 43000,
                "text": "Before drawing anything, collect relevant information.",
            },
        ],
        "ocr_hits": [],
        "frames": [
            {
                "evidence_id": "FRAME-001",
                "timestamp_ms": 10000,
                "artifact_path": "frames/frame_001.jpg",
            }
        ],
        "preprocess_version": "local_video_v1",
    }


def alu_artifact() -> dict:
    return {
        "schema_version": "1.0",
        "source_id": "RAW-PP",
        "model": "test-model",
        "prompt_version": "alu_extraction_v5",
        "usage": {},
        "alus": [
            {
                "alu": {
                    "alu_id": "ALU-001",
                    "statement": (
                        "The creator states that passage planning consists of four stages: "
                        "appraisal, planning, execution, and monitoring."
                    ),
                    "statement_type": "creator_statement",
                    "support_level": "directly_supported",
                    "rendering_scope": "general_educational",
                    "evidence_refs": ["SEG-001"],
                    "safety": {"safety_critical": False, "numeric_claim": False},
                },
                "decision": {
                    "accepted_for_reference": True,
                    "accepted_for_education": True,
                    "accepted_for_operational_use": False,
                    "reasons": ["PROVENANCE_NOT_OPERATIONAL_AUTHORITY"],
                },
            },
            {
                "alu": {
                    "alu_id": "ALU-002",
                    "statement": (
                        "The creator recommends collecting relevant voyage information "
                        "before drawing the route."
                    ),
                    "statement_type": "recommendation",
                    "support_level": "directly_supported",
                    "rendering_scope": "general_educational",
                    "evidence_refs": ["SEG-002"],
                    "safety": {"safety_critical": True, "numeric_claim": False},
                },
                "decision": {
                    "accepted_for_reference": True,
                    "accepted_for_education": True,
                    "accepted_for_operational_use": False,
                    "reasons": ["PROVENANCE_NOT_OPERATIONAL_AUTHORITY"],
                },
            },
        ],
    }


class LessonBlueprintTests(unittest.TestCase):
    def _card(self):
        return build_source_learning_card(
            evidence_pack=evidence_pack(),
            alu_artifact=alu_artifact(),
            title=(
                "Kể 4 giai đoạn passage planning mà trả lời nhanh quá là TRƯỢT "
                "do NGUYEN CHI HIEU tạo với bản nhạc original sound"
            ),
        )

    def test_clean_title_removes_platform_boilerplate(self) -> None:
        title = clean_display_title(self._card().title)
        self.assertEqual(
            title,
            "Kể 4 giai đoạn passage planning mà trả lời nhanh quá là TRƯỢT",
        )

    def test_blueprint_preserves_alu_grounding(self) -> None:
        blueprint = build_lesson_blueprint(self._card())
        self.assertEqual(blueprint.source_id, "RAW-PP")
        self.assertEqual(len(blueprint.learning_objectives), 2)
        self.assertEqual(blueprint.learning_objectives[0].alu_ids, ("ALU-001",))
        self.assertEqual(blueprint.quick_check[1]["alu_id"], "ALU-002")

    def test_creator_safety_content_requires_authoritative_verification(self) -> None:
        blueprint = build_lesson_blueprint(self._card())
        self.assertTrue(blueprint.authoritative_verification_required)

    def test_preview_hides_evidence_behind_details(self) -> None:
        card = self._card()
        blueprint = build_lesson_blueprint(card)
        text = render_lesson_preview(
            blueprint,
            evidence_anchors=card.evidence_anchors,
        )
        self.assertIn("## Learning goal", text)
        self.assertIn("## Big picture", text)
        self.assertIn("## Oral interview practice", text)
        self.assertIn("<summary>Show evidence</summary>", text)
        self.assertIn("SEG-001", text)

    def test_blueprint_json_marks_preview_scope(self) -> None:
        payload = blueprint_to_json(build_lesson_blueprint(self._card()))
        self.assertEqual(payload["artifact_type"], "source_lesson_blueprint_preview")
        self.assertTrue(payload["authoritative_verification_required"])

    def test_writes_preview_artifacts_atomically(self) -> None:
        card = self._card()
        blueprint = build_lesson_blueprint(card)
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path, md_path = write_lesson_preview(
                blueprint,
                evidence_anchors=card.evidence_anchors,
                output_dir=temp_dir,
            )
            self.assertTrue(json_path.is_file())
            self.assertTrue(md_path.is_file())
            self.assertFalse(Path(temp_dir, "lesson_blueprint.json.tmp").exists())
            self.assertFalse(Path(temp_dir, "lesson_preview.md.tmp").exists())


if __name__ == "__main__":
    unittest.main()
