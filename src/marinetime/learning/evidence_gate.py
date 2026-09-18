from __future__ import annotations

from typing import Any

from .mastery import AssessmentResult, MasteryStateError


_STAGE_RANK = {
    "seen": 0,
    "understood": 1,
    "recalled": 2,
    "explained": 3,
    "applied": 4,
    "retained": 5,
}


def validate_evidence_progression(
    *,
    state: dict[str, Any],
    result: AssessmentResult,
) -> None:
    """Fail closed when evidence would claim a capability not yet demonstrated.

    The mastery engine records evidence; this gate protects the meaning of higher
    ownership stages. In particular, delayed recall proves retention of something
    previously learned, not application by itself.
    """
    if state.get("artifact_type") != "learner_mastery_state":
        raise MasteryStateError("LEARNER_MASTERY_STATE_REQUIRED")
    concepts = state.get("concepts")
    if not isinstance(concepts, dict):
        raise MasteryStateError("CONCEPT_STATE_REQUIRED")

    for concept_id in result.concept_ids:
        concept = concepts.get(concept_id)
        if not isinstance(concept, dict):
            raise MasteryStateError(f"UNKNOWN_CONCEPT_ID:{concept_id}")
        current = str(concept.get("ownership_stage") or "seen")
        rank = _STAGE_RANK.get(current, 0)

        if result.evidence_type == "oral" and rank < _STAGE_RANK["recalled"]:
            raise MasteryStateError(
                f"EVIDENCE_PREREQUISITE_NOT_MET:{concept_id}:oral_requires_recalled"
            )
        if result.evidence_type == "scenario" and rank < _STAGE_RANK["explained"]:
            raise MasteryStateError(
                f"EVIDENCE_PREREQUISITE_NOT_MET:{concept_id}:scenario_requires_explained"
            )
        if result.evidence_type == "delayed_recall" and rank < _STAGE_RANK["applied"]:
            raise MasteryStateError(
                f"EVIDENCE_PREREQUISITE_NOT_MET:{concept_id}:delayed_recall_requires_applied"
            )

        if result.evidence_type == "delayed_recall" and result.delayed_hours < 24:
            raise MasteryStateError(
                f"RETENTION_DELAY_TOO_SHORT:{concept_id}:minimum_24_hours"
            )
