# September 2026 integrity fixes

This change addresses reproducible failures in the video-to-learning pipeline.
It does not certify the maritime correctness of a production corpus.

## Changed behavior

- Source learning cards revalidate each stored ALU's shape, source identity,
  provenance, context and current eligibility. Cached approval cannot override
  rejected verification or unsupported evidence. An explicit stored withhold
  remains withheld. Boolean decision fields are required.
- Authority rule version `curated_official_source_rules_v2` grants direct support
  only for a whole, allowlisted four-stage proposition. Keyword overlap returns
  candidate references with `unresolved` status, including contradictory wording.
- Vietnamese explanations use a vetted whole-proposition rendering or a labeled
  source excerpt. Other English claims remain visible with a Vietnamese notice
  that the explanation needs review; no topic template adds source-attributed facts.
- The token ledger records durable reservations before provider calls. Missing
  usage and timeouts do not erase attempts. Per-video tokens and the three-call
  cap survive a new UTC day. See [budget recovery](TOKEN_BUDGET_POLICY.md).
- Rediscovering moved content repairs a missing video path without changing the
  source ID, status or attempt count. A live duplicate location is not replaced.
- Queue CLI failures return a nonzero exit code, including `--local-only`.
- ALU discovery validates stored contents before treating extraction as complete.

## Existing local data

1. Back up the current evidence, ALUs, ledger and exported lessons before updating.
2. Do not change rejected ALUs back to unverified to make a build succeed.
   Structurally incomplete ALUs need a traceable upstream correction.
3. Regenerate authority reviews and derived lessons from the original artifacts;
   previously exported documents are not retroactively repaired by a code update.
   The topic lesson builder rejects v1 authority reviews. Keyword matches may
   now remain unresolved, and a
   topic lesson that requires more official support may fail its existing QA gate.
4. To inspect the source-card/course path locally, use a separate output directory:

   ```powershell
   python scripts/build_full_learning_course.py --output-root storage/learning/review_fixed --export storage/exports/review_fixed.zip
   ```

   This course build makes no provider calls. It reads the existing evidence and
   ALUs, so their local paths must already be configured as documented by the pilot.

## Verification and development workflow

Run `python -m unittest discover -s tests -v`. Regression cases cover negation,
extra claims, stale approvals, malformed artifacts, usage omissions, timeouts,
daily rollover, moved files, and CLI failure status. Provider tests use fake
HTTP transports; they do not spend API quota. CI also exercises Windows because
the pilot uses local Windows tools.

Before merging safety or accounting changes, inspect the counterexample tests
and require both CI jobs (`unit-tests (ubuntu-latest)` and
`unit-tests (windows-latest)`) in a GitHub branch rule. Require a PR and an
independent review when a second reviewer is available. Workflow YAML alone
does not enable branch protection.

The remaining pilot gate is a human-reviewed sample of actual videos and lessons,
including OCR ambiguity, numerical conditions and contradictory sources. Synthetic
regressions do not replace that corpus, ASR/OCR validation, or maritime review.
