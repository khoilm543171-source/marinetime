from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PromptSpec:
    task: str
    version: str
    path: Path
    default_max_output_tokens: int


PROMPTS: dict[str, PromptSpec] = {
    "alu_extract": PromptSpec(
        task="alu_extract",
        version="alu_extraction_v3",
        path=Path("prompts/alu_extraction_v3.txt"),
        default_max_output_tokens=6_000,
    ),
    "lesson_build": PromptSpec(
        task="lesson_build",
        version="lesson_builder_v1",
        path=Path("prompts/lesson_builder_v1.txt"),
        default_max_output_tokens=1_500,
    ),
    "assessment_eval": PromptSpec(
        task="assessment_eval",
        version="assessment_eval_v1",
        path=Path("prompts/assessment_eval_v1.txt"),
        default_max_output_tokens=1_000,
    ),
}


def load_prompt(task: str, *, repo_root: str | Path = ".") -> tuple[PromptSpec, str]:
    try:
        spec = PROMPTS[task]
    except KeyError as exc:
        raise ValueError(f"Unknown Marinetime LLM task: {task}") from exc

    path = Path(repo_root) / spec.path
    return spec, path.read_text(encoding="utf-8")
