from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .blueprint import LessonBlueprint


class LearningCourseError(ValueError):
    """Raised when a full learner-facing course catalog cannot be built safely."""


@dataclass(frozen=True)
class CourseLesson:
    source_id: str
    display_title: str
    track_id: str
    track_title: str
    lesson_path: str
    learning_objectives: int
    retrieval_questions: int
    key_items: int
    safety_critical_items: int
    numeric_items: int
    authority_targets: int


@dataclass(frozen=True)
class LearningCourse:
    schema_version: str
    course_id: str
    title: str
    source_lessons: tuple[CourseLesson, ...]
    educational_alu_items: int
    withheld_alu_items: int
    source_cards_built: int
    sources_without_lesson: tuple[str, ...]
    missing_alu_sources: tuple[str, ...]


_TRACKS = (
    (
        "safety-regulation",
        "Safety, Regulation & Emergency",
        (
            "solas",
            "marpol",
            "stcw",
            "ism",
            "port state",
            "psc",
            "safety",
            "emergency",
            "enclosed space",
            "fire",
            "lifeboat",
            "pollution",
            "drill",
        ),
    ),
    (
        "navigation",
        "Navigation & Bridge Operations",
        (
            "passage planning",
            "navigation",
            "bridge",
            "radar",
            "ecdis",
            "chart",
            "voyage",
            "position fixing",
            "position-fixing",
            "colreg",
            "collision",
            "vhf",
            "route",
            "appraisal",
            "monitoring",
        ),
    ),
    (
        "engine-machinery",
        "Engine Room & Machinery",
        (
            "engine",
            "machinery",
            "pump",
            "purifier",
            "separator",
            "boiler",
            "compressor",
            "generator",
            "fuel oil",
            "lube oil",
            "lubricating",
            "cooling",
            "valve",
            "bearing",
            "piston",
            "crankshaft",
            "turbocharger",
            "diesel",
            "scavenge",
        ),
    ),
    (
        "watchkeeping-operations",
        "Watchkeeping & Shipboard Operations",
        (
            "watchkeeping",
            "watch keeping",
            "watch",
            "handover",
            "rounds",
            "bunker",
            "bunkering",
            "alarm",
            "checklist",
            "standing order",
            "permit to work",
            "shipboard operation",
        ),
    ),
    (
        "technical-english",
        "Technical English & Communication",
        (
            "english",
            "pronunciation",
            "communication",
            "speaking",
            "listening",
            "sentence",
            "phrase",
            "radio communication",
            "reporting",
        ),
    ),
    (
        "career-practical",
        "Career, Interview & Onboard Practice",
        (
            "interview",
            "cadet",
            "career",
            "seafarer",
            "onboard experience",
            "on board",
            "joining ship",
        ),
    ),
)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def classify_course_track(blueprint: LessonBlueprint) -> tuple[str, str]:
    haystack = _normalize(
        " ".join(
            [
                blueprint.display_title,
                blueprint.original_title,
                " ".join(
                    str(item.get("statement") or "")
                    for item in blueprint.key_items
                    if isinstance(item, dict)
                ),
            ]
        )
    )
    for track_id, track_title, keywords in _TRACKS:
        if any(keyword in haystack for keyword in keywords):
            return track_id, track_title
    return "general-marine", "General Marine Knowledge"


def build_learning_course(
    *,
    blueprints: Iterable[LessonBlueprint],
    source_cards_built: int,
    educational_alu_items: int,
    withheld_alu_items: int,
    sources_without_lesson: Iterable[str] = (),
    missing_alu_sources: Iterable[str] = (),
    course_id: str = "marinetime-core-v1",
    title: str = "Marinetime Core Learning Course",
) -> LearningCourse:
    if source_cards_built < 0 or educational_alu_items < 0 or withheld_alu_items < 0:
        raise LearningCourseError("NEGATIVE_COURSE_COUNT")

    lessons: list[CourseLesson] = []
    seen_sources: set[str] = set()
    for blueprint in blueprints:
        if blueprint.source_id in seen_sources:
            raise LearningCourseError(f"DUPLICATE_SOURCE_LESSON:{blueprint.source_id}")
        seen_sources.add(blueprint.source_id)
        track_id, track_title = classify_course_track(blueprint)
        safety_count = sum(
            1 for item in blueprint.key_items if bool(item.get("safety_critical"))
        )
        numeric_count = sum(
            1 for item in blueprint.key_items if bool(item.get("numeric_claim"))
        )
        lessons.append(
            CourseLesson(
                source_id=blueprint.source_id,
                display_title=blueprint.display_title,
                track_id=track_id,
                track_title=track_title,
                lesson_path=f"lessons/{blueprint.source_id}/lesson_preview.md",
                learning_objectives=len(blueprint.learning_objectives),
                retrieval_questions=len(blueprint.quick_check),
                key_items=len(blueprint.key_items),
                safety_critical_items=safety_count,
                numeric_items=numeric_count,
                authority_targets=len(blueprint.authority_targets),
            )
        )

    lessons.sort(
        key=lambda item: (
            next(
                (
                    index
                    for index, (track_id, _, _) in enumerate(_TRACKS)
                    if track_id == item.track_id
                ),
                len(_TRACKS),
            ),
            item.display_title.lower(),
            item.source_id,
        )
    )

    return LearningCourse(
        schema_version="1.0",
        course_id=course_id,
        title=title,
        source_lessons=tuple(lessons),
        educational_alu_items=educational_alu_items,
        withheld_alu_items=withheld_alu_items,
        source_cards_built=source_cards_built,
        sources_without_lesson=tuple(sorted(set(sources_without_lesson))),
        missing_alu_sources=tuple(sorted(set(missing_alu_sources))),
    )


