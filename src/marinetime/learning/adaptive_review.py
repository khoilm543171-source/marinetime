from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .mastery import MasteryStateError, due_concepts


_STAGE_PRIORITY = {
    "seen": 0,
    "understood": 1,
    "recalled": 2,
    "explained": 3,
    "applied": 4,
    "retained": 5,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _practice_index(practice_session: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    if practice_session.get("artifact_type") != "practice_session":
        raise MasteryStateError("PRACTICE_SESSION_REQUIRED")
    index: dict[str, list[dict[str, Any]]] = {}
    items = list(practice_session.get("retrieval_items") or [])
    oral = practice_session.get("oral_item")
    if isinstance(oral, dict):
        items.append(oral)
    for item in items:
        if not isinstance(item, dict):
            continue
        for concept_id in item.get("concept_ids") or []:
            index.setdefault(str(concept_id), []).append(item)
    return index


def _recommended_evidence(concept: dict[str, Any]) -> str:
    stage = str(concept.get("ownership_stage") or "seen")
    if stage in {"seen", "understood"}:
        return "retrieval"
    if stage == "recalled":
        return "oral"
    if stage == "explained":
        return "scenario"
    if stage in {"applied", "retained"}:
        return "delayed_recall"
    return "retrieval"


def _compatible(item: dict[str, Any], evidence_type: str) -> bool:
    item_type = str(item.get("type") or "")
    if evidence_type == "oral":
        return item_type == "oral_exam"
    if evidence_type == "retrieval":
        return item_type != "oral_exam"
    # Scenario and delayed-recall can reuse a grounded prompt, but the resulting
    # evidence type must be recorded explicitly by the caller.
    return True


def build_adaptive_review_plan(
    *,
    state: dict[str, Any],
    practice_session: dict[str, Any],
    now: str | None = None,
    max_items: int = 3,
) -> dict[str, Any]:
    if state.get("artifact_type") != "learner_mastery_state":
        raise MasteryStateError("LEARNER_MASTERY_STATE_REQUIRED")
    if state.get("topic_id") != practice_session.get("topic_id"):
        raise MasteryStateError("STATE_PRACTICE_TOPIC_MISMATCH")
    if isinstance(max_items, bool) or not isinstance(max_items, int) or max_items < 1:
        raise MasteryStateError("INVALID_MAX_ITEMS")

    timestamp = now or _now_iso()
    due = due_concepts(state, now=timestamp)
    index = _practice_index(practice_session)
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    used_assessments: set[str] = set()

    for concept in due:
        if len(selected) >= max_items:
            break
        concept_id = str(concept.get("concept_id") or "")
        evidence_type = _recommended_evidence(concept)
        candidates = index.get(concept_id, [])
        candidate = next(
            (
                item
                for item in candidates
                if str(item.get("assessment_id") or "") not in used_assessments
                and _compatible(item, evidence_type)
            ),
            None,
        )
        if candidate is None:
            skipped.append(
                {
                    "concept_id": concept_id,
                    "reason": "NO_COMPATIBLE_GROUNDED_ASSESSMENT",
                }
            )
            continue

        assessment_id = str(candidate.get("assessment_id"))
        used_assessments.add(assessment_id)
        selected.append(
            {
                "concept_id": concept_id,
                "concept_label": concept.get("label"),
                "ownership_stage": concept.get("ownership_stage"),
                "mastery_score": float(concept.get("mastery_score") or 0.0),
                "due_at": concept.get("next_review_at"),
                "assessment_id": assessment_id,
                "prompt": candidate.get("prompt"),
                "recommended_evidence_type": evidence_type,
                "selection_reason": (
                    "Concept is due; lower ownership stage and lower mastery are prioritized."
                ),
            }
        )

    return {
        "schema_version": "1.0",
        "artifact_type": "adaptive_review_plan",
        "topic_id": state.get("topic_id"),
        "generated_at": timestamp,
        "due_concept_count": len(due),
        "selected_count": len(selected),
        "items": selected,
        "skipped": skipped,
        "policy": {
            "priority": "due first, then lower ownership stage, then lower mastery score",
            "evidence_progression": {
                "seen_or_understood": "retrieval",
                "recalled": "oral",
                "explained": "scenario",
                "applied_or_retained": "delayed_recall",
            },
            "provider_calls": 0,
        },
        "note": (
            "The planner selects only assessments already grounded in the topic lesson. "
            "It does not grade answers or invent new factual content."
        ),
    }
