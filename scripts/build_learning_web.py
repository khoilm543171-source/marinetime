from __future__ import annotations

import argparse
import json
import shutil
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.learning.blueprint import _item_heading  # noqa: E402
from marinetime.learning.humanize import (  # noqa: E402
    vietnamese_explanation,
    vietnamese_heading,
)

DEFAULT_COURSE_ROOT = ROOT / "storage" / "learning" / "course_v2"
DEFAULT_OUTPUT_ROOT = ROOT / "storage" / "learning" / "web"
TEMPLATE_ROOT = ROOT / "web" / "learning"


class LearningWebError(ValueError):
    """Raised when the learner web bundle cannot be built safely."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LearningWebError(f"MISSING_ARTIFACT:{path}") from exc
    except json.JSONDecodeError as exc:
        raise LearningWebError(f"INVALID_JSON:{path}") from exc
    if not isinstance(payload, dict):
        raise LearningWebError(f"JSON_OBJECT_REQUIRED:{path}")
    return payload


def _module_lookup(track: dict[str, Any]) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    for module in track.get("modules") or []:
        if not isinstance(module, dict):
            continue
        module_id = str(module.get("module_id") or "")
        title = str(module.get("title") or "")
        description = str(module.get("description") or "")
        for lesson in module.get("lessons") or []:
            if not isinstance(lesson, dict):
                continue
            source_id = lesson.get("source_id")
            if isinstance(source_id, str) and source_id:
                lookup[source_id] = {
                    "module_id": module_id,
                    "module_title": title,
                    "module_description": description,
                }
    return lookup


def build_payload(course_root: Path) -> dict[str, Any]:
    catalog = _load_json(course_root / "course" / "course_catalog.json")
    if catalog.get("artifact_type") != "learner_course_catalog":
        raise LearningWebError("COURSE_CATALOG_TYPE_MISMATCH")

    tracks_out: list[dict[str, Any]] = []
    sessions: dict[str, dict[str, Any]] = {}

    tracks = catalog.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        raise LearningWebError("COURSE_HAS_NO_TRACKS")

    for track in tracks:
        if not isinstance(track, dict):
            raise LearningWebError("TRACK_NOT_OBJECT")
        track_id = str(track.get("track_id") or "")
        track_title = str(track.get("title") or track_id)
        modules = _module_lookup(track)
        session_refs: list[dict[str, Any]] = []

        lessons = track.get("lessons")
        if not isinstance(lessons, list):
            raise LearningWebError(f"TRACK_LESSONS_INVALID:{track_id}")

        for index, lesson in enumerate(lessons, start=1):
            if not isinstance(lesson, dict):
                raise LearningWebError(f"LESSON_REF_INVALID:{track_id}:{index}")
            source_id = str(lesson.get("source_id") or "")
            if not source_id:
                raise LearningWebError(f"LESSON_SOURCE_ID_MISSING:{track_id}:{index}")

            blueprint = _load_json(
                course_root / "lessons" / source_id / "lesson_blueprint.json"
            )
            card = _load_json(
                course_root / "source_cards" / source_id / "learning_card.json"
            )
            if blueprint.get("source_id") != source_id:
                raise LearningWebError(f"BLUEPRINT_SOURCE_MISMATCH:{source_id}")
            if card.get("source_id") != source_id:
                raise LearningWebError(f"CARD_SOURCE_MISMATCH:{source_id}")

            evidence_anchors = card.get("evidence_anchors")
            if not isinstance(evidence_anchors, dict):
                evidence_anchors = {}

            key_items_out: list[dict[str, Any]] = []
            for item in blueprint.get("key_items") or []:
                if not isinstance(item, dict):
                    continue
                alu_id = str(item.get("alu_id") or "")
                anchors = evidence_anchors.get(alu_id) or []
                if not isinstance(anchors, list):
                    anchors = []
                heading = _item_heading(item)
                key_items_out.append(
                    {
                        **item,
                        "heading": heading,
                        "heading_vi": vietnamese_heading(heading),
                        "explanation_vi": vietnamese_explanation(
                            item,
                            heading=heading,
                            anchors=tuple(str(value) for value in anchors),
                        ),
                        "evidence": [str(value) for value in anchors],
                    }
                )

            module = modules.get(
                source_id,
                {
                    "module_id": f"{track_id}-foundations",
                    "module_title": "Nền tảng / Foundations",
                    "module_description": "",
                },
            )
            display_title = str(
                blueprint.get("display_title")
                or lesson.get("display_title")
                or source_id
            )

            session = {
                "source_id": source_id,
                "display_title": display_title,
                "original_title": str(blueprint.get("original_title") or ""),
                "track_id": track_id,
                "track_title": track_title,
                **module,
                "provenance_class": blueprint.get("provenance_class"),
                "learning_objectives": blueprint.get("learning_objectives") or [],
                "mental_model": blueprint.get("mental_model") or [],
                "key_items": key_items_out,
                "quick_check": blueprint.get("quick_check") or [],
                "oral_exam_prompt": str(blueprint.get("oral_exam_prompt") or ""),
                "warnings": blueprint.get("warnings") or [],
                "authoritative_verification_required": bool(
                    blueprint.get("authoritative_verification_required")
                ),
                "authority_targets": blueprint.get("authority_targets") or [],
                "safety_critical_items": int(
                    lesson.get("safety_critical_items") or 0
                ),
                "numeric_items": int(lesson.get("numeric_items") or 0),
                "withheld_items": int(card.get("withheld_items") or 0),
            }
            sessions[source_id] = session
            session_refs.append(
                {
                    "source_id": source_id,
                    "display_title": display_title,
                    "module_id": module["module_id"],
                    "module_title": module["module_title"],
                    "safety_critical_items": session["safety_critical_items"],
                    "numeric_items": session["numeric_items"],
                }
            )

        tracks_out.append(
            {
                "track_id": track_id,
                "title": track_title,
                "lesson_count": len(session_refs),
                "sessions": session_refs,
            }
        )

    return {
        "schema_version": "1.0",
        "artifact_type": "marinetime_learning_web_payload",
        "course": {
            "course_id": catalog.get("course_id"),
            "title": catalog.get("title"),
            "source_lessons_built": catalog.get("source_lessons_built"),
            "educational_alu_items": catalog.get("educational_alu_items"),
            "withheld_alu_items": catalog.get("withheld_alu_items"),
            "missing_alu_sources": catalog.get("missing_alu_sources") or [],
        },
        "tracks": tracks_out,
        "sessions": sessions,
    }


def write_bundle(
    *,
    course_root: Path,
    output_root: Path,
    template_root: Path = TEMPLATE_ROOT,
) -> Path:
    if not template_root.is_dir():
        raise LearningWebError(f"TEMPLATE_ROOT_NOT_FOUND:{template_root}")

    payload = build_payload(course_root)
    output_root.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "app.js", "styles.css"):
        source = template_root / name
        if not source.is_file():
            raise LearningWebError(f"TEMPLATE_NOT_FOUND:{source}")
        shutil.copy2(source, output_root / name)

    data_dir = output_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    data_path = data_dir / "course.json"
    temp = data_path.with_suffix(".json.tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(data_path)
    return data_path


def _serve(output_root: Path, port: int) -> None:
    handler = lambda *args, **kwargs: SimpleHTTPRequestHandler(
        *args,
        directory=str(output_root),
        **kwargs,
    )
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"LEARNING_WEB_SERVING=http://127.0.0.1:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Build a human-first local Marinetime learning website from Course V2 "
            "artifacts. Provider calls: 0."
        )
    )
    p.add_argument("--course-root", type=Path, default=DEFAULT_COURSE_ROOT)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    p.add_argument("--serve", action="store_true")
    p.add_argument("--port", type=int, default=8765)
    return p


def main() -> int:
    args = parser().parse_args()
    if args.port <= 0 or args.port > 65535:
        print("LEARNING_WEB_FAILED:INVALID_PORT", file=sys.stderr)
        return 2

    try:
        data_path = write_bundle(
            course_root=args.course_root,
            output_root=args.output_root,
        )
    except (OSError, LearningWebError) as exc:
        print(f"LEARNING_WEB_FAILED:{exc}", file=sys.stderr)
        print(
            "Hint: build Course V2 first with "
            "python scripts/build_full_learning_course.py",
            file=sys.stderr,
        )
        return 1

    payload = _load_json(data_path)
    print("LEARNING_WEB_OK")
    print(f"tracks={len(payload['tracks'])}")
    print(f"sessions={len(payload['sessions'])}")
    print(f"output={args.output_root / 'index.html'}")
    print("provider_calls=0")

    if args.serve:
        _serve(args.output_root, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
