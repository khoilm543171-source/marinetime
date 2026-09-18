from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cards import SourceLearningCard


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
    appraisal = _find_item(key_items, "appraisal")
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
            "List the four passage-planning stages in the correct order.",
            (str(framework.get("alu_id")),) if framework else all_ids,
        ),
        LearningObjective(
            "LO-02",
            "Explain what the source says happens during appraisal, planning, execution, and monitoring.",
            tuple(str(item.get("alu_id")) for item in stage_items),
        ),
        LearningObjective(
            "LO-03",
            "Give a 60–90 second interview answer that names the four stages and explains the work done in each stage.",
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
                "prompt": "Without looking back, list the four passage-planning stages in order.",
                "answer_anchor": str(framework.get("statement", "")),
                "alu_id": str(framework.get("alu_id", "")),
            }
        )
    if appraisal:
        questions.append(
            {
                "question_id": "Q-02",
                "prompt": "During appraisal, what information does this source say should be gathered before drawing the route? Recall at least four examples.",
                "answer_anchor": str(appraisal.get("statement", "")),
                "alu_id": str(appraisal.get("alu_id", "")),
            }
        )
    if planning:
        questions.append(
            {
                "question_id": "Q-03",
                "prompt": "During planning, what route checks and actions does this source mention before the route is used?",
                "answer_anchor": str(planning.get("statement", "")),
                "alu_id": str(planning.get("alu_id", "")),
            }
        )
    if execution:
        questions.append(
            {
                "question_id": "Q-04",
                "prompt": "What does this source say the bridge team does during execution?",
                "answer_anchor": str(execution.get("statement", "")),
                "alu_id": str(execution.get("alu_id", "")),
            }
        )
    if monitoring:
        questions.append(
            {
                "question_id": "Q-05",
                "prompt": "How does this source say the vessel's position and progress should be monitored and cross-checked?",
                "answer_anchor": str(monitoring.get("statement", "")),
                "alu_id": str(monitoring.get("alu_id", "")),
            }
        )

    oral = (
        "Interview question: **How do you make a passage plan?**\n\n"
        "Answer in 60–90 seconds. Use this structure:\n"
        "1. Name the four stages in order.\n"
        "2. Appraisal — explain what information you gather before drawing the route.\n"
        "3. Planning — explain the berth-to-berth route checks, validation, and discussion mentioned in the source.\n"
        "4. Execution — explain what happens once the plan is approved.\n"
        "5. Monitoring — explain how progress and position are checked and cross-checked.\n\n"
        "Do not only recite the four stage names; demonstrate that you understand what happens in each stage."
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
                text=f"Explain this evidence-backed idea in your own words: {_plain_claim(str(item.get('statement', '')))}",
                alu_ids=(str(item.get("alu_id")),),
            )
        )

    mental_model = tuple(_item_heading(item) for item in key_items[:5])
    quick_check = tuple(
        {
            "question_id": f"Q-{index:02d}",
            "prompt": f"Without looking back, explain: {_item_heading(item)}.",
            "answer_anchor": str(item.get("statement", "")),
            "alu_id": str(item.get("alu_id", "")),
        }
        for index, item in enumerate(key_items[:5], start=1)
    )
    oral = (
        f"Explain **{clean_display_title(card.title)}** in 60–90 seconds without reading notes. "
        "State the main idea first, then support it with the evidence-backed points shown in this lesson."
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
    lines: list[str] = [
        f"# {blueprint.display_title}",
        "",
        "> Source-grounded lesson preview. Creator experience remains creator experience until higher-authority evidence verifies it.",
        "",
        "## Learning goals",
        "",
    ]
    for objective in blueprint.learning_objectives:
        lines.append(f"- **{objective.objective_id}:** {objective.text}")

    lines.extend(["", "## Mental model", ""])
    if blueprint.mental_model:
        for line in blueprint.mental_model:
            lines.append(f"- {line}")
    else:
        lines.append("- No compact mental model could be derived deterministically.")

    lines.extend(["", "## Learn the source", ""])
    for index, item in enumerate(blueprint.key_items, start=1):
        heading = _item_heading(item)
        lines.extend(
            [
                f"### {index}. {heading}",
                "",
                f"**Source-backed point:** {item['statement']}",
                "",
                f"- **Support:** {item.get('support_level')}",
            ]
        )
        flags: list[str] = []
        if item.get("safety_critical"):
            flags.append("safety-critical")
        if item.get("numeric_claim"):
            flags.append("numeric")
        if flags:
            lines.append("- **Needs extra care:** " + ", ".join(flags))

        lines.extend(["", "<details>", "<summary>Show evidence</summary>", ""])
        anchors = evidence_anchors.get(str(item.get("alu_id")), ())
        if anchors:
            for anchor in anchors:
                lines.append(f"- {anchor}")
        else:
            lines.append("- No evidence anchor available.")
        lines.extend(["", "</details>", ""])

    lines.extend(["## Oral interview practice", "", blueprint.oral_exam_prompt, ""])
    lines.extend(
        [
            "### Self-check",
            "",
            "- Did I explain the work done in each stage, rather than only reciting labels?",
            "- Did I stay inside what the evidence actually supports?",
            "- Did I avoid treating creator experience as an official procedure?",
            "",
            "## Retrieval practice",
            "",
        ]
    )
    for item in blueprint.quick_check:
        lines.append(f"{item['question_id']}. {item['prompt']}")

    lines.extend(["", "## Trust boundary", ""])
    if blueprint.authoritative_verification_required:
        safety_count = sum(
            1 for item in blueprint.key_items if bool(item.get("safety_critical"))
        )
        numeric_count = sum(
            1 for item in blueprint.key_items if bool(item.get("numeric_claim"))
        )
        lines.append(
            f"- **Authority check queued:** {len(blueprint.authority_targets)} ALU(s)."
        )
        lines.append(f"- Safety-critical source claims: {safety_count}.")
        if numeric_count:
            lines.append(f"- Numeric claims needing context/unit verification: {numeric_count}.")
        lines.append(
            "- These claims are usable for source-level learning only; they are not operational guidance yet."
        )
        lines.append(
            "- Authority targets: " + ", ".join(blueprint.authority_targets)
        )
    else:
        lines.append(
            "- No additional authority queue was created by this preview; existing validation still applies."
        )

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

    lines.extend(
        [
            "",
            "## Next stage",
            "",
            "Cross-source Topic Packet → Authority Verifier → Instructional Designer → assessment QA.",
            "",
        ]
    )
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
