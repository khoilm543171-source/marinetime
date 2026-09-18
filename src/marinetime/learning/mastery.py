from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


class MasteryStateError(ValueError):
    """Raised when learner-state evidence is malformed or cannot be applied safely."""


STAGES = ("seen", "understood", "recalled", "explained", "applied", "retained")
_STAGE_RANK = {stage: index for index, stage in enumerate(STAGES)}

# Pilot heuristic only. These are scheduling defaults, not claims of optimal pedagogy.
_NEXT_REVIEW_DAYS = {
    "seen": 0,
    "understood": 1,
    "recalled": 2,
    "explained": 4,
    "applied": 7,
    "retained": 14,
}


@dataclass(frozen=True)
class AssessmentResult:
    assessment_id: str
    concept_ids: tuple[str, ...]
    evidence_type: str
    score: float
    assessed_at: str
    delayed_hours: float = 0.0
    notes: str | None = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MasteryStateError("INVALID_ASSESSED_AT") from exc
    if parsed.tzinfo is None:
        raise MasteryStateError("ASSESSED_AT_MUST_INCLUDE_TIMEZONE")
    return parsed.astimezone(timezone.utc)


def _validate_score(score: Any) -> float:
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise MasteryStateError("INVALID_SCORE")
    value = float(score)
    if value < 0 or value > 1:
        raise MasteryStateError("SCORE_OUT_OF_RANGE")
    return value


def _concepts_from_topic_lesson(topic_lesson: dict[str, Any]) -> list[dict[str, Any]]:
    if topic_lesson.get("artifact_type") != "topic_lesson":
        raise MasteryStateError("TOPIC_LESSON_REQUIRED")
    topic_id = str(topic_lesson.get("topic_id") or "").strip()
    if not topic_id:
        raise MasteryStateError("TOPIC_ID_REQUIRED")

    concepts = [
        {
            "concept_id": f"{topic_id}:framework",
            "label": "Four-stage framework",
            "kind": "framework",
            "stage": None,
        }
    ]
    for stage in topic_lesson.get("stage_lessons") or []:
        if not isinstance(stage, dict):
            continue
        stage_id = str(stage.get("stage") or "").strip()
        if not stage_id:
            continue
        concepts.append(
            {
                "concept_id": f"{topic_id}:{stage_id}",
                "label": str(stage.get("title") or stage_id.title()),
                "kind": "stage",
                "stage": stage_id,
            }
        )
    concepts.append(
        {
            "concept_id": f"{topic_id}:authority-boundary",
            "label": "Authority vs creator wording",
            "kind": "boundary",
            "stage": None,
        }
    )
    concepts.append(
        {
            "concept_id": f"{topic_id}:oral-answer",
            "label": "60–90 second oral explanation",
            "kind": "performance",
            "stage": None,
        }
    )
    return concepts


