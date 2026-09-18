from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.learning.topic_lesson import (  # noqa: E402
    TopicLessonError,
    build_topic_lesson,
    write_topic_lesson_artifacts,
)


DEFAULT_TOPICS = ROOT / "storage" / "learning" / "topics"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Build an authority-aware learner-facing topic lesson plus deterministic QA."
        )
    )
    p.add_argument("--topic-root", type=Path, default=DEFAULT_TOPICS)
    p.add_argument("--topic", default="passage-planning")
    return p


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON_OBJECT_REQUIRED")
    return payload


def main() -> int:
    args = parser().parse_args()
    root = args.topic_root / args.topic
    topic_packet_path = root / "topic_packet.json"
    authority_review_path = root / "authority_review.json"

    print("TOPIC_LESSON_START")
    print(f"topic={args.topic}")
    print("provider_calls=0")

    try:
        topic_packet = _load_json(topic_packet_path)
        authority_review = _load_json(authority_review_path)
        lesson = build_topic_lesson(
            topic_packet=topic_packet,
            authority_review=authority_review,
        )
        lesson_json, lesson_md, qa_json, qa_md = write_topic_lesson_artifacts(
            lesson,
            output_dir=root,
        )
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        TopicLessonError,
    ) as exc:
        print(
            f"TOPIC_LESSON_FAILED:{type(exc).__name__}:"
            f"{' '.join(str(exc).split())[:400]}",
            file=sys.stderr,
        )
        return 1

    assessment = lesson.payload["assessment"]
    print(
        "TOPIC_LESSON_OK "
        f"sources={lesson.payload['source_count']} "
        f"stages={len(lesson.payload['stage_lessons'])} "
        f"retrieval_questions={len(assessment['retrieval_practice'])} "
        f"oral_assessment=1"
    )
    print(f"lesson_json={lesson_json}")
    print(f"lesson_markdown={lesson_md}")
    print(f"qa_json={qa_json}")
    print(f"qa_markdown={qa_md}")
    print("provider_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
