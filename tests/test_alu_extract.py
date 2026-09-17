from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from marinetime.pipeline.alu_extract import ALUExtractionError, parse_alu_response


def base_pack():
    return {
        "schema_version": "1.0",
        "source_id": "VID-001",
        "provenance_class": "creator_experience",
        "context": {},
        "transcript_segments": [
            {
                "evidence_id": "SEG-001",
                "start_ms": 0,
                "end_ms": 1200,
                "text": "Example marine engineering statement",
            }
        ],
        "ocr_hits": [],
        "frames": [{"evidence_id": "FRAME-001", "timestamp_ms": 800}],
        "preprocess_version": "pilot-v1",
    }


def base_alu():
    return {
        "schema_version": "1.0",
        "alu_id": "ALU-001",
        "source_id": "VID-001",
        "evidence_refs": ["SEG-001"],
        "statement": "The creator states an example marine engineering point.",
        "statement_type": "creator_statement",
        "support_level": "directly_supported",
        "rendering_scope": "source_specific",
        "context_requirement": "minimal",
        "provenance_class": "creator_experience",
        "verification_status": "unverified",
        "context": {},
        "safety": {"safety_critical": False, "numeric_claim": False},
        "numeric": None,
        "relation": None,
    }


def response_for(alu):
    return json.dumps({"alus": [alu]})


class ALUExtractionTests(unittest.TestCase):
    def test_accepts_grounded_unverified_alu_and_blocks_operation(self):
        result = parse_alu_response(response_for(base_alu()), base_pack())
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].decision.accepted_for_reference)
        self.assertTrue(result[0].decision.accepted_for_education)
        self.assertFalse(result[0].decision.accepted_for_operational_use)
        self.assertIn("NOT_VERIFIED_FOR_OPERATION", result[0].decision.reasons)

    def test_rejects_unknown_evidence_reference(self):
        alu = base_alu()
        alu["evidence_refs"] = ["MADE-UP-REF"]
        with self.assertRaisesRegex(ALUExtractionError, "UNKNOWN_EVIDENCE_REF"):
            parse_alu_response(response_for(alu), base_pack())

    def test_rejects_model_self_verification(self):
        alu = base_alu()
        alu["verification_status"] = "verified"
        with self.assertRaisesRegex(ALUExtractionError, "SELF_VERIFICATION_FORBIDDEN"):
            parse_alu_response(response_for(alu), base_pack())

    def test_rejects_provenance_promotion(self):
        alu = base_alu()
        alu["provenance_class"] = "maker_manual"
        with self.assertRaisesRegex(ALUExtractionError, "PROVENANCE_MISMATCH"):
            parse_alu_response(response_for(alu), base_pack())

    def test_rejects_duplicate_alu_ids(self):
        alu = base_alu()
        text = json.dumps({"alus": [alu, dict(alu)]})
        with self.assertRaisesRegex(ALUExtractionError, "DUPLICATE_ALU_ID"):
            parse_alu_response(text, base_pack())


if __name__ == "__main__":
    unittest.main()
