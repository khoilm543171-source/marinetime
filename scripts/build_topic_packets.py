from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.authority.verify import (  # noqa: E402
    AuthorityVerificationError,
    build_authority_review,
    render_authority_review,
)
from marinetime.learning.topic_packet import (  # noqa: E402
    TopicPacketError,
    build_topic_packet,
    classify_blueprint_topic,
    write_topic_packet,
)


DEFAULT_LESSONS = ROOT / "storage" / "learning" / "lesson_previews"
DEFAULT_OUTPUT = ROOT / "storage" / "learning" / "topics"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Aggregate source lesson blueprints into deterministic topic packets and "
            "build an authority review for supported topics."
        )
    )
    p.add_argument("--lesson-root", type=Path, default=DEFAULT_LESSONS)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--topic", default="passage-planning")
    return p


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON_OBJECT_REQUIRED")
    return payload


def _discover_blueprints(root: Path) -> list[dict]:
    if not root.exists():
        return []
    blueprints: list[dict] = []
    for path in sorted(root.glob("*/lesson_blueprint.json")):
        try:
            payload = _load_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        payload["_artifact_path"] = str(path)
        blueprints.append(payload)
    return blueprints


def _topic_title(blueprints: list[dict], topic_id: str) -> str:
    for blueprint in blueprints:
        candidate_id, title = classify_blueprint_topic(blueprint)
        if candidate_id == topic_id:
            return title
    return topic_id.replace("-", " ").title()


def _write_authority(review: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "authority_review.json"
    md_path = out_dir / "authority_review.md"

    json_temp = json_path.with_suffix(".json.tmp")
    json_temp.write_text(
        json.dumps(review, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    json_temp.replace(json_path)

    md_temp = md_path.with_suffix(".md.tmp")
    md_temp.write_text(render_authority_review(review), encoding="utf-8")
    md_temp.replace(md_path)
    return json_path, md_path


def main() -> int:
    args = parser().parse_args()
    blueprints = _discover_blueprints(args.lesson_root)
    print("TOPIC_PACKET_START")
    print(f"lesson_blueprints={len(blueprints)}")
    print(f"topic={args.topic}")
    print("provider_calls=0")

    if not blueprints:
        print("TOPIC_PACKET_FAILED:NO_LESSON_BLUEPRINTS", file=sys.stderr)
        return 1

    title = _topic_title(blueprints, args.topic)
    try:
        packet = build_topic_packet(
            blueprints,
            topic_id=args.topic,
            display_title=title,
        )
        out_dir = args.output_root / args.topic
        packet_json, packet_md = write_topic_packet(packet, output_dir=out_dir)
    except (OSError, ValueError, TopicPacketError) as exc:
        print(
            f"TOPIC_PACKET_FAILED:{type(exc).__name__}:{' '.join(str(exc).split())[:300]}",
            file=sys.stderr,
        )
        return 1

    print(
        f"TOPIC_PACKET_OK topic={packet.topic_id} sources={packet.source_count} "
        f"claims={len(packet.claims)} authority_targets={len(packet.authority_targets)}"
    )
    print(f"topic_json={packet_json}")
    print(f"topic_markdown={packet_md}")

    try:
        review = build_authority_review(
            topic_id=packet.topic_id,
            targets=packet.authority_targets,
        )
        authority_json, authority_md = _write_authority(review, out_dir)
    except AuthorityVerificationError as exc:
        print(f"AUTHORITY_REVIEW_SKIPPED:{exc}")
    else:
        counts = review["counts"]
        print(
            "AUTHORITY_REVIEW_OK "
            f"direct={counts.get('direct_support', 0)} "
            f"partial={counts.get('partial_support', 0)} "
            f"not_applicable={counts.get('not_applicable', 0)} "
            f"unresolved={counts.get('unresolved', 0)}"
        )
        print(f"authority_json={authority_json}")
        print(f"authority_markdown={authority_md}")

    print("TOPIC_PACKET_SUMMARY")
    print("provider_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
