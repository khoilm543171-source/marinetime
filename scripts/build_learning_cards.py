from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.learning.cards import (  # noqa: E402
    LearningCardError,
    _load_json_object,
    build_source_learning_card,
    write_card_artifacts,
)
from marinetime.pilot.queue import list_jobs  # noqa: E402


DEFAULT_EVIDENCE = ROOT / "storage" / "evidence"
DEFAULT_DB = ROOT / "storage" / "marinetime.sqlite3"
DEFAULT_OUTPUT = ROOT / "storage" / "learning" / "source_cards"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Build learner-facing source cards from completed local ALU artifacts."
    )
    p.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE)
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--limit", type=int, default=3)
    return p


def _title_map(db_path: Path) -> dict[str, str]:
    return {job.source_id: job.video_path.stem for job in list_jobs(db_path)}


def _discover(evidence_root: Path) -> list[Path]:
    candidates = []
    if not evidence_root.exists():
        return candidates
    for alu_path in evidence_root.glob("*/alus.json"):
        if (alu_path.parent / "evidence_pack.json").is_file():
            candidates.append(alu_path)
    return sorted(candidates, key=lambda path: path.parent.name)


def _write_index(rows: list[dict[str, str]], output_root: Path) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / "preview_index.md"
    lines = [
        "# Marinetime — Source Learning Card Preview",
        "",
        "Today milestone: learner-facing previews generated from validated ALUs.",
        "",
    ]
    for index, row in enumerate(rows, start=1):
        rel = Path(row["source_id"]) / "learning_card.md"
        lines.extend(
            [
                f"## {index}. {row['title']}",
                "",
                f"- Source: {row['source_id']}",
                f"- Card: {rel.as_posix()}",
                "",
            ]
        )
    if not rows:
        lines.append("_No completed ALU artifacts were available._")
    temp = path.with_suffix(".md.tmp")
    temp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temp.replace(path)
    return path


def main() -> int:
    args = parser().parse_args()
    if args.limit <= 0:
        print("LEARNING_CARD_FAILED:LIMIT_MUST_BE_POSITIVE", file=sys.stderr)
        return 2

    titles = _title_map(args.db)
    candidates = _discover(args.evidence_root)
    selected = candidates[: args.limit]

    built = 0
    failed = 0
    rows: list[dict[str, str]] = []

    print("LEARNING_CARD_PREVIEW_START")
    print(f"completed_alu_artifacts={len(candidates)}")
    print(f"selected={len(selected)}")
    print("provider_calls=0")

    for alu_path in selected:
        source_dir = alu_path.parent
        evidence_path = source_dir / "evidence_pack.json"
        try:
            alu_artifact = _load_json_object(alu_path)
            evidence_pack = _load_json_object(evidence_path)
            source_id = str(evidence_pack.get("source_id") or source_dir.name)
            title = titles.get(source_id, source_id)
            card = build_source_learning_card(
                evidence_pack=evidence_pack,
                alu_artifact=alu_artifact,
                title=title,
            )
            out_dir = args.output_root / source_id
            json_path, md_path = write_card_artifacts(card, output_dir=out_dir)
        except (
            OSError,
            ValueError,
            json.JSONDecodeError,
            LearningCardError,
        ) as exc:
            failed += 1
            print(
                f"LEARNING_CARD_FAILED source={source_dir.name} "
                f"error={type(exc).__name__}:{' '.join(str(exc).split())[:300]}"
            )
            continue

        built += 1
        rows.append({"source_id": card.source_id, "title": card.title})
        print(
            f"LEARNING_CARD_OK source_id={card.source_id} "
            f"educational_items={len(card.educational_items)} "
            f"withheld={card.withheld_items} markdown={md_path} json={json_path}"
        )

    index_path = _write_index(rows, args.output_root)
    print("LEARNING_CARD_PREVIEW_SUMMARY")
    print(f"built={built}")
    print(f"failed={failed}")
    print(f"index={index_path}")
    print("provider_calls=0")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
