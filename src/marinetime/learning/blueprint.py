from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cards import SourceLearningCard
from .humanize import (
    glossary_for_texts,
    simple_safety_note,
    vietnamese_explanation,
    vietnamese_heading,
)


class LessonBlueprintError(ValueError):
    """Raised when a learner-facing lesson blueprint cannot be built safely."""


@dataclass(frozen=True)
class LearningObjective:
    objective_id: str
    text: str
    alu_ids: tuple[str, ...]


@dataclass(frozen=True)
class LessonBlueprint:
    schema_version: str
    source_id: str
    original_title: str
    display_title: str
    provenance_class: str
    learning_objectives: tuple[LearningObjective, ...]
    key_items: tuple[dict[str, Any], ...]
    mental_model: tuple[str, ...]
    quick_check: tuple[dict[str, str], ...]
    oral_exam_prompt: str
    authority_targets: tuple[str, ...]
    authoritative_verification_required: bool
    warnings: tuple[str, ...]


_TIKTOK_SUFFIX_PATTERNS = (
    re.compile(r"\s+do\s+.+?\s+tạo với bản nhạc\s+.*$", re.IGNORECASE),
    re.compile(r"\s+created with\s+.+?\s+sound\s+.*$", re.IGNORECASE),
)
_CREATOR_PREFIXES = (
    "the creator states that ",
    "the creator reports that ",
    "the creator describes ",
    "the creator recommends ",
    "the creator states ",
    "the creator reports ",
)


def clean_display_title(title: str, *, limit: int = 110) -> str:
    """Remove common platform boilerplate while preserving the original elsewhere."""
    value = " ".join(title.split()).strip(" -")
    for pattern in _TIKTOK_SUFFIX_PATTERNS:
        value = pattern.sub("", value).strip(" -")
    value = re.sub(r"\s{2,}", " ", value)
    if len(value) > limit:
        value = value[: max(0, limit - 1)].rstrip(" -–—,:;") + "…"
    return value or title.strip()


def _plain_claim(statement: str) -> str:
    value = " ".join(statement.split()).strip()
    lower = value.lower()
    for prefix in _CREATOR_PREFIXES:
        if lower.startswith(prefix):
            value = value[len(prefix):].strip()
            break
    if value:
        value = value[0].upper() + value[1:]
    return value


def _is_passage_planning(card: SourceLearningCard) -> bool:
    haystack = " ".join(
        [card.title]
        + [str(item.get("statement", "")) for item in card.educational_items]
    ).lower()
    return (
        "passage planning" in haystack
        and all(word in haystack for word in ("appraisal", "planning", "execution", "monitoring"))
    )


def _find_item(items: tuple[dict[str, Any], ...], *needles: str) -> dict[str, Any] | None:
    for item in items:
        statement = str(item.get("statement", "")).lower()
        if all(needle.lower() in statement for needle in needles):
            return item
    return None


def _item_heading(item: dict[str, Any]) -> str:
    statement = str(item.get("statement", ""))
    lower = statement.lower()
    if "four stages" in lower and "passage planning" in lower:
        return "Four-stage framework"
    if "interview" in lower or "checklist" in lower:
        return "Interview strategy — explain, do not only list"
    if "appraisal" in lower:
        return "Appraisal — gather voyage information"
    if "during planning" in lower or "berth-to-berth" in lower:
        return "Planning — build and validate the route"
    if "during execution" in lower or "approved plan" in lower:
        return "Execution — follow the approved plan"
    if "monitoring" in lower and ("radar" in lower or "visual" in lower):
        return "Monitoring — check progress and cross-check position"
    if "gps" in lower or "position-fixing method" in lower:
        return "Monitoring principle — do not rely on one fixing method"
    plain = _plain_claim(statement)
    if len(plain) > 72:
        plain = plain[:69].rstrip(" ,;:-") + "…"
    return plain


