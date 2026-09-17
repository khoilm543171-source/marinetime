# Marinetime MVP Starter

This repository is the **frozen 3-video pilot scaffold** for Marinetime.

## Goal
Prove that a small set of Marine Engineering videos can be converted into evidence-backed, context-aware, bilingual learning material **without unsafe hallucination or runaway token cost**.

## Pilot rule
Do not add agents, services, databases, or abstractions unless a failure in the 3-video pilot proves they are needed.

## 3-video pilot
Use exactly three deliberately different sources:
1. clear technical explanation;
2. blurry/ambiguous visual or numeric reading;
3. creator heuristic / practical case.

## Pipeline

```text
SOURCE
  -> INGEST + MANIFEST
  -> LOCAL PREPROCESSING
  -> EVIDENCE PACK
  -> ALU EXTRACTION (one expensive semantic pass)
  -> DETERMINISTIC VALIDATION
  -> LIGHT CURATION
  -> SIMPLE INDEX
  -> LESSON / ASSESSMENT
  -> LEARNER STATE
  -> FEEDBACK REPORT
```

## Non-negotiable invariants
- No evidence -> no factual claim.
- No context -> no generalization.
- No provenance -> no authoritative/operational use.
- Safety-critical uncertainty -> no operational instruction.
- Numeric claims require explicit value, unit, measurement condition, equipment context, and source evidence.
- Creator experience never silently becomes standard procedure.
- LLM may propose; code must enforce safety.
- One source gets one expensive semantic pass by default; targeted recovery is allowed.
- Hard budget limits stop runaway jobs.

## Quick check

```bash
python -m unittest discover -s tests -v
```

## What is intentionally NOT included yet
- graph database
- multi-agent swarm
- autonomous external verification
- distributed workers
- polished UI
- generic tutor agent

## Claude/Opus API layer

The starter now includes a single provider doorway:

```text
src/marinetime/llm/
  client.py          # Anthropic-Messages-compatible HTTP client
  router.py          # approved task routing only
  token_guard.py     # hard preflight token kill-switch
  prompt_registry.py # versioned runtime prompts
  usage.py           # token usage JSONL, no secrets/prompts
```

Setup instructions: `docs/LLM_API_SETUP.md`.

### Instruction hierarchy for low token waste

```text
CLAUDE.md                    tiny always-on coding rules
RULES.md                     detailed reference; load only when relevant
.claude/skills/*/SKILL.md    task-specific progressive rules
prompts/*.txt                runtime prompts sent only for that task
```

Do **not** concatenate all four layers into every Claude API request.

## Claude Code development policy (v0.2.4)
- Main agent owns implementation and integration.
- Subagents are opt-in for isolated/verbose/independent work only.
- Nested subagents are disabled for the MVP.
- `test-summarizer` is the only project subagent included initially and is read-only.
- Use `TESTING.md` before declaring work complete.
- Use `docs/HANDOFF.md` before `/clear` or transferring a long session.
- See `docs/SUBAGENT_POLICY.md` for delegation rules.
