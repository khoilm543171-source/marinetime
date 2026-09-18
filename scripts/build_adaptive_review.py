from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.learning.adaptive_review import build_adaptive_review_plan  # noqa: E402
from marinetime.learning.mastery import MasteryStateError, write_json_atomic  # noqa: E402


DEFAULT_TOPICS = ROOT / "storage" / "learning" / "topics"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Build the next grounded review session from learner mastery state."
    )
    p.add_argument("--topic-root", type=Path, default=DEFAULT_TOPICS)
    p.add_argument("--topic", default="passage-planning")
    p.add_argument("--max-items", type=int, default=3)
    p.add_argument("--now", default=None)
    return p


def _load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON_OBJECT_REQUIRED")
    return payload


def _render(plan: dict) -> str:
    lines = [
        f"# {plan.get('topic_id')} — Adaptive Review",
        "",
        f"- **Due concepts:** {plan.get('due_concept_count', 0)}",
        f"- **Selected:** {plan.get('selected_count', 0)}",
        "",
    ]
    if not plan.get("items"):
        lines.extend(["No grounded review item is due right now.", ""])
    for index, item in enumerate(plan.get("items") or [], start=1):
        lines.extend(
            [
                f"## {index}. {item.get('concept_label')}",
                "",
                f"- Ownership: **{item.get('ownership_stage')}**",
                f"- Mastery: {float(item.get('mastery_score') or 0):.0%}",
                f"- Assessment: {item.get('assessment_id')}",
                f"- Evidence target: {item.get('recommended_evidence_type')}",
                "",
                str(item.get("prompt") or ""),
                "",
            ]
        )
    lines.extend(
        [
            "> Review selection is deterministic and reuses grounded lesson assessments; it does not invent factual content.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = parser().parse_args()
    root = args.topic_root / args.topic
    print("ADAPTIVE_REVIEW_START")
    print(f"topic={args.topic}")
    print("provider_calls=0")
    try:
        state = _load(root / "learner_state.json")
        practice = _load(root / "practice_session.json")
        plan = build_adaptive_review_plan(
            state=state,
            practice_session=practice,
            now=args.now,
            max_items=args.max_items,
        )
        json_path = write_json_atomic(root / "adaptive_review.json", plan)
        md_path = root / "adaptive_review.md"
        temp = md_path.with_suffix(".md.tmp")
        temp.write_text(_render(plan), encoding="utf-8")
        temp.replace(md_path)
    except (OSError, ValueError, json.JSONDecodeError, MasteryStateError) as exc:
        print(
            f"ADAPTIVE_REVIEW_FAILED:{type(exc).__name__}:"
            f"{' '.join(str(exc).split())[:400]}",
            file=sys.stderr,
        )
        return 1

    print(
        f"ADAPTIVE_REVIEW_OK due={plan['due_concept_count']} "
        f"selected={plan['selected_count']}"
    )
    print(f"review_json={json_path}")
    print(f"review_markdown={md_path}")
    print("provider_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
