from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.learning.mastery import (  # noqa: E402
    MasteryStateError,
    build_initial_learner_state,
    build_practice_session,
    render_mastery_state,
    write_json_atomic,
)


DEFAULT_TOPICS = ROOT / "storage" / "learning" / "topics"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Initialize deterministic learner ownership state from a topic lesson."
    )
    p.add_argument("--topic-root", type=Path, default=DEFAULT_TOPICS)
    p.add_argument("--topic", default="passage-planning")
    p.add_argument("--learner-id", default="local-user")
    return p


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON_OBJECT_REQUIRED")
    return payload


def main() -> int:
    args = parser().parse_args()
    root = args.topic_root / args.topic
    lesson_path = root / "topic_lesson.json"

    print("LEARNER_STATE_INIT_START")
    print(f"topic={args.topic}")
    print("provider_calls=0")

    try:
        lesson = _load_json(lesson_path)
        state = build_initial_learner_state(
            topic_lesson=lesson,
            learner_id=args.learner_id,
        )
        practice = build_practice_session(lesson)
        state_json = write_json_atomic(root / "learner_state.json", state)
        practice_json = write_json_atomic(root / "practice_session.json", practice)

        state_md = root / "learner_state.md"
        temp = state_md.with_suffix(".md.tmp")
        temp.write_text(render_mastery_state(state), encoding="utf-8")
        temp.replace(state_md)
    except (OSError, ValueError, json.JSONDecodeError, MasteryStateError) as exc:
        print(
            f"LEARNER_STATE_INIT_FAILED:{type(exc).__name__}:"
            f"{' '.join(str(exc).split())[:400]}",
            file=sys.stderr,
        )
        return 1

    print(
        f"LEARNER_STATE_INIT_OK concepts={len(state['concepts'])} "
        f"practice_items={len(practice['retrieval_items'])} "
        f"oral_item={1 if practice.get('oral_item') else 0}"
    )
    print(f"state_json={state_json}")
    print(f"state_markdown={state_md}")
    print(f"practice_json={practice_json}")
    print("provider_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
