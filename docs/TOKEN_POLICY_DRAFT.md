# Token Policy Draft

Status: user-approved operating policy; apply as a dedicated follow-up PR after the current EvidencePack/ALU pilot PR.

## Goal
Optimize for engineering quality, not minimum token usage, while preserving quota for the user's other projects.

## Daily allocation
- Assumed provider quota supplied by the user: 10,000,000 tokens/day.
- Marinetime hard allocation: 7,000,000 tokens/day.
- Reserved for other projects: 3,000,000 tokens/day.
- Closeout threshold: 5,500,000 Marinetime tokens/day.

## Behavior
Before 5.5M:
- Prefer the strongest model when the task materially benefits from deeper reasoning.
- Use independent verification/review when it improves correctness, safety, or architecture.
- Do not avoid a useful subagent or second review solely to save tokens.
- Still avoid duplicate work, irrelevant context, blind retries, and whole-repository dumps because they reduce quality as well as waste quota.

At or above 5.5M:
- Freeze new scope, experiments, and optional research.
- Spend remaining Marinetime allocation only on finishing the current PR: tests, debugging, review, safety checks, documentation, and merge readiness.

At 7M:
- Hard stop all new Marinetime provider calls for the day.
- Preserve repo state and handoff instead of borrowing from the 3M reserve.

## PR rule
A PR must enter closeout mode early enough to finish before the 7M hard cap. Do not start a large new PR when the remaining Marinetime allocation is insufficient for implementation + verification + review.

## Enforcement follow-up
The dedicated budget-policy PR should:
1. change the runtime hard cap from 9M to 7M everywhere it is actually enforced;
2. add a 5.5M closeout signal/status;
3. keep the 3M reserve outside Marinetime;
4. add tests proving the hard cap cannot be bypassed;
5. document that provider quota semantics remain provider-reported and may need adjustment if the gateway counts token classes differently.
