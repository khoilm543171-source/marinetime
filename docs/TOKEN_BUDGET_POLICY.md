# Marinetime daily token budget policy

Status: user-approved MVP operating policy.

## Allocation

Marinetime reserves only part of the user's reported provider quota for this project:

- **Build mode:** below 5,500,000 Marinetime guard tokens/day.
- **Closeout mode:** from 5,500,000 up to (but not including) 7,000,000/day.
- **Hard stop:** 7,000,000/day.
- The remaining provider quota is intentionally outside Marinetime for the user's other projects.

The 5.5M threshold is a **workflow signal**, not a runtime ban. Once reached, do not start new scope, experiments, optional research, or refactors. The remaining allowance exists to finish the active PR: tests, debugging, safety checks, review, documentation, and merge readiness.

The 7M threshold is a **runtime kill-switch**. `assert_token_budget` rejects a request whose preflight projection would cross it.

## Accounting semantics

The v2 ledger reserves each attempted request before contacting the provider, then
settles it with usage returned by the configured Claude-compatible provider. Marinetime counts:

- input tokens;
- output tokens;
- cache-creation input tokens when reported;
- cache-read input tokens when reported.

These are **guard-accounting values**, not a claim about provider billing or quota weighting. The Nghimmo gateway may account for cache tokens, thinking/reasoning tokens, or other token classes differently from the fields it returns. Until the provider documents those semantics, the user's external quota/points application is the authority for remaining provider allowance; the Marinetime ledger is an internal safety guard.

## Preflight limitation

Before a request, Marinetime persists estimated input tokens plus the requested
maximum output. The reservation and its attempt count survive timeouts, missing
or malformed usage responses, and process restarts. Valid actual usage replaces
the reservation rather than being added a second time. Each request is attributed
to its start date in UTC. Per-video tokens and the three-call limit span all dates.
Daily tokens alone reset at the UTC date boundary.

Provider input/output usage must be present and nonnegative integers. The guard
still relies on a text estimate and an undocumented provider accounting system;
it is not a mathematical guarantee about provider billing. Dollar limits remain
optional configuration until a reliable pricing source is connected.

### Ledger migration and recovery

- Existing unversioned usage records remain readable and count as completed attempts.
- New records use schema version `2.0` with `reserved` and `usage` events joined
  by `request_id`. A settlement preserves the reservation's source and timestamp.
- Never truncate or delete the ledger to reset a blocked video or daily limit.
- Malformed lines block new calls with `USAGE_LEDGER_INVALID_LINE`; preserve a
  backup and reconcile the damaged entry with provider records before repairing it.
- A short-lived adjacent `.lock` serializes budget checks and writes across
  processes. `USAGE_LEDGER_LOCKED` blocks new calls. Remove an abandoned lock only
  after confirming every writer is stopped; keep the ledger and reservations.
- Unsettled requests keep their reserved charge. Do not assume that a timeout or
  unsuccessful response was free, or replay it automatically.

The 1.5M closeout window exists partly to keep substantial safety margin before the 7M Marinetime allocation is exhausted.

## Invariants

1. Do not raise the 7M hard cap simply to make a task pass.
2. Do not lower or bypass token accounting in a feature PR.
3. Closeout mode freezes new scope but allows calls required to finish the active PR.
4. At hard stop, preserve repository state and handoff instead of consuming the reserve.
5. If provider accounting semantics become known, update accounting/tests explicitly rather than silently changing token weights.
