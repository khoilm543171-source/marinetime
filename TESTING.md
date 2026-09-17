# Marinetime Testing Contract

A coding task is not complete until relevant tests have actually run.

## Default test command

```bash
python -m unittest discover -s tests -v
```

## Safety-sensitive changes
Always run tests covering:
- safety validator behavior;
- token/cost guards;
- LLM response parsing when relevant;
- schema validation when schemas change.

## Completion requirements
- No failing relevant tests.
- No secret/API key appears in `git diff`.
- No safety invariant is weakened silently.
- No token/cost guard is bypassed.
- Any changed prompt/schema has a version or explicit migration decision.

## Test subagent use
A test subagent is useful only when output is noisy or long. It should return:
- exact command run;
- pass/fail counts;
- failing test names;
- short error excerpts;
- no implementation edits.

For one small targeted test, run it directly in the main context.
