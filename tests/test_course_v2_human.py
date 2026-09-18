from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.learning.course_qa import (
    validate_course_markdown,
    validate_lesson_markdown,
)
from marinetime.learning.humanize import (
    glossary_for_texts,
    vietnamese_explanation,
    vietnamese_source_excerpt,
)


class HumanCourseV2Tests(unittest.TestCase):
    def test_vietnamese_source_excerpt_prefers_real_vietnamese_evidence(self) -> None:
        anchors = (
            "SEG-001 · transcript 00:00–00:12 · Trước khi lập tuyến phải thu thập đủ thông tin chuyến đi.",
        )
        excerpt = vietnamese_source_excerpt(anchors)
        self.assertIsNotNone(excerpt)
        self.assertIn("thu thập đủ thông tin", excerpt or "")

    def test_passage_planning_explanation_is_human_and_grounded(self) -> None:
        item = {
            "statement": (
                "The creator states that passage planning consists of four stages: "
                "appraisal, planning, execution, and monitoring."
            )
        }
        text = vietnamese_explanation(
            item,
            heading="Four-stage framework",
            anchors=(),
        )
        self.assertIn("4 giai đoạn", text)
        self.assertIn("Appraisal → Planning → Execution → Monitoring", text)

    def test_glossary_keeps_english_and_explains_vietnamese(self) -> None:
        glossary = dict(
            glossary_for_texts(
                ["Passage planning uses ECDIS, radar and position fixing."]
            )
        )
        self.assertIn("passage planning", glossary)
        self.assertIn("ECDIS", glossary)
        self.assertIn("radar", glossary)
        self.assertIn("position fixing", glossary)

    def test_lesson_qa_rejects_machine_facing_stub(self) -> None:
        report = validate_lesson_markdown(
            "# Lesson\n\nALU-001 support_level=directly_supported"
        )
        self.assertFalse(report.passed)

    def test_lesson_qa_accepts_human_structure(self) -> None:
        text = """# Bài học

## Bạn sẽ học gì / What you will learn
- Hiểu ý chính.

## Học bài này trong 10–15 phút
1. Đọc.

**English technical point**
Pump moves liquid.

**Giải thích tiếng Việt**
Bơm dùng để chuyển chất lỏng theo nội dung nguồn.

## Tự kiểm tra / Retrieval practice
- Tự nói lại.

## Oral practice / Luyện nói
Nói thành tiếng.

<details>
<summary>Evidence / Nguồn gốc của ý này</summary>
Nguồn
</details>
"""
        report = validate_lesson_markdown(text)
        self.assertTrue(report.passed)

    def test_course_qa_accepts_human_home(self) -> None:
        text = """# Marinetime

Tiếng Việt dùng để giải thích; English để học thuật ngữ.

## Bắt đầu ở đây
Học một bài.

## Learning path / Lộ trình
Buồng máy.

## Cách biết mình đã học thật
Tự nhớ lại kiến thức.
"""
        report = validate_course_markdown(text)
        self.assertTrue(report.passed)


if __name__ == "__main__":
    unittest.main()
