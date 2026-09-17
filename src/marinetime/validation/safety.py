from __future__ import annotations

from dataclasses import dataclass
from typing import Any


OPERATIONAL_AUTHORITY_PROVENANCE = {"standard", "maker_manual", "regulatory"}


@dataclass(frozen=True)
class ValidationDecision:
    accepted_for_reference: bool
    accepted_for_education: bool
    accepted_for_operational_use: bool
    reasons: tuple[str, ...]


def _is_unknown(value: Any) -> bool:
    return value in (None, "", "unknown", [])


def _numeric_evidence_is_linked(source_evidence: Any, evidence_refs: list[str]) -> bool:
    if isinstance(source_evidence, str):
        return source_evidence in evidence_refs
    if isinstance(source_evidence, list) and source_evidence:
        return all(isinstance(ref, str) and ref in evidence_refs for ref in source_evidence)
    return False


def validate_alu(alu: dict[str, Any]) -> ValidationDecision:
    """Deterministic safety/provenance gate.

    The LLM may suggest fields, but this function decides use eligibility.
    """
    reasons: list[str] = []
    reference = True
    educational = True
    operational = True

    evidence_refs = alu.get("evidence_refs") or []
    if not evidence_refs:
        reasons.append("MISSING_EVIDENCE")
        educational = False
        operational = False

    support = alu.get("support_level")
    if support == "unsupported":
        reasons.append("UNSUPPORTED_STATEMENT")
        educational = False
        operational = False
    elif support != "directly_supported":
        reasons.append("SUPPORT_INSUFFICIENT_FOR_OPERATION")
        operational = False

    provenance = alu.get("provenance_class")
    rendering_scope = alu.get("rendering_scope")
    if provenance not in OPERATIONAL_AUTHORITY_PROVENANCE:
        reasons.append("PROVENANCE_NOT_OPERATIONAL_AUTHORITY")
        operational = False

    if provenance in {"creator_experience", "onboard_heuristic", "case_specific", "unverified"}:
        if rendering_scope == "authoritative_operational":
            reasons.append("PROVENANCE_SCOPE_VIOLATION")
            operational = False

    verification_status = alu.get("verification_status")
    if verification_status != "verified":
        reasons.append("NOT_VERIFIED_FOR_OPERATION")
        operational = False

    context = alu.get("context") or {}
    required_scopes = {
        alu.get("context_requirement", "minimal"),
        alu.get("claim_scope", "minimal"),
    }
    if "equipment_specific" in required_scopes and _is_unknown(context.get("equipment")):
        reasons.append("EQUIPMENT_CONTEXT_MISSING")
        operational = False
    if "maker_specific" in required_scopes and _is_unknown(context.get("maker")):
        reasons.append("MAKER_CONTEXT_MISSING")
        operational = False
    if "vessel_specific" in required_scopes and _is_unknown(context.get("vessel_type")):
        reasons.append("VESSEL_CONTEXT_MISSING")
        operational = False
    if "regulatory_specific" in required_scopes and _is_unknown(
        context.get("regulatory_context")
    ):
        reasons.append("REGULATORY_CONTEXT_MISSING")
        operational = False

    safety = alu.get("safety") or {}
    if safety.get("safety_critical") and not evidence_refs:
        reasons.append("SAFETY_CRITICAL_WITHOUT_EVIDENCE")
        operational = False

    if safety.get("numeric_claim"):
        numeric = alu.get("numeric") or {}
        required_numeric = (
            "value",
            "unit",
            "measurement_condition",
            "equipment_context",
            "source_evidence",
        )
        missing = [field for field in required_numeric if _is_unknown(numeric.get(field))]
        if missing:
            reasons.append("NUMERIC_CONTEXT_INCOMPLETE:" + ",".join(missing))
            operational = False
        elif not _numeric_evidence_is_linked(numeric.get("source_evidence"), evidence_refs):
            reasons.append("NUMERIC_SOURCE_EVIDENCE_MISMATCH")
            operational = False

    if verification_status == "rejected":
        reasons.append("VERIFICATION_REJECTED")
        educational = False
        operational = False

    return ValidationDecision(
        accepted_for_reference=reference,
        accepted_for_education=educational,
        accepted_for_operational_use=operational,
        reasons=tuple(reasons),
    )
