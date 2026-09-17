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
            "rendering_scope": "context_specific",
            "context_requirement": "minimal",
            "context": {},
            "safety": {"safety_critical": False, "numeric_claim": False},
            "verification_status": "verified",
        }

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
        alu["rendering_scope"] = "authoritative_operational"
        d = validate_alu(alu)
        self.assertFalse(d.accepted_for_operational_use)
        self.assertIn("PROVENANCE_SCOPE_VIOLATION", d.reasons)

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

    def test_numeric_claim_requires_context(self):
        alu = self.base()
        alu["safety"] = {"safety_critical": True, "numeric_claim": True}
        alu["numeric"] = {"value": 8, "unit": "bar"}
        d = validate_alu(alu)
        self.assertFalse(d.accepted_for_operational_use)
        self.assertTrue(any(r.startswith("NUMERIC_CONTEXT_INCOMPLETE") for r in d.reasons))


if __name__ == "__main__":
    unittest.main()
