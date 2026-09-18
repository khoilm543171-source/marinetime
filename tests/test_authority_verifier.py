from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.authority.verify import (
    SUPPORT_DIRECT,
    SUPPORT_NOT_APPLICABLE,
    SUPPORT_PARTIAL,
    SUPPORT_UNRESOLVED,
    build_authority_review,
    classify_passage_planning_claim,
    render_authority_review,
)


class AuthorityVerifierTests(unittest.TestCase):
    def test_four_stage_framework_has_direct_official_support(self) -> None:
        finding = classify_passage_planning_claim(
            alu_id="ALU-001",
            source_id="RAW-1",
            statement=(
                "The creator states that passage planning consists of four stages: "
                "appraisal, planning, execution, and monitoring."
            ),
        )
        self.assertEqual(finding.support_status, SUPPORT_DIRECT)
        self.assertTrue(
            any(ref["authority_source_id"] == "IMO-A893-21" for ref in finding.authority_refs)
        )
        self.assertTrue(
            any(ref["authority_source_id"] == "MCA-OOW-034-83" for ref in finding.authority_refs)
        )

    def test_interview_strategy_is_not_applicable_to_navigation_authority(self) -> None:
        finding = classify_passage_planning_claim(
            alu_id="ALU-002",
            source_id="RAW-1",
            statement=(
                "The creator recommends explaining passage planning from real experience "
                "rather than reading a checklist in an interview."
            ),
        )
        self.assertEqual(finding.support_status, SUPPORT_NOT_APPLICABLE)
        self.assertEqual(finding.authority_refs, ())

    def test_appraisal_creator_list_is_partial_not_overpromoted(self) -> None:
        finding = classify_passage_planning_claim(
            alu_id="ALU-003",
            source_id="RAW-1",
            statement=(
                "The creator describes collecting information from agents, charterer voyage "
                "instructions, charts, ENC updates, warnings, tides, UKC, and port information "
                "before drawing the route during appraisal."
            ),
        )
        self.assertEqual(finding.support_status, SUPPORT_PARTIAL)
        self.assertIn("does not reproduce every", finding.rationale)

    def test_gps_absolute_wording_is_only_partial_support(self) -> None:
        finding = classify_passage_planning_claim(
            alu_id="ALU-006",
            source_id="RAW-1",
            statement=(
                "The creator recommends never relying on one position-fixing method only, "
                "specifically stating never to rely on GPS alone during monitoring."
            ),
        )
        self.assertEqual(finding.support_status, SUPPORT_PARTIAL)
        self.assertIn("exact absolute wording", finding.rationale)

    def test_unknown_claim_remains_unresolved(self) -> None:
        finding = classify_passage_planning_claim(
            alu_id="ALU-X",
            source_id="RAW-1",
            statement="The creator makes an unrelated claim about paint color.",
        )
        self.assertEqual(finding.support_status, SUPPORT_UNRESOLVED)

    def test_review_counts_findings_without_mutating_alu_status(self) -> None:
        review = build_authority_review(
            topic_id="passage-planning",
            targets=[
                {
                    "source_id": "RAW-1",
                    "alu_id": "ALU-001",
                    "statement": (
                        "The creator states that passage planning consists of four stages: "
                        "appraisal, planning, execution, and monitoring."
                    ),
                },
                {
                    "source_id": "RAW-1",
                    "alu_id": "ALU-002",
                    "statement": (
                        "The creator recommends explaining passage planning from real experience "
                        "rather than reading a checklist in an interview."
                    ),
                },
            ],
        )
        self.assertEqual(review["counts"][SUPPORT_DIRECT], 1)
        self.assertEqual(review["counts"][SUPPORT_NOT_APPLICABLE], 1)
        self.assertIn("does not mutate", review["promotion_note"])

    def test_markdown_explicitly_preserves_original_alus(self) -> None:
        review = build_authority_review(
            topic_id="passage-planning",
            targets=[
                {
                    "source_id": "RAW-1",
                    "alu_id": "ALU-001",
                    "statement": (
                        "The creator states that passage planning consists of four stages: "
                        "appraisal, planning, execution, and monitoring."
                    ),
                }
            ],
        )
        text = render_authority_review(review)
        self.assertIn("Original ALUs remain unchanged", text)
        self.assertIn("IMO-A893-21", text)
        self.assertIn("Authority support does not automatically grant operational permission", text)


if __name__ == "__main__":
    unittest.main()
