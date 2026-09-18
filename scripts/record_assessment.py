from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.learning.evidence_gate import validate_evidence_progression  # noqa: E402
from marinetime.learning.mastery import (  # noqa: E402
    MasteryStateError,
    apply_assessment_result,
    due_concepts,
    normalize_assessment_result,
    render_mastery_state,
    write_json_atomic,
)

DEFAULT_TOPICS = ROOT / "storage" / "learning" / "topics"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Record explicit learner evidence and update concept ownership state.")
    p.add_argument("--topic-root", type=Path, default=DEFAULT_TOPICS)
    p.add_argument("--topic", default="passage-planning")
    p.add_argument("--assessment-id", required=True)
    p.add_argument("--score", type=float, required=True)
    p.add_argument("--evidence-type", required=True, choices=("retrieval", "oral", "scenario", "delayed_recall"))
    p.add_argument("--assessed-at")
    p.add_argument("--delayed-hours", type=float, default=0.0)
    p.add_argument("--notes")
    return p


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON_OBJECT_REQUIRED")
    return payload


def _write_markdown(path: Path, text: str) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


def main() -> int:
    args = parser().parse_args()
    root = args.topic_root / args.topic
    state_path = root / "learner_state.json"
    practice_path = root / "practice_session.json"
    markdown_path = root / "learner_state.md"
    print("ASSESSMENT_RECORD_START")
    print(f"topic={args.topic}")
    print(f"assessment_id={args.assessment_id}")
    print(f"evidence_type={args.evidence_type}")
    print("provider_calls=0")
    try:
        state = _load_json(state_path)
        practice = _load_json(practice_path)
        result = normalize_assessment_result(
            practice_session=practice,
            assessment_id=args.assessment_id,
            score=args.score,
            evidence_type=args.evidence_type,
            assessed_at=args.assessed_at,
            delayed_hours=args.delayed_hours,
            notes=args.notes,
        )
        validate_evidence_progression(state=state, result=result)
        before = {
            concept_id: {"ownership_stage": item.get("ownership_stage"), "mastery_score": item.get("mastery_score")}
            for concept_id, item in (state.get("concepts") or {}).items()
            if concept_id in result.concept_ids and isinstance(item, dict)
        }
        apply_assessment_result(state=state, result=result)
        write_json_atomic(state_path, state)
        _write_markdown(markdown_path, render_mastery_state(state))
        changed = []
        for concept_id in result.concept_ids:
            item = state["concepts"][concept_id]
            previous = before.get(concept_id, {})
            changed.append({
                "concept_id": concept_id,
                "from_stage": previous.get("ownership_stage"),
                "to_stage": item.get("ownership_stage"),
                "from_score": previous.get("mastery_score"),
                "to_score": item.get("mastery_score"),
            })
        due = due_concepts(state, now=result.assessed_at)
    except (OSError, ValueError, json.JSONDecodeError, MasteryStateError) as exc:
        print(f"ASSESSMENT_RECORD_FAILED:{type(exc).__name__}:{' '.join(str(exc).split())[:400]}", file=sys.stderr)
        return 1
    print("ASSESSMENT_RECORD_OK")
    print(f"score={result.score:.3f}")
    print(f"concepts_updated={len(changed)}")
    for item in changed:
        print(
            "CONCEPT_UPDATE "
            f"concept_id={item['concept_id']} "
            f"stage={item['from_stage']}->{item['to_stage']} "
            f"mastery={float(item['from_score'] or 0.0):.3f}->{float(item['to_score'] or 0.0):.3f}"
        )
    print(f"topic_mastery={float(state.get('topic_mastery_score') or 0.0):.3f}")
    print(f"due_now={len(due)}")
    print(f"state_json={state_path}")
    print(f"state_markdown={markdown_path}")
    print("provider_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
