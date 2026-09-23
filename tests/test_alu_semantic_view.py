from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from marinetime.llm.router import LLMTaskResult
from marinetime.pipeline.alu_extract import build_semantic_evidence_view, extract_alus


def evidence_pack() -> dict:
    return {
        "schema_version": "1.0",
        "source_id": "VID-COMPACT-001",
        "provenance_class": "creator_experience",
        "context": {"equipment": "unknown"},
        "transcript_segments": [
            {
                "evidence_id": "SEG-001",
                "start_ms": 0,
                "end_ms": 1000,
                "text": "Example statement",
            }
        ],
        "ocr_hits": [
            {
                "evidence_id": "OCR-001",
                "timestamp_ms": 500,
                "text": "PUMP 01",
                "score": 0.93,
                "polygon": [[1, 2], [3, 4], [5, 6], [7, 8]],
                "frame_artifact_path": "frames/frame_001.jpg",
            }
        ],
        "frames": [
            {
                "evidence_id": "FRAME-001",
                "timestamp_ms": 500,
                "artifact_path": "frames/frame_001.jpg",
                "content_hash": "sha256:deadbeef",
            }
        ],
        "preprocess_version": "pilot-v1",
    }


def valid_response() -> str:
    return json.dumps(
        {
            "alus": [
                {
                    "schema_version": "1.0",
                    "alu_id": "ALU-001",
                    "source_id": "VID-COMPACT-001",
                    "evidence_refs": ["SEG-001", "OCR-001"],
                    "statement": "The source contains an example statement and OCR label.",
                    "statement_type": "creator_statement",
                    "support_level": "directly_supported",
                    "rendering_scope": "source_specific",
                    "claim_scope": "minimal",
                    "context_requirement": "minimal",
                    "provenance_class": "creator_experience",
                    "verification_status": "unverified",
                    "context": {"equipment": "unknown"},
                    "safety": {"safety_critical": False, "numeric_claim": False},
                    "numeric": None,
                    "relation": None,
                }
            ]
        }
    )


class CompactSemanticViewTests(unittest.TestCase):
    def test_strips_nonsemantic_geometry_hashes_and_paths_but_keeps_evidence(self):
        compact = build_semantic_evidence_view(evidence_pack())
        serialized = json.dumps(compact)

        self.assertIn("SEG-001", serialized)
        self.assertIn("OCR-001", serialized)
        self.assertIn("FRAME-001", serialized)
        self.assertIn("PUMP 01", serialized)
        self.assertNotIn("polygon", serialized)
        self.assertNotIn("artifact_path", serialized)
        self.assertNotIn("content_hash", serialized)
        self.assertEqual(compact["ocr_hits"][0]["score"], 0.93)

    def test_extract_sends_compact_view_but_validates_against_canonical_pack(self):
        model_result = LLMTaskResult(
            text=valid_response(),
            model="fake-model",
            task="alu_extract",
            prompt_version="alu_extraction_v4",
            input_tokens=10,
            output_tokens=5,
            stop_reason="end_turn",
        )
        with patch("marinetime.llm.router.run_task", return_value=model_result) as mocked:
            result = extract_alus(client=object(), evidence_pack=evidence_pack())

        dynamic_input = mocked.call_args.kwargs["dynamic_input"]
        self.assertNotIn("polygon", dynamic_input)
        self.assertNotIn("content_hash", dynamic_input)
        self.assertIn("OCR-001", dynamic_input)
        self.assertEqual(mocked.call_args.kwargs["video_id"], "VID-COMPACT-001")
        self.assertEqual(result.alus[0].alu["evidence_refs"], ["SEG-001", "OCR-001"])


if __name__ == "__main__":
    unittest.main()
