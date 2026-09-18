from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.learning.blueprint import (  # noqa: E402
    LessonBlueprintError,
    build_lesson_blueprint,
    write_lesson_preview,
)
from marinetime.learning.cards import (  # noqa: E402
    LearningCardError,
    _load_json_object,
    build_source_learning_card,
    write_card_artifacts,
)
from marinetime.learning.course import (  # noqa: E402
    build_learning_course,
    write_course_artifacts,
)
from marinetime.learning.course_qa import (  # noqa: E402
    HumanCourseQAError,
    assert_human_artifact,
)
from marinetime.pilot.queue import list_jobs  # noqa: E402


DEFAULT_EVIDENCE = ROOT / "storage" / "evidence"
DEFAULT_DB = ROOT / "storage" / "marinetime.sqlite3"
DEFAULT_OUTPUT = ROOT / "storage" / "learning" / "course_v2"
DEFAULT_EXPORT = ROOT / "storage" / "exports" / "marinetime_course_v2.zip"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Build the human-first bilingual Course V2 from every completed ALU artifact. "
            "Vietnamese explains; English preserves maritime terminology. Provider calls: 0."
        )
    )
    p.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE)
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--export", type=Path, default=DEFAULT_EXPORT)
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional test/debug limit. Omit to build every completed ALU source.",
    )
    return p


def _title_map(db_path: Path) -> dict[str, str]:
    if not db_path.is_file():
        return {}
    return {job.source_id: job.video_path.stem for job in list_jobs(db_path)}


def _discover(evidence_root: Path) -> tuple[list[Path], list[str]]:
    completed: list[Path] = []
    missing: list[str] = []
    if not evidence_root.exists():
        return completed, missing

    for evidence_path in sorted(evidence_root.glob("*/evidence_pack.json")):
        source_id = evidence_path.parent.name
        alu_path = evidence_path.parent / "alus.json"
        if alu_path.is_file():
            completed.append(alu_path)
        else:
            missing.append(source_id)
    return completed, missing


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _zip_tree(root: Path, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(root).as_posix())
    tmp.replace(out)


def main() -> int:
    args = parser().parse_args()
    if args.limit is not None and args.limit <= 0:
        print("LEARNING_COURSE_FAILED:LIMIT_MUST_BE_POSITIVE", file=sys.stderr)
        return 2

    candidates, missing_alus = _discover(args.evidence_root)
    if args.limit is not None:
        candidates = candidates[: args.limit]

    if not candidates:
        print("LEARNING_COURSE_FAILED:NO_COMPLETED_ALUS", file=sys.stderr)
        return 2

    titles = _title_map(args.db)
    staging = args.output_root.with_name(args.output_root.name + ".tmp-build")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    source_cards = staging / "source_cards"
    lessons_root = staging / "lessons"
    course_root = staging / "course"

    blueprints = []
    source_cards_built = 0
    educational_items = 0
    withheld_items = 0
    sources_without_lesson: list[str] = []
    build_rows: list[dict[str, object]] = []

    print("FULL_LEARNING_COURSE_V2_START")
    print(f"completed_alu_artifacts={len(candidates)}")
    print(f"missing_alus={len(missing_alus)}")
    print("provider_calls=0")

    try:
        for index, alu_path in enumerate(candidates, start=1):
            source_dir = alu_path.parent
            evidence_path = source_dir / "evidence_pack.json"
            alu_artifact = _load_json_object(alu_path)
            evidence_pack = _load_json_object(evidence_path)
            source_id = str(evidence_pack.get("source_id") or source_dir.name)
            title = titles.get(source_id, source_id)

            card = build_source_learning_card(
                evidence_pack=evidence_pack,
                alu_artifact=alu_artifact,
                title=title,
            )
            write_card_artifacts(card, output_dir=source_cards / source_id)
            source_cards_built += 1
            educational_items += len(card.educational_items)
            withheld_items += card.withheld_items

            lesson_status = "BUILT"
            if card.educational_items:
                blueprint = build_lesson_blueprint(card)
                _, lesson_md = write_lesson_preview(
                    blueprint,
                    evidence_anchors=card.evidence_anchors,
                    output_dir=lessons_root / source_id,
                )
                assert_human_artifact(lesson_md, kind="LESSON")
                blueprints.append(blueprint)
            else:
                lesson_status = "WITHHELD_NO_EDUCATIONAL_ITEMS"
                sources_without_lesson.append(source_id)

            build_rows.append(
                {
                    "source_id": source_id,
                    "education_items": len(card.educational_items),
                    "withheld_items": card.withheld_items,
                    "lesson_status": lesson_status,
                }
            )
            print(
                f"COURSE_SOURCE_OK index={index}/{len(candidates)} "
                f"source_id={source_id} educational={len(card.educational_items)} "
                f"withheld={card.withheld_items} lesson={lesson_status}"
            )

        course = build_learning_course(
            blueprints=blueprints,
            source_cards_built=source_cards_built,
            educational_alu_items=educational_items,
            withheld_alu_items=withheld_items,
            sources_without_lesson=sources_without_lesson,
            missing_alu_sources=missing_alus,
        )
        catalog_json, course_md = write_course_artifacts(
            course,
            output_dir=course_root,
        )
        assert_human_artifact(course_md, kind="COURSE")

        manifest = {
            "schema_version": "2.0",
            "artifact_type": "learning_course_build_manifest",
            "provider_calls": 0,
            "human_course_qa": "passed",
            "source_cards_built": source_cards_built,
            "source_lessons_built": len(blueprints),
            "educational_alu_items": educational_items,
            "withheld_alu_items": withheld_items,
            "sources_without_lesson": sorted(sources_without_lesson),
            "missing_alu_sources": sorted(missing_alus),
            "sources": build_rows,
        }
        manifest_path = staging / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if args.output_root.exists():
            shutil.rmtree(args.output_root)
        staging.replace(args.output_root)

        _zip_tree(args.output_root, args.export)
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        LearningCardError,
        LessonBlueprintError,
        HumanCourseQAError,
    ) as exc:
        if staging.exists():
            shutil.rmtree(staging)
        print(
            f"LEARNING_COURSE_FAILED:{type(exc).__name__}:"
            f"{' '.join(str(exc).split())[:500]}",
            file=sys.stderr,
        )
        return 1

    print("FULL_LEARNING_COURSE_V2_OK")
    print(f"source_cards={source_cards_built}")
    print(f"source_lessons={len(blueprints)}")
    print(f"educational_alu_items={educational_items}")
    print(f"withheld_alu_items={withheld_items}")
    print(f"sources_without_lesson={len(sources_without_lesson)}")
    print(f"missing_alus={len(missing_alus)}")
    print(f"course_markdown={args.output_root / 'course' / 'COURSE.md'}")
    print(f"course_catalog={args.output_root / 'course' / 'course_catalog.json'}")
    print(f"course_zip={args.export}")
    print(f"course_zip_sha256={_sha256(args.export)}")
    print(f"course_zip_bytes={args.export.stat().st_size}")
    print("provider_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
