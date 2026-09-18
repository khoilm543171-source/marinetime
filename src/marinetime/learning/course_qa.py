from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .humanize import contains_vietnamese


class HumanCourseQAError(ValueError):
    """Raised when a learner-facing artifact regresses into machine-facing output."""


@dataclass(frozen=True)
class HumanCourseQA:
    passed: bool
    checks: tuple[tuple[str, bool], ...]


_LESSON_REQUIRED = (
    "## Bạn sẽ học gì / What you will learn",
    "## Học bài này trong 10–15 phút",
    "**English technical point**",
    "**Giải thích tiếng Việt**",
    "## Tự kiểm tra / Retrieval practice",
    "## Oral practice / Luyện nói",
    "<summary>Evidence / Nguồn gốc của ý này</summary>",
)

_COURSE_REQUIRED = (
    "## Bắt đầu ở đây",
    "## Learning path / Lộ trình",
    "Tiếng Việt dùng để giải thích",
    "## Cách biết mình đã học thật",
)


def _qa(text: str, required: tuple[str, ...], *, kind: str) -> HumanCourseQA:
    checks: list[tuple[str, bool]] = []
    checks.append((f"{kind}:HAS_VIETNAMESE", contains_vietnamese(text)))
    for marker in required:
        checks.append((f"{kind}:MARKER:{marker}", marker in text))

    if kind == "LESSON":
        # The visible lesson should not start as an internal artifact dump.
        first_chunk = text.split(
            "<details>\n<summary>Thông tin kiểm chứng kỹ thuật", 1
        )[0]
        checks.append(("LESSON:NO_VISIBLE_INTERNAL_AUTHORITY_TARGETS", "Internal authority targets:" not in first_chunk))
        checks.append(("LESSON:NO_VISIBLE_RAW_ALU_HEADING", "### ALU-" not in first_chunk))

    return HumanCourseQA(
        passed=all(passed for _, passed in checks),
        checks=tuple(checks),
    )


def validate_lesson_markdown(text: str) -> HumanCourseQA:
    return _qa(text, _LESSON_REQUIRED, kind="LESSON")


def validate_course_markdown(text: str) -> HumanCourseQA:
    return _qa(text, _COURSE_REQUIRED, kind="COURSE")


def assert_human_artifact(path: str | Path, *, kind: str) -> None:
    text = Path(path).read_text(encoding="utf-8")
    if kind == "LESSON":
        report = validate_lesson_markdown(text)
    elif kind == "COURSE":
        report = validate_course_markdown(text)
    else:
        raise ValueError(f"UNKNOWN_HUMAN_COURSE_QA_KIND:{kind}")

    if not report.passed:
        failed = [name for name, passed in report.checks if not passed]
        raise HumanCourseQAError(
            "HUMAN_COURSE_QA_FAILED:" + ",".join(failed)
        )