def _passage_profile(
    key_items: tuple[dict[str, Any], ...],
) -> tuple[
    str,
    tuple[LearningObjective, ...],
    tuple[str, ...],
    tuple[dict[str, str], ...],
    str,
]:
    framework = _find_item(key_items, "four stages", "passage planning")
    appraisal = _find_item(key_items, "appraisal", "before")
    if appraisal is None:
        appraisal = _find_item(key_items, "appraisal", "collect")
    planning = _find_item(key_items, "during planning")
    execution = _find_item(key_items, "execution")
    monitoring = _find_item(key_items, "monitoring", "cross-checked")
    if monitoring is None:
        monitoring = _find_item(key_items, "monitoring", "position")

    stage_items = tuple(
        item for item in (appraisal, planning, execution, monitoring) if item is not None
    )
    all_ids = tuple(
        str(item.get("alu_id"))
        for item in ((framework,) if framework else ()) + stage_items
    )

    objectives = (
        LearningObjective(
            "LO-01",
            "Nêu đúng thứ tự 4 giai đoạn passage planning / List the four passage-planning stages in the correct order.",
            (str(framework.get("alu_id")),) if framework else all_ids,
        ),
        LearningObjective(
            "LO-02",
            "Giải thích bằng tiếng Việt việc gì xảy ra ở Appraisal, Planning, Execution và Monitoring; sau đó nói lại các thuật ngữ chính bằng English.",
            tuple(str(item.get("alu_id")) for item in stage_items),
        ),
        LearningObjective(
            "LO-03",
            "Trả lời phỏng vấn 60–90 giây: nêu 4 giai đoạn bằng English và giải thích rõ việc làm trong từng giai đoạn.",
            all_ids,
        ),
    )

    mental_model: list[str] = []
    if appraisal:
        mental_model.append("Appraisal → gather voyage information before drawing the route")
    if planning:
        mental_model.append("Planning → build, check, validate, and discuss the berth-to-berth route")
    if execution:
        mental_model.append("Execution → follow the approved plan after proper discussion")
    if monitoring:
        mental_model.append("Monitoring → check progress against the plan and cross-check position")

    questions: list[dict[str, str]] = []
    if framework:
        questions.append(
            {
                "question_id": "Q-01",
                "prompt": "Không nhìn lại bài: nêu 4 giai đoạn passage planning theo đúng thứ tự, ưu tiên nói tên giai đoạn bằng English.",
                "answer_anchor": str(framework.get("statement", "")),
                "alu_id": str(framework.get("alu_id", "")),
            }
        )
    if appraisal:
        questions.append(
            {
                "question_id": "Q-02",
                "prompt": "Appraisal là gì? Trước khi vẽ tuyến, nguồn nói cần thu thập những thông tin nào? Hãy trả lời bằng tiếng Việt và giữ các thuật ngữ English quan trọng.",
                "answer_anchor": str(appraisal.get("statement", "")),
                "alu_id": str(appraisal.get("alu_id", "")),
            }
        )
    if planning:
        questions.append(
            {
                "question_id": "Q-03",
                "prompt": "Ở Planning, nguồn nói phải làm và kiểm tra gì với tuyến trước khi sử dụng? Trả lời bằng tiếng Việt, dùng đúng thuật ngữ berth-to-berth nếu có.",
                "answer_anchor": str(planning.get("statement", "")),
                "alu_id": str(planning.get("alu_id", "")),
            }
        )
    if execution:
        questions.append(
            {
                "question_id": "Q-04",
                "prompt": "Ở Execution, nguồn nói bridge team làm gì với approved plan?",
                "answer_anchor": str(execution.get("statement", "")),
                "alu_id": str(execution.get("alu_id", "")),
            }
        )
    if monitoring:
        questions.append(
            {
                "question_id": "Q-05",
                "prompt": "Ở Monitoring, vị trí và tiến trình của tàu được theo dõi/cross-check như thế nào theo đúng nội dung nguồn?",
                "answer_anchor": str(monitoring.get("statement", "")),
                "alu_id": str(monitoring.get("alu_id", "")),
            }
        )

    oral = (
        "**Interview question:** How do you make a passage plan?\n\n"
        "**Cách luyện:** trả lời 60–90 giây. Có thể hiểu ý bằng tiếng Việt trước, "
        "nhưng khi nói hãy giữ các thuật ngữ English chính xác.\n\n"
        "1. Name the four stages: Appraisal → Planning → Execution → Monitoring.\n"
        "2. Appraisal — giải thích thông tin cần thu thập trước khi vẽ tuyến.\n"
        "3. Planning — giải thích berth-to-berth route, kiểm tra/validation và thảo luận theo nguồn.\n"
        "4. Execution — giải thích việc thực hiện approved plan.\n"
        "5. Monitoring — giải thích cách theo dõi progress/position và cross-check.\n\n"
        "**Mục tiêu:** người nghe thấy bạn hiểu công việc, không chỉ đọc thuộc 4 cái tên."
    )

    return (
        "Passage Planning — 4 Stages and Interview Answer",
        objectives,
        tuple(mental_model),
        tuple(questions),
        oral,
    )


