import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from marinetime.validation.safety import validate_alu


class SafetyValidationTests(unittest.TestCase):
    def base(self):
        return {
            "evidence_refs": ["SEG-01"],
            "support_level": "directly_supported",
            "provenance_class": "maker_manual",
            "rendering_scope": "authoritative_operational",
            "claim_scope": "minimal",
            "context_requirement": "minimal",
            "context": {},
            "safety": {"safety_critical": False, "numeric_claim": False},
            "verification_status": "verified",
        }

    def test_verified_authoritative_maker_manual_can_be_operational(self):
        d = validate_alu(self.base())
        self.assertTrue(d.accepted_for_operational_use)

    def test_missing_evidence_blocks_education_and_operation(self):
        alu = self.base()
        alu["evidence_refs"] = []
        d = validate_alu(alu)
        self.assertTrue(d.accepted_for_reference)
        self.assertFalse(d.accepted_for_education)
        self.assertFalse(d.accepted_for_operational_use)

    def test_creator_experience_cannot_be_authoritative_operational(self):
        alu = self.base()
        alu["provenance_class"] = "creator_experience"
        d = validate_alu(alu)
        self.assertFalse(d.accepted_for_operational_use)
        self.assertIn("PROVENANCE_SCOPE_VIOLATION", d.reasons)
        self.assertIn("PROVENANCE_NOT_OPERATIONAL_AUTHORITY", d.reasons)

    def test_textbook_is_not_operational_authority(self):
        alu = self.base()
        alu["provenance_class"] = "textbook"
        d = validate_alu(alu)
        self.assertTrue(d.accepted_for_education)
        self.assertFalse(d.accepted_for_operational_use)
        self.assertIn("PROVENANCE_NOT_OPERATIONAL_AUTHORITY", d.reasons)

    def test_partial_support_is_not_operational(self):
        alu = self.base()
        alu["support_level"] = "partially_supported"
        d = validate_alu(alu)
        self.assertTrue(d.accepted_for_education)
        self.assertFalse(d.accepted_for_operational_use)
        self.assertIn("SUPPORT_INSUFFICIENT_FOR_OPERATION", d.reasons)

    def test_verified_context_specific_alu_is_still_not_operational(self):
        alu = self.base()
        alu["rendering_scope"] = "context_specific"
        d = validate_alu(alu)
        self.assertFalse(d.accepted_for_operational_use)
        self.assertIn("RENDERING_SCOPE_NOT_OPERATIONAL", d.reasons)

    def test_unverified_alu_cannot_be_operational(self):
        alu = self.base()
        alu["verification_status"] = "unverified"
        d = validate_alu(alu)
        self.assertTrue(d.accepted_for_reference)
        self.assertTrue(d.accepted_for_education)
        self.assertFalse(d.accepted_for_operational_use)
        self.assertIn("NOT_VERIFIED_FOR_OPERATION", d.reasons)

    def test_maker_specific_unknown_maker_blocks_operation(self):
        alu = self.base()
        alu["context_requirement"] = "maker_specific"
        alu["context"] = {"maker": "unknown"}
        d = validate_alu(alu)
        self.assertFalse(d.accepted_for_operational_use)
        self.assertIn("MAKER_CONTEXT_MISSING", d.reasons)

    def test_claim_scope_also_enforces_required_context(self):
        alu = self.base()
        alu["claim_scope"] = "maker_specific"
        alu["context_requirement"] = "minimal"
        alu["context"] = {"maker": "unknown"}
        d = validate_alu(alu)
        self.assertFalse(d.accepted_for_operational_use)
        self.assertIn("MAKER_CONTEXT_MISSING", d.reasons)

    def test_numeric_claim_requires_context(self):
        alu = self.base()
        alu["safety"] = {"safety_critical": True, "numeric_claim": True}
        alu["numeric"] = {"value": 8, "unit": "bar"}
        d = validate_alu(alu)
        self.assertFalse(d.accepted_for_operational_use)
        self.assertTrue(any(r.startswith("NUMERIC_CONTEXT_INCOMPLETE") for r in d.reasons))

    def test_numeric_source_evidence_must_link_to_alu_evidence(self):
        alu = self.base()
        alu["safety"] = {"safety_critical": True, "numeric_claim": True}
        alu["numeric"] = {
            "value": 8,
            "unit": "bar",
            "measurement_condition": "running",
            "equipment_context": "pump discharge",
            "source_evidence": "SEG-99",
        }
        d = validate_alu(alu)
        self.assertFalse(d.accepted_for_operational_use)
        self.assertIn("NUMERIC_SOURCE_EVIDENCE_MISMATCH", d.reasons)

    def test_complete_numeric_claim_can_pass_numeric_gate(self):
        alu = self.base()
        alu["safety"] = {"safety_critical": True, "numeric_claim": True}
        alu["numeric"] = {
            "value": 8,
            "unit": "bar",
            "measurement_condition": "running",
            "equipment_context": "pump discharge",
            "source_evidence": "SEG-01",
        }
        d = validate_alu(alu)
        self.assertNotIn("NUMERIC_SOURCE_EVIDENCE_MISMATCH", d.reasons)
        self.assertFalse(any(r.startswith("NUMERIC_CONTEXT_INCOMPLETE") for r in d.reasons))
        self.assertTrue(d.accepted_for_operational_use)


if __name__ == "__main__":
    unittest.main()
