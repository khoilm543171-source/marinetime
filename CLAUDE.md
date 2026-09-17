# Marinetime — Claude coding brain

Marinetime is an evidence-first Marine Engineering learning system. The current target is the **3-video MVP pilot**, not a general AI platform.

## Always-on invariants
1. No evidence -> no factual claim.
2. No context -> no generalization.
3. No provenance -> no authoritative or operational use.
4. Safety-critical uncertainty -> withhold operational instruction.
5. Never auto-correct uncertain OCR numeric values.
6. Creator experience/onboard heuristic may be shown as labeled evidence but never promoted to authoritative procedure.
7. LLM output is untrusted until deterministic validation passes.
8. Deterministic/local work comes before LLM calls.
9. One expensive semantic pass per source by default; targeted recovery is allowed.
10. Never bypass token/cost guards, schema validation, source lineage, or safety validation.

## Token discipline
- Read only files needed for the current task.
- Do not dump the repository into context.
- Prefer artifact IDs/references over copying long JSON.
- Keep runtime prompts task-specific and versioned.
- Do not create extra agents/frameworks unless a measured pilot failure requires them.
- One automatic retry maximum.
- Daily token mode is defined in `docs/TOKEN_BUDGET_POLICY.md`: below 5.5M = build; at/above 5.5M = freeze new scope and close the active PR; 7M = hard stop Marinetime provider calls.
- Never raise or bypass the 7M Marinetime hard cap to finish a task.

## File loading policy
- `RULES.md` is **not** an always-load file. Read it only when changing architecture, schemas, safety, retrieval permissions, provider routing, budgets, or learning-state logic.
- Load one relevant `.claude/skills/*/SKILL.md` when its trigger matches the task. Do not load unrelated skills.
- Runtime safety must live in code/schema/tests, not only in this file or prompts.

## Ownership
- ingest -> Source
- preprocess -> EvidencePack
- ALU extractor -> ALU
- validator -> hard safety/provenance eligibility
- curator -> validate/dedupe/contradiction metadata; never silently rewrite source meaning
- lesson builder -> traceable Lesson

Stop when acceptance criteria are met. Do not improve unrelated code.

## Subagent policy
Subagents are an exception, not the default.

The main agent owns the task end-to-end: plan, implementation, integration, validation, final diff, and completion report. Do not delegate the whole task and wait for a summary.

Use a subagent only when at least one condition is true:
- the subtask is self-contained and can return a bounded result;
- it produces verbose logs/search output that would pollute the main context;
- two or more subtasks are genuinely independent and can run in parallel;
- it needs a restricted tool/permission set different from the main task;
- the work is a natural context boundary that would otherwise justify `/clear`.

Do not use a subagent when:
- the change is quick or single-file;
- planning, implementation, and testing share substantial state;
- the next step depends tightly on details from the previous step;
- the main agent would need to reopen the same files or rerun the same tools afterward;
- delegation exists only to "use agents".

MVP limits:
- no nested subagents;
- no agent-to-agent chat loops;
- no more than 2 concurrent subagents;
- prefer one main agent plus at most one specialist;
- subagents must return compact evidence-backed reports, not essays.

Subagent report contract:
- `RESULT`: what was found/done;
- `EVIDENCE`: exact files, commands, tests, or line references;
- `RISKS`: unresolved issues only;
- `HANDOFF`: only the minimum state the main agent needs.

If the main agent must redo the subagent's exploration to understand the report, the delegation failed. Improve the contract or do the work directly next time.