def _generic_profile(
    card: SourceLearningCard,
    key_items: tuple[dict[str, Any], ...],
) -> tuple[
    str,
    tuple[LearningObjective, ...],
    tuple[str, ...],
    tuple[dict[str, str], ...],
    str,
]:
    objectives: list[LearningObjective] = []
    for index, item in enumerate(key_items[:3], start=1):
        objectives.append(
            LearningObjective(
                objective_id=f"LO-{index:02d}",
                text=(
                    "Giải thích ý này bằng tiếng Việt, sau đó nói lại 1–2 câu English kỹ thuật: "
                    f"{_plain_claim(str(item.get('statement', '')))}"
                ),
                alu_ids=(str(item.get("alu_id")),),
            )
        )

    mental_model = tuple(_item_heading(item) for item in key_items[:5])
    quick_check = tuple(
        {
            "question_id": f"Q-{index:02d}",
            "prompt": (
                "Không nhìn lại bài: giải thích bằng tiếng Việt rồi nói lại thuật ngữ English chính: "
                f"{_item_heading(item)}."
            ),
            "answer_anchor": str(item.get("statement", "")),
            "alu_id": str(item.get("alu_id", "")),
        }
        for index, item in enumerate(key_items[:5], start=1)
    )
    oral = (
        f"Giải thích **{clean_display_title(card.title)}** trong 60–90 giây mà không đọc note. "
        "Bắt đầu bằng ý chính bằng tiếng Việt; sau đó dùng đúng các thuật ngữ English quan trọng "
        "và chỉ nói những gì nguồn/evidence thực sự hỗ trợ."
    )
    return clean_display_title(card.title), tuple(objectives), mental_model, quick_check, oral


def build_lesson_blueprint(card: SourceLearningCard) -> LessonBlueprint:
    if not card.educational_items:
        raise LessonBlueprintError("NO_EDUCATIONAL_ITEMS")

    key_items = tuple(card.educational_items[:8])

    if _is_passage_planning(card):
        display_title, objectives, mental_model, quick_check, oral_exam_prompt = (
            _passage_profile(key_items)
        )
    else:
        display_title, objectives, mental_model, quick_check, oral_exam_prompt = (
            _generic_profile(card, key_items)
        )

    authority_targets = tuple(
        str(item.get("alu_id"))
        for item in key_items
        if (
            card.provenance_class not in {"standard", "maker_manual", "regulatory"}
            or bool(item.get("safety_critical"))
            or bool(item.get("numeric_claim"))
            or item.get("support_level") != "directly_supported"
        )
    )
    authoritative_required = bool(authority_targets)

    return LessonBlueprint(
        schema_version="1.1",
        source_id=card.source_id,
        original_title=card.title,
        display_title=display_title,
        provenance_class=card.provenance_class,
        learning_objectives=objectives,
        key_items=key_items,
        mental_model=mental_model,
        quick_check=quick_check,
        oral_exam_prompt=oral_exam_prompt,
        authority_targets=authority_targets,
        authoritative_verification_required=authoritative_required,
        warnings=card.warnings,
    )


