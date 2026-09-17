from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from marinetime.pipeline.evidence_pack import EvidencePackError, validate_evidence_pack


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


class EvidencePackTests(unittest.TestCase):
    def test_accepts_traceable_pack(self):
        summary = validate_evidence_pack(base_pack())
        self.assertEqual(summary.source_id, "VID-001")
        self.assertEqual(summary.provenance_class, "creator_experience")
        self.assertEqual(summary.evidence_ids, frozenset({"SEG-001", "FRAME-001"}))
        self.assertEqual(summary.transcript_count, 1)
        self.assertEqual(summary.frame_count, 1)

    def test_rejects_duplicate_evidence_id_across_modalities(self):
        pack = base_pack()
        pack["frames"][0]["evidence_id"] = "SEG-001"
        with self.assertRaisesRegex(EvidencePackError, "DUPLICATE_EVIDENCE_ID"):
            validate_evidence_pack(pack)

    def test_rejects_noncanonical_evidence_id(self):
        pack = base_pack()
        pack["transcript_segments"][0]["evidence_id"] = " SEG-001 "
        with self.assertRaisesRegex(EvidencePackError, "NONCANONICAL_EVIDENCE_ID"):
            validate_evidence_pack(pack)

    def test_rejects_missing_provenance(self):
        pack = base_pack()
        del pack["provenance_class"]
        with self.assertRaisesRegex(EvidencePackError, "MISSING_TOP_LEVEL:provenance_class"):
            validate_evidence_pack(pack)

    def test_rejects_invalid_transcript_range(self):
        pack = base_pack()
        pack["transcript_segments"][0]["start_ms"] = 2000
        with self.assertRaisesRegex(EvidencePackError, "INVALID_TIMESTAMP_RANGE"):
            validate_evidence_pack(pack)

    def test_rejects_missing_transcript_timestamp(self):
        pack = base_pack()
        del pack["transcript_segments"][0]["start_ms"]
        with self.assertRaisesRegex(EvidencePackError, "INVALID_TIMESTAMP"):
            validate_evidence_pack(pack)

    def test_rejects_missing_transcript_text(self):
        pack = base_pack()
        pack["transcript_segments"][0]["text"] = ""
        with self.assertRaisesRegex(EvidencePackError, "MISSING_TEXT"):
            validate_evidence_pack(pack)

    def test_rejects_frame_without_timestamp(self):
        pack = base_pack()
        del pack["frames"][0]["timestamp_ms"]
        with self.assertRaisesRegex(EvidencePackError, "FRAME_0_INVALID_TIMESTAMP"):
            validate_evidence_pack(pack)

    def test_rejects_ocr_without_text_or_timestamp(self):
        pack = base_pack()
        pack["ocr_hits"] = [{"evidence_id": "OCR-001", "timestamp_ms": 500}]
        with self.assertRaisesRegex(EvidencePackError, "OCR_0_MISSING_TEXT"):
            validate_evidence_pack(pack)

    def test_rejects_unsupported_schema_version(self):
        pack = base_pack()
        pack["schema_version"] = "2.0"
        with self.assertRaisesRegex(EvidencePackError, "UNSUPPORTED_SCHEMA_VERSION"):
            validate_evidence_pack(pack)


if __name__ == "__main__":
    unittest.main()
