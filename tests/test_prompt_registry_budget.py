from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.llm.prompt_registry import PROMPTS, load_prompt
from marinetime.llm.token_guard import TokenLimits


def test_prompt_output_defaults_respect_global_per_call_budget() -> None:
    limits = TokenLimits()
    offenders = {
        name: spec.default_max_output_tokens
        for name, spec in PROMPTS.items()
        if spec.default_max_output_tokens > limits.max_output_tokens_per_call
    }
    assert offenders == {}


def test_alu_prompt_uses_bounded_v5_contract() -> None:
    spec = PROMPTS["alu_extract"]
    assert spec.version == "alu_extraction_v5"
    assert spec.default_max_output_tokens == TokenLimits().max_output_tokens_per_call


def test_alu_v5_prompt_locks_evidence_faithful_wording_rules() -> None:
    spec, text = load_prompt("alu_extract", repo_root=ROOT)
    assert spec.version == "alu_extraction_v5"
    required_phrases = (
        "One ALU = one main proposition",
        "Preserve epistemic framing",
        "Use observed_fact only for something directly observable",
        "Do not add technical names, acronyms, acronym expansions",
        "Low-confidence OCR should not be the sole basis",
        "Do not strengthen modality",
    )
    for phrase in required_phrases:
        assert phrase in text


def test_bug_audit_prompt_is_registered_and_guard_bounded() -> None:
    spec, text = load_prompt("bug_audit", repo_root=ROOT)
    assert spec.version == "bug_audit_v1"
    assert spec.default_max_output_tokens <= TokenLimits().max_output_tokens_per_call
    assert "Most likely root cause" in text
    assert "Do not recommend disabling validation" in text
