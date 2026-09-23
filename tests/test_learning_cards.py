from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.learning.cards import (
    build_source_learning_card,
    card_to_json,
    render_card_markdown,
    write_card_artifacts,
)


def evidence_pack() -> dict:
    return {
        "schema_version": "1.0",
        "source_id": "RAW-001",
        "provenance_class": "creator_experience",
        "context": {"creator_id": "nguyen-chi-hieu"},
        "transcript_segments": [
            {
                "evidence_id": "SEG-001",
                "start_ms": 1000,
                "end_ms": 5000,
                "text": "The creator explains one learning point from onboard experience.",
            }
        ],
        "ocr_hits": [],
        "frames": [
            {
                "evidence_id": "FRAME-001",
                "timestamp_ms": 0,
                "requested_timestamp_ms": 15000,
                "timestamp_fallback_reason": "NO_FRAME_AT_REQUESTED_TIMESTAMP",
                "artifact_path": "frames/frame_001.png",
            }
        ],
        "preprocess_version": "local_video_v1",
    }


def alu_artifact() -> dict:
    return {
        "schema_version": "1.0",
        "source_id": "RAW-001",
        "model": "test-model",
        "prompt_version": "alu_extraction_v5",
        "usage": {},
        "alus": [
            {
                "alu": {
                    "schema_version": "1.0",
                    "source_id": "RAW-001",
                    "provenance_class": "creator_experience",
                    "verification_status": "unverified",
                    "claim_scope": "minimal",
                    "context_requirement": "minimal",
                    "context": {"creator_id": "nguyen-chi-hieu"},
                    "numeric": None,
                    "relation": None,
                    "alu_id": "ALU-001",
                    "statement": "The creator describes one learning point from onboard experience.",
                    "statement_type": "creator_statement",
                    "support_level": "directly_supported",
                    "rendering_scope": "source_specific",
                    "evidence_refs": ["SEG-001", "FRAME-001"],
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
                    "schema_version": "1.0",
                    "source_id": "RAW-001",
                    "provenance_class": "creator_experience",
                    "verification_status": "unverified",
                    "claim_scope": "minimal",
                    "context_requirement": "minimal",
                    "context": {"creator_id": "nguyen-chi-hieu"},
                    "numeric": None,
                    "relation": None,
                    "alu_id": "ALU-002",
                    "statement": "A withheld unsupported claim.",
                    "statement_type": "unknown",
                    "support_level": "unsupported",
                    "rendering_scope": "source_specific",
                    "evidence_refs": ["SEG-001"],
                    "safety": {"safety_critical": False, "numeric_claim": False},
                },
                "decision": {
                    "accepted_for_reference": True,
                    "accepted_for_education": False,
                    "accepted_for_operational_use": False,
                    "reasons": ["UNSUPPORTED_STATEMENT"],
                },
            },
        ],
    }


class LearningCardTests(unittest.TestCase):
    def test_card_keeps_only_education_approved_items(self) -> None:
        card = build_source_learning_card(
            evidence_pack=evidence_pack(),
            alu_artifact=alu_artifact(),
            title="Example video",
        )
        self.assertEqual(card.source_id, "RAW-001")
        self.assertEqual(card.title, "Example video")
        self.assertEqual(len(card.educational_items), 1)
        self.assertEqual(card.withheld_items, 1)
        self.assertEqual(card.educational_items[0]["alu_id"], "ALU-001")

    def test_card_preserves_honest_frame_fallback_provenance(self) -> None:
        card = build_source_learning_card(
            evidence_pack=evidence_pack(),
            alu_artifact=alu_artifact(),
        )
        anchors = card.evidence_anchors["ALU-001"]
        self.assertTrue(any("fallback=NO_FRAME_AT_REQUESTED_TIMESTAMP" in value for value in anchors))
        self.assertTrue(any("requested 00:15" in value for value in anchors))

    def test_markdown_is_learner_facing_and_warns_about_scope(self) -> None:
        card = build_source_learning_card(
            evidence_pack=evidence_pack(),
            alu_artifact=alu_artifact(),
            title="Example video",
        )
        text = render_card_markdown(card)
        self.assertIn("What this source can teach", text)
        self.assertIn("Active recall", text)
        self.assertIn("Creator experience", text)
        self.assertIn("not operational permission", text)

    def test_json_preview_has_explicit_artifact_type(self) -> None:
        card = build_source_learning_card(
            evidence_pack=evidence_pack(),
            alu_artifact=alu_artifact(),
        )
        payload = card_to_json(card)
        self.assertEqual(payload["artifact_type"], "source_learning_card_preview")
        self.assertEqual(payload["withheld_items"], 1)

    def test_writes_markdown_and_json_atomically(self) -> None:
        card = build_source_learning_card(
            evidence_pack=evidence_pack(),
            alu_artifact=alu_artifact(),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path, md_path = write_card_artifacts(card, output_dir=temp_dir)
            self.assertTrue(json_path.is_file())
            self.assertTrue(md_path.is_file())
            self.assertFalse(Path(temp_dir, "learning_card.json.tmp").exists())
            self.assertFalse(Path(temp_dir, "learning_card.md.tmp").exists())


if __name__ == "__main__":
    unittest.main()