def _assessment_concept_map(topic_lesson: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    topic_id = str(topic_lesson.get("topic_id") or "").strip()
    mapping: dict[str, tuple[str, ...]] = {
        "Q-01": (f"{topic_id}:framework",),
        "Q-06": (f"{topic_id}:authority-boundary",),
        "ORAL-01": (
            f"{topic_id}:framework",
            f"{topic_id}:appraisal",
            f"{topic_id}:planning",
            f"{topic_id}:execution",
            f"{topic_id}:monitoring",
            f"{topic_id}:authority-boundary",
            f"{topic_id}:oral-answer",
        ),
    }
    stage_to_q = {
        "appraisal": "Q-02",
        "planning": "Q-03",
        "execution": "Q-04",
        "monitoring": "Q-05",
    }
    for stage in topic_lesson.get("stage_lessons") or []:
        if not isinstance(stage, dict):
            continue
        stage_id = str(stage.get("stage") or "").strip()
        qid = stage_to_q.get(stage_id)
        if qid:
            mapping[qid] = (f"{topic_id}:{stage_id}",)
    return mapping


def build_initial_learner_state(
    *,
    topic_lesson: dict[str, Any],
    learner_id: str = "local-user",
    created_at: str | None = None,
) -> dict[str, Any]:
    concepts = _concepts_from_topic_lesson(topic_lesson)
    now = created_at or _utc_now_iso()
    _parse_iso(now)

    state = {
        "schema_version": "1.0",
        "artifact_type": "learner_mastery_state",
        "learner_id": learner_id,
        "topic_id": topic_lesson["topic_id"],
        "created_at": now,
        "updated_at": now,
        "concepts": {
            item["concept_id"]: {
                "concept_id": item["concept_id"],
                "label": item["label"],
                "kind": item["kind"],
                "stage_context": item["stage"],
                "ownership_stage": "seen",
                "mastery_score": 0.0,
                "evidence_count": 0,
                "last_assessed_at": None,
                "next_review_at": now,
                "assessment_history": [],
            }
            for item in concepts
        },
        "topic_mastery_score": 0.0,
        "scope_note": (
            "Mastery is inferred only from recorded learner evidence. Generating or reading "
            "a lesson alone does not establish ownership."
        ),
        "scheduling_note": (
            "Review intervals are pilot heuristics and may be replaced by a calibrated scheduler."
        ),
    }
    return state


def build_practice_session(topic_lesson: dict[str, Any]) -> dict[str, Any]:
    if topic_lesson.get("artifact_type") != "topic_lesson":
        raise MasteryStateError("TOPIC_LESSON_REQUIRED")
    concept_map = _assessment_concept_map(topic_lesson)
    retrieval = []
    for item in (topic_lesson.get("assessment") or {}).get("retrieval_practice") or []:
        if not isinstance(item, dict):
            continue
        assessment_id = str(item.get("assessment_id") or "").strip()
        if not assessment_id:
            continue
        retrieval.append(
            {
                "assessment_id": assessment_id,
                "type": item.get("type"),
                "prompt": item.get("prompt"),
                "concept_ids": list(concept_map.get(assessment_id, ())),
                "scoring_mode": "normalized_score_required",
            }
        )

    oral = (topic_lesson.get("assessment") or {}).get("oral_exam") or {}
    oral_id = str(oral.get("assessment_id") or "").strip()
    oral_item = None
    if oral_id:
        oral_item = {
            "assessment_id": oral_id,
            "type": "oral_exam",
            "prompt": oral.get("question"),
            "concept_ids": list(concept_map.get(oral_id, ())),
            "rubric": list(oral.get("rubric") or []),
            "scoring_mode": "normalized_score_required",
        }

    return {
        "schema_version": "1.0",
        "artifact_type": "practice_session",
        "topic_id": topic_lesson.get("topic_id"),
        "retrieval_items": retrieval,
        "oral_item": oral_item,
        "note": (
            "This artifact defines what to practice. Free-text/oral grading is not performed "
            "by this deterministic module."
        ),
    }


def normalize_assessment_result(
    *,
    practice_session: dict[str, Any],
    assessment_id: str,
    score: float,
    evidence_type: str,
    assessed_at: str | None = None,
    delayed_hours: float = 0.0,
    notes: str | None = None,
) -> AssessmentResult:
    known: dict[str, tuple[str, ...]] = {}
    for item in practice_session.get("retrieval_items") or []:
        if isinstance(item, dict) and item.get("assessment_id"):
            known[str(item["assessment_id"])] = tuple(item.get("concept_ids") or ())
    oral = practice_session.get("oral_item")
    if isinstance(oral, dict) and oral.get("assessment_id"):
        known[str(oral["assessment_id"])] = tuple(oral.get("concept_ids") or ())

    if assessment_id not in known:
        raise MasteryStateError(f"UNKNOWN_ASSESSMENT_ID:{assessment_id}")
    allowed_types = {"retrieval", "oral", "scenario", "delayed_recall"}
    if evidence_type not in allowed_types:
        raise MasteryStateError(f"INVALID_EVIDENCE_TYPE:{evidence_type}")
    value = _validate_score(score)
    if isinstance(delayed_hours, bool) or not isinstance(delayed_hours, (int, float)):
        raise MasteryStateError("INVALID_DELAYED_HOURS")
    delayed = float(delayed_hours)
    if delayed < 0:
        raise MasteryStateError("NEGATIVE_DELAYED_HOURS")

    timestamp = assessed_at or _utc_now_iso()
    _parse_iso(timestamp)
    return AssessmentResult(
        assessment_id=assessment_id,
        concept_ids=known[assessment_id],
        evidence_type=evidence_type,
        score=value,
        assessed_at=timestamp,
        delayed_hours=delayed,
        notes=notes,
    )


def _evidence_stage(result: AssessmentResult) -> str:
    if result.score < 0.5:
        return "seen"
    if result.evidence_type == "retrieval":
        return "recalled" if result.score >= 0.8 else "understood"
    if result.evidence_type == "oral":
        return "explained" if result.score >= 0.75 else "understood"
    if result.evidence_type == "scenario":
        return "applied" if result.score >= 0.75 else "understood"
    if result.evidence_type == "delayed_recall":
        if result.score >= 0.8 and result.delayed_hours >= 24:
            return "retained"
        return "recalled" if result.score >= 0.8 else "understood"
    raise MasteryStateError(f"INVALID_EVIDENCE_TYPE:{result.evidence_type}")


def _next_review(stage: str, assessed_at: str) -> str:
    parsed = _parse_iso(assessed_at)
    days = _NEXT_REVIEW_DAYS[stage]
    return (parsed + timedelta(days=days)).replace(microsecond=0).isoformat()


def apply_assessment_result(
    *,
    state: dict[str, Any],
    result: AssessmentResult,
) -> dict[str, Any]:
    if state.get("artifact_type") != "learner_mastery_state":
        raise MasteryStateError("LEARNER_MASTERY_STATE_REQUIRED")
    concepts = state.get("concepts")
    if not isinstance(concepts, dict):
        raise MasteryStateError("CONCEPT_STATE_REQUIRED")

    event_stage = _evidence_stage(result)
    for concept_id in result.concept_ids:
        concept = concepts.get(concept_id)
        if not isinstance(concept, dict):
            raise MasteryStateError(f"UNKNOWN_CONCEPT_ID:{concept_id}")

        previous_stage = str(concept.get("ownership_stage") or "seen")
        previous_rank = _STAGE_RANK.get(previous_stage, 0)
        event_rank = _STAGE_RANK[event_stage]
        next_stage = STAGES[max(previous_rank, event_rank)]

        previous_score = float(concept.get("mastery_score") or 0.0)
        evidence_count = int(concept.get("evidence_count") or 0)
        next_score = round(
            ((previous_score * evidence_count) + result.score) / (evidence_count + 1),
            4,
        )

        event = {
            "assessment_id": result.assessment_id,
            "evidence_type": result.evidence_type,
            "score": result.score,
            "assessed_at": result.assessed_at,
            "delayed_hours": result.delayed_hours,
            "ownership_stage_awarded": event_stage,
            "notes": result.notes,
        }
        history = concept.get("assessment_history")
        if not isinstance(history, list):
            history = []
        history.append(event)

        concept["ownership_stage"] = next_stage
        concept["mastery_score"] = next_score
        concept["evidence_count"] = evidence_count + 1
        concept["last_assessed_at"] = result.assessed_at
        concept["next_review_at"] = _next_review(next_stage, result.assessed_at)
        concept["assessment_history"] = history

    scores = [
        float(item.get("mastery_score") or 0.0)
        for item in concepts.values()
        if isinstance(item, dict)
    ]
    state["topic_mastery_score"] = round(sum(scores) / len(scores), 4) if scores else 0.0
    state["updated_at"] = result.assessed_at
    return state


def due_concepts(
    state: dict[str, Any],
    *,
    now: str | None = None,
) -> list[dict[str, Any]]:
    timestamp = _parse_iso(now or _utc_now_iso())
    concepts = state.get("concepts")
    if not isinstance(concepts, dict):
        raise MasteryStateError("CONCEPT_STATE_REQUIRED")

    due = []
    for concept in concepts.values():
        if not isinstance(concept, dict):
            continue
        next_review = concept.get("next_review_at")
        if not isinstance(next_review, str):
            continue
        if _parse_iso(next_review) <= timestamp:
            due.append(concept)
    return sorted(
        due,
        key=lambda item: (
            _STAGE_RANK.get(str(item.get("ownership_stage")), 0),
            float(item.get("mastery_score") or 0.0),
            str(item.get("concept_id")),
        ),
    )


def render_mastery_state(state: dict[str, Any]) -> str:
    lines = [
        f"# {state.get('topic_id')} — Knowledge Ownership",
        "",
        f"- **Topic mastery score:** {float(state.get('topic_mastery_score') or 0.0):.0%}",
        "",
        "## Concepts",
        "",
    ]
    concepts = state.get("concepts") or {}
    for concept_id in sorted(concepts):
        item = concepts[concept_id]
        lines.extend(
            [
                f"### {item.get('label')}",
                "",
                f"- Ownership stage: **{item.get('ownership_stage')}**",
                f"- Mastery score: {float(item.get('mastery_score') or 0.0):.0%}",
                f"- Evidence count: {item.get('evidence_count')}",
                f"- Next review: {item.get('next_review_at')}",
                "",
            ]
        )
    lines.extend(
        [
            "## Ownership ladder",
            "",
            "Seen → Understood → Recalled → Explained → Applied → Retained",
            "",
            "> A generated lesson is not counted as mastery. Only learner evidence moves ownership forward.",
            "",
        ]
    )
    return "\n".join(lines)


def write_json_atomic(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(target)
    return target