def course_to_json(course: LearningCourse) -> dict[str, Any]:
    tracks: dict[str, dict[str, Any]] = {}
    for lesson in course.source_lessons:
        entry = tracks.setdefault(
            lesson.track_id,
            {
                "track_id": lesson.track_id,
                "title": lesson.track_title,
                "lesson_count": 0,
                "lessons": [],
            },
        )
        entry["lesson_count"] += 1
        entry["lessons"].append(
            {
                "source_id": lesson.source_id,
                "display_title": lesson.display_title,
                "lesson_path": lesson.lesson_path,
                "learning_objectives": lesson.learning_objectives,
                "retrieval_questions": lesson.retrieval_questions,
                "key_items": lesson.key_items,
                "safety_critical_items": lesson.safety_critical_items,
                "numeric_items": lesson.numeric_items,
                "authority_targets": lesson.authority_targets,
            }
        )

    return {
        "schema_version": course.schema_version,
        "artifact_type": "learner_course_catalog",
        "course_id": course.course_id,
        "title": course.title,
        "source_cards_built": course.source_cards_built,
        "source_lessons_built": len(course.source_lessons),
        "educational_alu_items": course.educational_alu_items,
        "withheld_alu_items": course.withheld_alu_items,
        "sources_without_lesson": list(course.sources_without_lesson),
        "missing_alu_sources": list(course.missing_alu_sources),
        "tracks": list(tracks.values()),
        "scope_note": (
            "This course is a source-grounded learning layer. Creator experience remains "
            "creator experience until an authority review upgrades the support. Course "
            "classification is deterministic and provisional; it is for navigation, not "
            "evidence authority."
        ),
    }


def render_course_markdown(course: LearningCourse) -> str:
    payload = course_to_json(course)
    lines = [
        f"# {course.title}",
        "",
        "> Evidence-first learner course generated from validated Marinetime ALUs.",
        "",
        "## Course status",
        "",
        f"- Source cards: **{course.source_cards_built}**",
        f"- Learner lessons: **{len(course.source_lessons)}**",
        f"- Education-approved ALU items represented: **{course.educational_alu_items}**",
        f"- ALU items withheld by education gates: **{course.withheld_alu_items}**",
        f"- Sources still missing ALU: **{len(course.missing_alu_sources)}**",
        f"- Sources with ALU but no teachable lesson: **{len(course.sources_without_lesson)}**",
        "",
        "## How to use this course",
        "",
        "1. Open one lesson and read the mental model before expanding evidence.",
        "2. Close the lesson and answer its retrieval questions from memory.",
        "3. Give the oral answer out loud instead of silently rereading.",
        "4. Treat safety-critical or numeric creator claims as learning material, not operational permission, until authority review is attached.",
        "5. Record assessment evidence in Marinetime so mastery can move from Seen → Understood → Recalled → Explained → Applied → Retained.",
        "",
    ]

    for track in payload["tracks"]:
        lines.extend(
            [
                f"## {track['title']}",
                "",
                f"Lessons: **{track['lesson_count']}**",
                "",
            ]
        )
        for index, lesson in enumerate(track["lessons"], start=1):
            flags: list[str] = []
            if lesson["safety_critical_items"]:
                flags.append(f"safety-critical={lesson['safety_critical_items']}")
            if lesson["numeric_items"]:
                flags.append(f"numeric={lesson['numeric_items']}")
            if lesson["authority_targets"]:
                flags.append(f"authority-queue={lesson['authority_targets']}")
            suffix = f" — {', '.join(flags)}" if flags else ""
            lines.append(
                f"{index}. [{lesson['display_title']}]({lesson['lesson_path']}) "
                f"— {lesson['retrieval_questions']} retrieval question(s){suffix}"
            )
        lines.append("")

    if course.sources_without_lesson:
        lines.extend(
            [
                "## Sources withheld from learner lessons",
                "",
                "These completed ALU sources produced no education-approved learner lesson:",
                "",
            ]
        )
        for source_id in course.sources_without_lesson:
            lines.append(f"- {source_id}")
        lines.append("")

    if course.missing_alu_sources:
        lines.extend(["## Deferred sources", ""])
        for source_id in course.missing_alu_sources:
            lines.append(f"- {source_id} — ALU unavailable; not silently substituted.")
        lines.append("")

    lines.extend(
        [
            "## Trust boundary",
            "",
            "- Every learner lesson is derived from an ALU that passed the existing education gate.",
            "- Evidence anchors remain available inside each lesson.",
            "- Track labels are navigation aids only and do not change provenance or verification status.",
            "- No generated lesson counts as mastery; only learner evidence changes ownership state.",
            "",
        ]
    )
    return "\n".join(lines)


def write_course_artifacts(
    course: LearningCourse,
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "course_catalog.json"
    md_path = root / "COURSE.md"

    json_tmp = json_path.with_suffix(".json.tmp")
    json_tmp.write_text(
        json.dumps(course_to_json(course), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    json_tmp.replace(json_path)

    md_tmp = md_path.with_suffix(".md.tmp")
    md_tmp.write_text(render_course_markdown(course), encoding="utf-8")
    md_tmp.replace(md_path)
    return json_path, md_path
