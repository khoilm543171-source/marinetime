# Marinetime Subagent Policy

## Purpose
Keep the main coding context small without multiplying token usage unnecessarily.

Subagents support the main agent. They do not replace it.

## Decision gate
Before spawning a subagent, answer:

1. Is the subtask self-contained?
2. Will it generate verbose output that the main context does not need?
3. Can it return a small, verifiable artifact/report?
4. Will the main agent avoid repeating the same work?
5. Is parallel execution actually independent?

If fewer than two answers are `yes`, do the work in the main agent.

## Good Marinetime uses
- Run a noisy test suite and return only failures plus commands.
- Inspect a large log file and return exact error locations.
- Explore an unfamiliar module read-only while the main agent continues a separate task.
- Independently research two unrelated implementation options.

## Bad Marinetime uses
- Editing one small Python file.
- Delegating the entire feature from plan through merge.
- Having one agent extract context and another repeat the same repository scan.
- Chaining reviewer -> fixer -> reviewer when the main agent already owns all state.
- Multiple agents editing the same validators, schemas, or safety files.

## Handoff contract
Every subagent returns only:

```text
RESULT
- concise outcome

EVIDENCE
- file paths / commands / failing tests / exact references

RISKS
- unresolved issues only

HANDOFF
- minimal facts the main agent needs to continue
```

No narrative history.

## Cost rules
- Default concurrent subagents: 0.
- Normal maximum: 1.
- Hard MVP maximum: 2 independent subagents.
- Spawn depth: 1 (nested spawning disabled).
- Do not use a subagent solely to save latency when it materially increases duplicated context.

## Main-agent responsibility
The main agent must still:
- understand the acceptance criteria;
- own the final implementation;
- review `git diff`;
- run or verify the relevant acceptance tests;
- produce the final completion report.
