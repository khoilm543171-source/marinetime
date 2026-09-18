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
        "An toàn, Quy định & Ứng phó sự cố / Safety, Regulation & Emergency",
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
        "Hàng hải & Buồng lái / Navigation & Bridge Operations",
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
        "Buồng máy & Máy móc / Engine Room & Machinery",
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
        "Trực ca & Vận hành trên tàu / Watchkeeping & Shipboard Operations",
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
        "Tiếng Anh kỹ thuật & Giao tiếp / Technical English & Communication",
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
        "Phỏng vấn, Cadet & Kinh nghiệm đi tàu / Career, Interview & Onboard Practice",
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
    return "general-marine", "Kiến thức hàng hải tổng hợp / General Marine Knowledge"


def build_learning_course(
    *,
    blueprints: Iterable[LessonBlueprint],
    source_cards_built: int,
    educational_alu_items: int,
    withheld_alu_items: int,
    sources_without_lesson: Iterable[str] = (),
    missing_alu_sources: Iterable[str] = (),
    course_id: str = "marinetime-core-v2",
    title: str = "Marinetime — Khóa học hàng hải thực chiến / Practical Maritime Learning",
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
                lesson_path=f"lessons/{blueprint.source_id}/LESSON.md",
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
        schema_version="2.0",
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
            "Learner-facing Course V2. Vietnamese is the explanation language; English is "
            "kept for maritime terminology and interview practice. Evidence/provenance data "
            "remain available behind each lesson and do not become operational permission."
        ),
    }


def render_course_markdown(course: LearningCourse) -> str:
    """Render a human course home page, not an engineering status report."""
    payload = course_to_json(course)
    lines = [
        f"# {course.title}",
        "",
        "> Đây là **khóa học để học**, không phải dashboard kỹ thuật. "
        "Tiếng Việt dùng để giải thích; English được giữ lại để học thuật ngữ, đi tàu và phỏng vấn.",
        "",
        "## Bắt đầu ở đây",
        "",
        "Mỗi bài học theo một nhịp cố định:",
        "",
        "1. **Hiểu** — đọc giải thích tiếng Việt và nhìn thuật ngữ English đi kèm.",
        "2. **Nhớ** — đóng bài và trả lời câu hỏi retrieval bằng trí nhớ.",
        "3. **Nói** — trả lời oral practice thành tiếng như đang nói với sĩ quan/phỏng vấn.",
        "4. **Kiểm tra nguồn khi cần** — evidence và thông tin authority nằm trong phần thu gọn cuối bài.",
        "",
        "Đừng cố đọc hết course một lượt. Học **một bài → tự trả lời → nghỉ → quay lại review**.",
        "",
        "## Learning path / Lộ trình",
        "",
    ]

    for track in payload["tracks"]:
        lines.extend(
            [
                f"### {track['title']}",
                "",
                f"**{track['lesson_count']} bài**",
                "",
            ]
        )
        for index, lesson in enumerate(track["lessons"], start=1):
            note = ""
            if lesson["safety_critical_items"] or lesson["numeric_items"]:
                note = " · ⚠️ có nội dung cần đối chiếu trước khi áp dụng thực tế"
            lines.append(
                f"{index}. [{lesson['display_title']}]({lesson['lesson_path']})"
                f" · {lesson['retrieval_questions']} câu tự kiểm tra{note}"
            )
        lines.append("")

    if course.sources_without_lesson or course.missing_alu_sources:
        lines.extend(
            [
                "## Chưa đưa vào khóa học",
                "",
                "Marinetime không tự bịa bài học để lấp chỗ trống:",
                "",
            ]
        )
        for source_id in course.sources_without_lesson:
            lines.append(f"- {source_id} — chưa có learning item đủ điều kiện.")
        for source_id in course.missing_alu_sources:
            lines.append(f"- {source_id} — chưa có ALU, nên chưa tạo lesson.")
        lines.append("")

    lines.extend(
        [
            "## Cách biết mình đã học thật",
            "",
            "Một bài không được tính là 'đã biết' chỉ vì bạn đã đọc xong.",
            "",
            "**Seen → Understood → Recalled → Explained → Applied → Retained**",
            "",
            "Marinetime chỉ nâng mức sở hữu kiến thức khi có bằng chứng học tập: "
            "tự nhớ lại, giải thích thành tiếng, xử lý tình huống và nhớ lại sau một khoảng thời gian.",
            "",
            "<details>",
            "<summary>Thông tin hệ thống / Data & provenance — không cần đọc để học course</summary>",
            "",
            f"- Source cards: {course.source_cards_built}",
            f"- Learner lessons: {len(course.source_lessons)}",
            f"- Education-approved ALU items: {course.educational_alu_items}",
            f"- ALU items withheld by gates: {course.withheld_alu_items}",
            f"- Missing-ALU sources: {len(course.missing_alu_sources)}",
            f"- Sources without learner lesson: {len(course.sources_without_lesson)}",
            "",
            "Track labels chỉ để điều hướng. Chúng không thay đổi provenance, authority hay safety status.",
            "",
            "</details>",
            "",
        ]
    )
    return "\\n".join(lines)


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