def blueprint_to_json(blueprint: LessonBlueprint) -> dict[str, Any]:
    return {
        "schema_version": blueprint.schema_version,
        "artifact_type": "source_lesson_blueprint_preview",
        "source_id": blueprint.source_id,
        "original_title": blueprint.original_title,
        "display_title": blueprint.display_title,
        "provenance_class": blueprint.provenance_class,
        "learning_objectives": [
            {
                "objective_id": item.objective_id,
                "text": item.text,
                "alu_ids": list(item.alu_ids),
            }
            for item in blueprint.learning_objectives
        ],
        "mental_model": list(blueprint.mental_model),
        "key_items": list(blueprint.key_items),
        "quick_check": list(blueprint.quick_check),
        "oral_exam_prompt": blueprint.oral_exam_prompt,
        "authority_targets": list(blueprint.authority_targets),
        "authoritative_verification_required": blueprint.authoritative_verification_required,
        "warnings": list(blueprint.warnings),
        "scope_note": (
            "Single-source instructional preview. No cross-source synthesis or "
            "authoritative verification has been performed."
        ),
    }


def render_lesson_preview(
    blueprint: LessonBlueprint,
    *,
    evidence_anchors: dict[str, tuple[str, ...]],
) -> str:
    """Render the learner document; machine QA/provenance stays collapsed."""

    lesson_texts = [blueprint.display_title]
    lesson_texts.extend(str(item.get("statement") or "") for item in blueprint.key_items)
    glossary = glossary_for_texts(lesson_texts)
    safety_count = sum(
        1 for item in blueprint.key_items if bool(item.get("safety_critical"))
    )
    numeric_count = sum(
        1 for item in blueprint.key_items if bool(item.get("numeric_claim"))
    )

    lines: list[str] = [
        f"# {blueprint.display_title}",
        "",
        "> **Cách dùng bài này:** hiểu bằng tiếng Việt trước, giữ thuật ngữ kỹ thuật bằng English, "
        "sau đó đóng tài liệu và tự nói lại. Không cần đọc JSON/ALU để học.",
        "",
        "## Bạn sẽ học gì / What you will learn",
        "",
    ]
    for objective in blueprint.learning_objectives:
        lines.append(f"- {objective.text}")

    lines.extend(
        [
            "",
            "## Học bài này trong 10–15 phút",
            "",
            "1. Đọc **Bản đồ ý chính** để biết bài đang nói về cái gì.",
            "2. Với mỗi ý, đọc **English technical point** rồi đọc **Giải thích tiếng Việt**.",
            "3. Đóng phần nội dung và trả lời **Tự kiểm tra** bằng trí nhớ.",
            "4. Nói phần **Oral practice** thành tiếng như đang trả lời sĩ quan/phỏng vấn.",
            "5. Chỉ mở **Evidence / nguồn gốc** khi muốn kiểm tra tại sao Marinetime nói điều đó.",
            "",
            "## Bản đồ ý chính / Mental model",
            "",
        ]
    )
    if blueprint.mental_model:
        for line in blueprint.mental_model:
            lines.append(f"- {line}")
    else:
        lines.append("- Bài này chưa có mental model ngắn; học theo từng ý bên dưới.")

    if glossary:
        lines.extend(["", "## English cần nhớ / Technical vocabulary", ""])
        for english, vietnamese in glossary:
            lines.append(f"- **{english}** → {vietnamese}")

    lines.extend(["", "## Nội dung bài học", ""])
    for index, item in enumerate(blueprint.key_items, start=1):
        heading = _item_heading(item)
        vi_heading = vietnamese_heading(heading)
        anchors = evidence_anchors.get(str(item.get("alu_id")), ())
        vi_explanation = vietnamese_explanation(
            item,
            heading=heading,
            anchors=anchors,
        )
        lines.extend(
            [
                f"### {index}. {vi_heading}",
                "",
                f"**English technical point**  ",
                str(item.get("statement") or "").strip(),
                "",
                "**Giải thích tiếng Việt**  ",
                vi_explanation,
                "",
            ]
        )

        flags: list[str] = []
        if item.get("safety_critical"):
            flags.append("safety-critical")
        if item.get("numeric_claim"):
            flags.append("numeric")
        if flags:
            lines.append(
                "**Khi học ý này:** hiểu nguyên tắc trước; chưa dùng nó như hướng dẫn thao tác thật "
                "cho tới khi đã đối chiếu nguồn có thẩm quyền."
            )
            lines.append("")

        lines.extend(
            [
                "<details>",
                "<summary>Evidence / Nguồn gốc của ý này</summary>",
                "",
            ]
        )
        if anchors:
            for anchor in anchors:
                lines.append(f"- {anchor}")
        else:
            lines.append("- Không có evidence anchor khả dụng.")
        lines.extend(["", "</details>", ""])

    notes = simple_safety_note(
        safety_count=safety_count,
        numeric_count=numeric_count,
    )
    if notes:
        lines.extend(["## Lưu ý an toàn — đọc như người học", ""])
        for note in notes:
            lines.append(note)
            lines.append("")

    lines.extend(["## Tự kiểm tra / Retrieval practice", ""])
    lines.append(
        "Đóng phần nội dung phía trên. Trả lời bằng tiếng Việt trước; sau đó nói lại các thuật ngữ "
        "English quan trọng mà không nhìn bài."
    )
    lines.append("")
    for item in blueprint.quick_check:
        lines.append(f"- **{item['question_id']}** — {item['prompt']}")

    lines.extend(["", "## Oral practice / Luyện nói", "", blueprint.oral_exam_prompt, ""])
    lines.extend(
        [
            "### Tự chấm nhanh",
            "",
            "- Tôi có giải thích được **ý nghĩa**, hay chỉ đọc thuộc từ khóa?",
            "- Tôi có dùng đúng thuật ngữ English quan trọng không?",
            "- Tôi có nói thêm điều mà nguồn không hỗ trợ không?",
            "",
            "<details>",
            "<summary>Thông tin kiểm chứng kỹ thuật — không cần đọc để học bài</summary>",
            "",
        ]
    )
    if blueprint.authoritative_verification_required:
        lines.append(
            f"- Có {len(blueprint.authority_targets)} điểm đang cần/đã chờ authority review trước khi coi là hướng dẫn vận hành."
        )
        lines.append(f"- Safety-critical items: {safety_count}.")
        if numeric_count:
            lines.append(f"- Numeric items: {numeric_count}.")
        lines.append("- Internal authority targets: " + ", ".join(blueprint.authority_targets))
    else:
        lines.append("- Bài này không tạo thêm authority queue ở bước source-level.")

    provenance_warning = next(
        (
            warning
            for warning in blueprint.warnings
            if warning.startswith("Creator experience:")
            or warning.startswith("Onboard heuristic:")
            or warning.startswith("Case-specific source:")
            or warning.startswith("Unverified source:")
        ),
        None,
    )
    if provenance_warning:
        lines.append(f"- {provenance_warning}")
    lines.extend(["", "</details>", ""])
    return "\n".join(lines)


def write_lesson_preview(
    blueprint: LessonBlueprint,
    *,
    evidence_anchors: dict[str, tuple[str, ...]],
    output_dir: str | Path,
) -> tuple[Path, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "lesson_blueprint.json"
    md_path = root / "lesson_preview.md"

    json_temp = json_path.with_suffix(".json.tmp")
    json_temp.write_text(
        json.dumps(blueprint_to_json(blueprint), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    json_temp.replace(json_path)

    md_temp = md_path.with_suffix(".md.tmp")
    md_temp.write_text(
        render_lesson_preview(blueprint, evidence_anchors=evidence_anchors),
        encoding="utf-8",
    )
    md_temp.replace(md_path)
    return json_path, md_path
