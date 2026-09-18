from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.learning.topic_packet import (
    build_topic_packet,
    classify_blueprint_topic,
    render_topic_packet,
    topic_packet_to_json,
    write_topic_packet,
)


def blueprint(source_id: str, duplicate_stage_claim: bool = False) -> dict:
    items = [
        {
            "alu_id": "ALU-001",
            "statement": (
                "The creator states that passage planning consists of four stages: "
                "appraisal, planning, execution, and monitoring."
            ),
            "statement_type": "creator_statement",
            "support_level": "directly_supported",
            "safety_critical": False,
            "numeric_claim": False,
        },
        {
            "alu_id": "ALU-002",
            "statement": (
                "The creator describes collecting voyage information before drawing "
                "the route during appraisal."
            ),
            "statement_type": "creator_statement",
            "support_level": "directly_supported",
            "safety_critical": True,
            "numeric_claim": False,
        },
    ]
    if duplicate_stage_claim:
        items[0]["statement"] = (
            "The creator reports that passage planning consists of four stages: "
            "appraisal, planning, execution, and monitoring."
        )
    return {
        "schema_version": "1.1",
        "artifact_type": "source_lesson_blueprint_preview",
        "source_id": source_id,
        "display_title": "Passage Planning — 4 Stages and Interview Answer",
        "original_title": "raw title",
        "provenance_class": "creator_experience",
        "mental_model": [
            "Appraisal → gather voyage information before drawing the route",
            "Planning → build the berth-to-berth route",
            "Execution → follow the approved plan",
            "Monitoring → check progress",
        ],
        "key_items": items,
        "authority_targets": ["ALU-001", "ALU-002"],
    }


class TopicPacketTests(unittest.TestCase):
    def test_classifies_passage_planning_topic(self) -> None:
        topic_id, title = classify_blueprint_topic(blueprint("RAW-1"))
        self.assertEqual(topic_id, "passage-planning")
        self.assertEqual(title, "Passage Planning")

    def test_combines_sources_without_treating_repetition_as_truth(self) -> None:
        packet = build_topic_packet(
            [blueprint("RAW-1"), blueprint("RAW-2", duplicate_stage_claim=True)],
            topic_id="passage-planning",
            display_title="Passage Planning",
        )
        self.assertEqual(packet.source_count, 2)
        self.assertEqual(len(packet.claims), 2)
        stage_claim = next(
            claim for claim in packet.claims if "four stages" in claim.statement.lower()
        )
        self.assertEqual(len(stage_claim.occurrences), 2)
        self.assertEqual(
            {item["source_id"] for item in stage_claim.occurrences},
            {"RAW-1", "RAW-2"},
        )

    def test_authority_queue_preserves_source_and_alu_identity(self) -> None:
        packet = build_topic_packet(
            [blueprint("RAW-1")],
            topic_id="passage-planning",
            display_title="Passage Planning",
        )
        self.assertEqual(len(packet.authority_targets), 2)
        self.assertEqual(packet.authority_targets[0]["source_id"], "RAW-1")
        self.assertEqual(packet.authority_targets[0]["alu_id"], "ALU-001")

    def test_packet_json_keeps_cross_source_scope_note(self) -> None:
        packet = build_topic_packet(
            [blueprint("RAW-1")],
            topic_id="passage-planning",
            display_title="Passage Planning",
        )
        payload = topic_packet_to_json(packet)
        self.assertEqual(payload["artifact_type"], "topic_packet")
        self.assertIn("does not establish truth", payload["scope_note"])

    def test_markdown_warns_repetition_is_not_proof(self) -> None:
        packet = build_topic_packet(
            [blueprint("RAW-1")],
            topic_id="passage-planning",
            display_title="Passage Planning",
        )
        text = render_topic_packet(packet)
        self.assertIn("Repetition across sources is not proof", text)
        self.assertIn("## Authority queue", text)

    def test_writes_topic_packet_atomically(self) -> None:
        packet = build_topic_packet(
            [blueprint("RAW-1")],
            topic_id="passage-planning",
            display_title="Passage Planning",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path, md_path = write_topic_packet(packet, output_dir=temp_dir)
            self.assertTrue(json_path.is_file())
            self.assertTrue(md_path.is_file())
            self.assertFalse(Path(temp_dir, "topic_packet.json.tmp").exists())
            self.assertFalse(Path(temp_dir, "topic_packet.md.tmp").exists())


if __name__ == "__main__":
    unittest.main()
