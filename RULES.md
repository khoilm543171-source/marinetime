# Marinetime runtime and engineering rules

This file is a detailed reference. It is intentionally not loaded for every coding task or every Claude API call.

## 1. Data trust boundaries
- Raw source and deterministic preprocessing are evidence inputs, not truth by themselves.
- LLM-generated fields are proposals until schema + deterministic validators accept them.
- Every ALU must preserve source lineage through evidence IDs.
- Never mutate the original source-derived statement during curation without storing an explicit revision/change reason.

## 2. Provenance
Keep these concepts separate:
- `media_type`: video, manual, note, textbook, regulation, image, external_document.
- `provenance_class`: standard, maker_manual, regulatory, textbook, onboard_heuristic, creator_experience, case_specific, unverified.

Unverified or experience-based material may be displayed in reference/education mode with labels, but is not operational authority.

For the MVP, operational authority uses an explicit provenance allowlist: `standard`, `maker_manual`, or `regulatory`. `textbook`, `creator_experience`, `onboard_heuristic`, `case_specific`, and `unverified` remain reference/education material even if another process later marks the ALU verified.

## 3. Safety
Code, not the LLM, makes the final allow/deny decision for operational use.
Reject operational use when any required condition fails, including missing evidence, non-direct support, non-authoritative provenance, non-operational rendering scope, missing units for numeric claims, missing required context, rejected/unverified status, or provenance/scope violations.

Operational permission requires all independent gates together: direct support + allowed provenance + `authoritative_operational` rendering scope + verified status + required context + numeric evidence completeness/linkage when applicable. Verification by itself never grants operational permission.

Never infer or repair uncertain numeric readings. Preserve the raw reading and uncertainty.

## 4. Context
Use both `claim_scope` and `context_requirement` when deciding which fields are mandatory:
- minimal
- equipment_specific
- maker_specific
- vessel_specific
- regulatory_specific

An ALU may only reuse known context already present in its validated EvidencePack. The extractor must not promote missing/unknown maker, model, vessel, equipment, or regulatory context into a known value. Context recovery/promotion requires an explicit upstream update with evidence.

Unknown context is allowed to exist for reference/education. It may reduce retrieval priority or block operational use.

## 5. Retrieval/use modes
- `reference_mode`: may surface source-specific or unverified material with labels.
- `educational_mode`: may explain supported concepts with appropriate provenance/context warnings.
- `operational_safety_mode`: strictest; only validated material meeting context/provenance/safety requirements.

Retrieval is not authority. Permission to retrieve and permission to instruct are separate.

## 6. Token/cost rules
- Local preprocessing first.
- Do not resend full transcripts when a bounded time window is sufficient.
- Send selected/cropped frames only.
- Default retrieval top_k=3; increase only after a coverage check fails.
- One automatic retry maximum.
- Abort before a call that would cross hard token/cost limits.
- Log usage metadata, never secrets or full prompts containing sensitive data.

## 7. Learning state
Keep separate axes:
- `mastery_level`: unseen, recognized, can_explain, can_apply, can_troubleshoot.
- `review_status`: not_scheduled, scheduled, due, overdue.

A mastery change requires assessment evidence. `can_troubleshoot` requires an open-response scenario demonstrating core cause/reasoning/action logic; MCQ alone is insufficient.

## 8. Technical English
Lessons may include bilingual terminology, but terminology corrections must not silently change technical meaning. Tutor and examiner behavior are separate concerns.

## 9. Scope
For the 3-video MVP, do not add graph databases, agent swarms, distributed workers, automatic external verification, generic tutor autonomy, or complex prerequisite graphs.

## 10. Claude Code subagents vs skills
Subagents are a developer-workflow mechanism, not part of Marinetime's runtime learning pipeline.

Use a Skill when reusable instructions should execute inside the main context and the task shares state with the main work.
Use a subagent only when isolated context, restricted tools, verbose output isolation, or independent parallel work creates clear value.

Rules:
- Main agent remains responsible for integration and acceptance criteria.
- Do not ask a subagent to reproduce broad repository context it does not need.
- Give each subagent a narrow task, allowed files/tools, output contract, and stop condition.
- Prefer references/paths/results over copied file bodies in the handoff.
- Never chain subagents by default. If a workflow is sequential and state-heavy, keep it in the main context.
- No nested subagents in the 3-video MVP.
- If a subagent causes the main agent to rerun the same search/test, remove that delegation pattern.
- Test/log isolation is a valid use case because high-volume output can stay outside the main context.
- Parallel subagents are allowed only for independent workstreams with no shared writable files.
- Any editing subagent must use an isolated worktree once parallel editing is introduced.


## 11. Source organization and creator identity
- Content hash + stable `source_id` are canonical source identity. Moving or renaming a file must not trigger reprocessing.
- Creator is metadata, never the canonical identity of a source.
- Resolve creator in this order: platform uploader/channel IDs, uploader/channel aliases, filename prefix aliases, OCR candidate, then UNKNOWN.
- OCR-only creator matches are candidates and must not be silently promoted to deterministic creator identity.
- Ambiguous matches resolve to UNKNOWN rather than guessing.
- Keep canonical local evidence storage source-id based.
- Human-facing Drive/viewer organization may group sources by creator without moving or rewriting canonical evidence.
- Creator and topic are separate catalog dimensions; one source may have one creator and multiple topics.
