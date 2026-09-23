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
                "text": "For appraisal, before drawing anything, collect relevant voyage information.",
            },
            {
                "evidence_id": "SEG-003",
                "start_ms": 43000,
                "end_ms": 64000,
                "text": "During planning, draw the berth-to-berth route, check and validate it.",
            },
            {
                "evidence_id": "SEG-004",
                "start_ms": 64000,
                "end_ms": 78000,
                "text": "During monitoring, check position against the plan and cross-check it.",
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


def _entry(
    alu_id: str,
    statement: str,
    refs: list[str],
    *,
    statement_type: str = "creator_statement",
    safety_critical: bool = False,
) -> dict:
    return {
        "alu": {
            "schema_version": "1.0",
            "source_id": "RAW-PP",
            "provenance_class": "creator_experience",
            "verification_status": "unverified",
            "claim_scope": "minimal",
            "context_requirement": "minimal",
            "context": {"creator_id": "nguyen-chi-hieu"},
            "numeric": None,
            "relation": None,
            "alu_id": alu_id,
            "statement": statement,
            "statement_type": statement_type,
            "support_level": "directly_supported",
            "rendering_scope": "general_educational",
            "evidence_refs": refs,
            "safety": {"safety_critical": safety_critical, "numeric_claim": False},
        },
        "decision": {
            "accepted_for_reference": True,
            "accepted_for_education": True,
            "accepted_for_operational_use": False,
            "reasons": ["PROVENANCE_NOT_OPERATIONAL_AUTHORITY"],
        },
    }


def alu_artifact() -> dict:
    return {
        "schema_version": "1.0",
        "source_id": "RAW-PP",
        "model": "test-model",
        "prompt_version": "alu_extraction_v5",
        "usage": {},
        "alus": [
            _entry(
                "ALU-001",
                "The creator states that passage planning consists of four stages: appraisal, planning, execution, and monitoring.",
                ["SEG-001"],
            ),
            _entry(
                "ALU-002",
                "The creator recommends explaining passage planning as if from real experience rather than reading a checklist in an interview.",
                ["SEG-001"],
                statement_type="recommendation",
            ),
            _entry(
                "ALU-003",
                "The creator describes collecting relevant voyage information before drawing the route during appraisal.",
                ["SEG-002"],
                safety_critical=True,
            ),
            _entry(
                "ALU-004",
                "The creator states that during planning, the officer draws the berth-to-berth route, checks it, validates it, and discusses it.",
                ["SEG-003"],
                safety_critical=True,
            ),
            _entry(
                "ALU-005",
                "The creator reports that during execution, the bridge team follows the approved plan after proper discussion.",
                ["SEG-003"],
                safety_critical=True,
            ),
            _entry(
                "ALU-006",
                "The creator recommends never relying on one position-fixing method only during monitoring.",
                ["SEG-004"],
                statement_type="recommendation",
                safety_critical=True,
            ),
            _entry(
                "ALU-007",
                "The creator states that during monitoring, position should be checked against the plan and cross-checked by radar and visual means.",
                ["SEG-004"],
                safety_critical=True,
            ),
        ],
    }


class LessonBlueprintTests(unittest.TestCase):
    def _card(self):
        return build_source_learning_card(
            evidence_pack=evidence_pack(),
            alu_artifact=alu_artifact(),
            title=(
                "Kể 4 giai đoạn passage planning mà trả lời nhanh quá là TRƯỢT "
                "Nói thế này mới ăn How to answer carefully about the question "
                "do NGUYEN CHI HIEU tạo với bản nhạc original sound"
            ),
        )

    def test_clean_title_removes_platform_boilerplate(self) -> None:
        title = clean_display_title(self._card().title)
        self.assertNotIn("tạo với bản nhạc", title)

    def test_passage_profile_uses_clean_topic_title(self) -> None:
        blueprint = build_lesson_blueprint(self._card())
        self.assertEqual(
            blueprint.display_title,
            "Passage Planning — 4 Stages and Interview Answer",
        )

    def test_learning_objectives_are_measurable_not_alu_repeats(self) -> None:
        blueprint = build_lesson_blueprint(self._card())
        texts = [item.text for item in blueprint.learning_objectives]
        self.assertEqual(len(texts), 3)
        self.assertIn("Nêu đúng thứ tự 4 giai đoạn", texts[0])
        self.assertIn("Giải thích bằng tiếng Việt", texts[1])
        self.assertIn("Trả lời phỏng vấn 60–90 giây", texts[2])
        self.assertFalse(any("The creator states that" in text for text in texts))

    def test_mental_model_is_stage_based(self) -> None:
        blueprint = build_lesson_blueprint(self._card())
        joined = "\n".join(blueprint.mental_model)
        self.assertIn("Appraisal →", joined)
        self.assertIn("Planning →", joined)
        self.assertIn("Execution →", joined)
        self.assertIn("Monitoring →", joined)

    def test_quick_check_is_specific_retrieval_practice(self) -> None:
        blueprint = build_lesson_blueprint(self._card())
        prompts = [item["prompt"] for item in blueprint.quick_check]
        self.assertIn("4 giai đoạn passage planning", prompts[0].lower())
        self.assertTrue(any("Appraisal" in prompt for prompt in prompts))
        self.assertTrue(any("Planning" in prompt for prompt in prompts))
        self.assertTrue(any("Execution" in prompt for prompt in prompts))
        self.assertTrue(any("Monitoring" in prompt for prompt in prompts))

    def test_creator_safety_content_creates_compact_authority_queue(self) -> None:
        blueprint = build_lesson_blueprint(self._card())
        self.assertTrue(blueprint.authoritative_verification_required)
        self.assertEqual(len(blueprint.authority_targets), 7)
        self.assertIn("ALU-007", blueprint.authority_targets)

    def test_preview_is_less_alu_like_and_keeps_evidence_collapsed(self) -> None:
        card = self._card()
        blueprint = build_lesson_blueprint(card)
        text = render_lesson_preview(
            blueprint,
            evidence_anchors=card.evidence_anchors,
        )
        self.assertIn("## Bạn sẽ học gì / What you will learn", text)
        self.assertIn("## Học bài này trong 10–15 phút", text)
        self.assertIn("## Bản đồ ý chính / Mental model", text)
        self.assertIn("## English cần nhớ / Technical vocabulary", text)
        self.assertIn("## Nội dung bài học", text)
        self.assertIn("**English technical point**", text)
        self.assertIn("**Giải thích tiếng Việt**", text)
        self.assertIn("## Oral practice / Luyện nói", text)
        self.assertIn("## Tự kiểm tra / Retrieval practice", text)
        self.assertIn("<summary>Evidence / Nguồn gốc của ý này</summary>", text)
        self.assertIn("**Interview question:** How do you make a passage plan?", text)
        self.assertNotIn("### 1. The creator states that passage planning", text)

    def test_trust_boundary_does_not_repeat_one_warning_per_safety_alu(self) -> None:
        card = self._card()
        blueprint = build_lesson_blueprint(card)
        text = render_lesson_preview(
            blueprint,
            evidence_anchors=card.evidence_anchors,
        )
        self.assertIn("## Lưu ý an toàn — đọc như người học", text)
        self.assertIn("không phải lệnh thao tác trên tàu", text)
        self.assertIn("<summary>Thông tin kiểm chứng kỹ thuật", text)
        self.assertIn("Safety-critical items: 5.", text)
        self.assertNotIn("ALU-003: safety-critical content", text)

    def test_blueprint_json_marks_v11_and_authority_targets(self) -> None:
        payload = blueprint_to_json(build_lesson_blueprint(self._card()))
        self.assertEqual(payload["schema_version"], "1.1")
        self.assertEqual(payload["artifact_type"], "source_lesson_blueprint_preview")
        self.assertTrue(payload["authoritative_verification_required"])
        self.assertIn("ALU-003", payload["authority_targets"])
        self.assertEqual(len(payload["mental_model"]), 4)

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
