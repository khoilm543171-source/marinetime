# MARINETIME — Blueprint V2.2 (MVP-Ready)

> Status: **implementation-ready for a 3-video pilot, then 10-video MVP**  
> Goal: turn Marine Engineering videos/manuals into **traceable, context-aware, bilingual, safety-gated learning** with minimal wasted LLM tokens.

---

## 0. Product definition

Marinetime is a personal Marine Engineering learning system that converts real-world videos, manuals, notes, and onboard experience into structured learning artifacts that are:

- traceable to source evidence;
- explicit about provenance and context;
- safe around operational/numeric claims;
- searchable and reusable;
- useful for visual recognition, oral exams, troubleshooting, watchkeeping, and Technical English.

**Non-goals for MVP:** graph database, multi-agent swarm, mobile app, multi-user platform, autonomous web research, distributed workers, generic “AI tutor that knows everything”.

---

# 1. Non-negotiable invariants

1. **No evidence -> no factual claim.**
2. **No context -> no generalization.**
3. **No provenance -> no authoritative/operational use.**
4. **Safety-critical uncertainty -> no operational instruction.**
5. **Numeric claims require value + unit + operating condition + equipment context + source evidence.**
6. **Creator experience never silently becomes standard procedure.**
7. **LLM may propose; code must enforce safety.**
8. **One raw source gets one expensive semantic understanding pass by default.**
9. **Downstream modules reference artifacts by ID, not by copying full outputs.**
10. **Hard budget limits stop runaway jobs.**

---

# 2. MVP architecture

```text
SOURCE (video/manual/note)
        |
        v
INGEST + MANIFEST
(hash, media type, ownership/license metadata, modified time)
        |
        v
LOCAL PREPROCESSING
(WhisperX / FFmpeg / OCR / keyframes / dedup)
        |
        v
EVIDENCE PACK
(transcript segments, OCR hits, frame refs, timestamps)
        |
        v
ALU EXTRACTION — ONE EXPENSIVE PASS
(minimal semantic units only)
        |
        v
DETERMINISTIC VALIDATION
(schema, evidence refs, enums, safety hard rules, cost guard)
        |
        v
LIGHT CURATION / ENRICHMENT
(context tags, provenance tags, duplicate flags, contradiction candidates)
        |
        v
INDEX
(keyword + metadata; vector later if needed)
        |
        v
RETRIEVAL POLICY
(reference / educational / operational-safety modes)
        |
        v
LESSON + ASSESSMENT
(bilingual, source-traceable)
        |
        v
LEARNER STATE + FEEDBACK REPORT
```

### Pipeline ownership

| Stage | Owner | LLM? | Output |
|---|---|---:|---|
| ingest | code | no | `Source`, `JobManifest` |
| preprocess | code/local models | no | `EvidencePack` |
| ALU extraction | Opus/Sonnet | yes, one main pass | `ALU[]` |
| validation | code | no | accepted/rejected ALUs |
| curation | code + optional cheap/targeted LLM | mostly no | tags, dedupe, contradiction candidates |
| retrieval | code | no | ALU refs |
| lesson builder | LLM | yes | `Lesson` |
| assessment evaluator | rules first, LLM for semantic rubric | limited | `AssessmentResult` |
| learner state | code | no | state update |

**Important:** `knowledge-curator` does **not** create ALUs. It validates/enriches existing ALUs and must not silently rewrite source claims.

---

# 3. Split source representation: media vs authority

Never overload one `source_type` field.

```text
media_type:
  video
  manual
  note
  textbook
  regulation
  image
  external_document

provenance_class:
  standard
  maker_manual
  regulatory
  textbook
  onboard_heuristic
  creator_experience
  case_specific
  unverified
```

Examples:

```text
YouTube maker training video:
media_type = video
provenance_class = maker_manual

Chief Engineer TikTok:
media_type = video
provenance_class = creator_experience
```

---

# 4. EvidencePack contract

```json
{
  "schema_version": "1.0",
  "source_id": "SRC-0001",
  "transcript_segments": [
    {"id":"SEG-01","start":12.4,"end":18.9,"text":"...","asr_confidence":0.91}
  ],
  "ocr_hits": [
    {"id":"OCR-01","time":16.2,"text":"SYNCHROSCOPE","ocr_confidence":0.88}
  ],
  "frames": [
    {"id":"FRM-01","time":16.2,"path":"frames/SRC-0001/016.2.webp","quality":"usable"}
  ],
  "preprocess_version":"pre-v1"
}
```

EvidencePack contains **observations only**. It does not contain lessons, normalized procedures, or universal technical claims.

---

# 5. ALU contract — minimal but explicit

An ALU is **a source-grounded learning unit**, not automatically a universal truth.

```json
{
  "schema_version": "1.0",
  "alu_id": "SRC-0001-U01",
  "source_id": "SRC-0001",
  "evidence_refs": ["SEG-01", "FRM-01"],

  "statement": "The creator closes the breaker after observing the synchroscope.",

  "statement_type": "creator_statement",
  "support_level": "directly_supported",
  "rendering_scope": "source_specific",
  "claim_scope": "equipment_specific",
  "context_requirement": "equipment_specific",

  "media_type": "video",
  "provenance_class": "creator_experience",
  "verification_status": "unverified",

  "domain": {
    "system": "electrical_generator",
    "equipment": "generator",
    "component": "synchroscope",
    "parameter": null,
    "fault": null,
    "procedure": "generator_synchronisation",
    "hazard": null
  },

  "context": {
    "vessel_type": "unknown",
    "maker": "unknown",
    "model": "unknown",
    "operating_mode": "unknown",
    "operating_condition": "unknown",
    "manual_revision": "unknown",
    "regulatory_context": "unknown"
  },

  "safety": {
    "safety_critical": false,
    "numeric_claim": false
  },

  "language": {
    "source_language": "en",
    "technical_terms": ["synchroscope", "breaker"]
  }
}
```

### Allowed `statement_type`

- `observed_fact`
- `creator_statement`
- `inferred_relationship`
- `procedure`
- `recommendation`
- `question`
- `unknown`

### Allowed `support_level`

- `directly_supported`
- `partially_supported`
- `context_limited`
- `unsupported`

### Allowed `rendering_scope`

- `source_specific`
- `context_specific`
- `general_educational`
- `authoritative_operational`

### Allowed `context_requirement`

- `minimal`
- `equipment_specific`
- `maker_specific`
- `vessel_specific`
- `regulatory_specific`

---

# 6. Avoid ALU extractor overload

The main LLM extraction pass should do only these semantic tasks:

1. split evidence into atomic learning units;
2. write a concise source-grounded statement;
3. attach evidence refs;
4. suggest `statement_type` and basic domain tags;
5. flag obvious uncertainty.

It should **not** be responsible for the final decision on:

- safety eligibility;
- authoritative use;
- cost budget;
- schema correctness;
- whether maker context is sufficient;
- whether a numeric claim is valid;
- learner mastery.

Those are validated by code.

### Targeted enrichment exception

Only if an ALU is high-value but ambiguous may Marinetime run a **targeted second pass** on that ALU/evidence window. Never re-send the whole source unless necessary.

---

# 7. Hard safety validator

LLM proposes flags; validator enforces them.

Pseudo-rules:

```python
if not alu.evidence_refs:
    reject("missing_evidence")

if alu.support_level == "unsupported":
    reject_for_educational_claim_use()

if alu.safety.safety_critical and missing_required_context(alu):
    reject_for_operational_use("INSUFFICIENT_CONTEXT")

if alu.safety.numeric_claim:
    require(value, unit, measurement_condition, equipment_context, source_evidence)

if alu.provenance_class in {"creator_experience", "onboard_heuristic", "case_specific"} \
   and alu.rendering_scope == "authoritative_operational":
    reject("provenance_scope_violation")

if alu.context_requirement == "maker_specific" and alu.context.maker == "unknown":
    reject_for_operational_use("MAKER_UNKNOWN")
```

### Numeric safety rule

Never auto-correct an uncertain OCR reading.

```text
OCR: 80 bar
Model guess: "probably 8 bar"

FORBIDDEN: silently change to 8 bar
REQUIRED: preserve source reading + mark uncertain + request verification
```

Numeric evidence must preserve:

- value;
- unit;
- measurement point;
- operating/load condition;
- equipment;
- maker/model when required;
- source revision/page/timestamp if available.

---

# 8. Retrieval/use modes

Not every retrieved ALU can be used in the same way.

## 8.1 `reference_mode`
May show unverified/creator-specific content if clearly labeled.

## 8.2 `educational_mode`
May teach concepts using textbook/manual/creator evidence with provenance visible. Context-limited claims must remain labeled.

## 8.3 `operational_safety_mode`
Strictest. Only ALUs that pass required provenance, context, evidence, and safety validation may be used to form operational guidance.

### Retrieval policy

```text
1. hard exclusion
2. preferred context match
3. semantic/keyword ranking
4. fallback candidates with warnings
5. coverage check
```

Context matching should be graded, not purely binary:

```text
exact maker/model match           1.0
same equipment, maker unknown     0.7
same system, different maker      0.4
general theory                    0.3
unknown context                   reference/educational only
```

Default `top_k = 3`, then increase to 5 only if coverage validation says required lesson sections are unsupported.

---

# 9. Marine Engineering relation fields without a graph DB

Do not build a graph database for MVP, but do not bury all relations in prose.

Optional structured relation:

```json
{
  "subject": "exhaust_gas_temperature",
  "relation": "may_indicate",
  "object": "poor_combustion",
  "evidence_refs": ["SEG-42"],
  "context": {"equipment":"main_engine","maker":"unknown"}
}
```

Suggested relations:

- `contains`
- `supplies`
- `controls`
- `protects`
- `causes`
- `may_indicate`
- `requires`
- `precedes`
- `follows`

---

# 10. Bilingual / Technical English policy

Marinetime should preserve **technical English as the canonical technical term**, while teaching in Vietnamese when useful.

Each important technical term may store:

```json
{
  "term_en": "synchroscope",
  "meaning_vi": "đồng hồ hòa đồng bộ",
  "source_context": "generator synchronisation",
  "source_alu_ref": "SRC-0001-U03"
}
```

Lesson policy:

- explain concept in Vietnamese when needed;
- keep canonical equipment/component/procedure terms in English;
- provide English sentence patterns for oral exam/watchkeeping;
- correct English terminology separately from technical understanding;
- a typo alone should not fail a conceptual assessment unless the term changes technical meaning or safety interpretation.

---

# 11. LearnerState: split mastery from review

```text
mastery_level:
  unseen
  recognized
  can_explain
  can_apply
  can_troubleshoot

review_status:
  not_scheduled
  scheduled
  due
  overdue
```

Every mastery update requires `evidence_of_mastery`:

```json
{
  "assessment_id":"ASM-003",
  "assessment_type":"troubleshooting_scenario",
  "observed_at":"...",
  "result":"pass",
  "error_tags":[]
}
```

### Definition of `can_troubleshoot` for MVP

A learner reaches `can_troubleshoot` only after a **constructed-response scenario**, not simple ABCD multiple choice.

Minimum pass requirements:

1. identifies the central symptom/fault class;
2. proposes at least one plausible core cause supported by the learned material;
3. proposes a safe diagnostic check or next action;
4. avoids unsafe/unsupported operational instructions;
5. explanation is semantically correct even if wording differs.

The evaluator should distinguish:

- conceptual correctness;
- diagnostic reasoning;
- Technical English terminology.

---

# 12. Lesson traceability contract

A lesson must be auditable at section level.

```json
{
  "lesson_id":"LES-001",
  "lesson_version":"1.0",
  "learner_goal":"generator_synchronisation",
  "mode":"educational_mode",
  "generated_sections":[
    {
      "section_id":"S1",
      "section_type":"explanation",
      "content":"...",
      "source_alu_refs":["SRC-0001-U01"],
      "frame_refs":["FRM-01"],
      "provenance_labels":["creator_experience"],
      "uncertainty_flags":[]
    }
  ],
  "model_name":"...",
  "prompt_version":"lesson_builder_v1",
  "pipeline_version":"mvp-2.2",
  "created_at":"..."
}
```

A lesson section without `source_alu_refs` cannot make a factual technical claim.

---

# 13. FeedbackReport (replaces generic Incident-only model)

```text
feedback_type:
  extraction_error
  evidence_error
  provenance_error
  safety_error
  contradiction_error
  retrieval_error
  teaching_quality
  learner_state_error
  UI_error

resolution_action:
  accept_feedback
  reject_feedback
  create_correction
  rerun_partial_pipeline
  rerun_full_pipeline
  mark_source_unreliable
```

Every report should trace back to:

```text
answer/lesson section
  -> ALU
    -> evidence
      -> source + timestamp/page
```

---

# 14. Reprocessing policy

Default rule: one expensive semantic pass per source.

Allowed exceptions:

```text
full_source_reprocess
partial_source_reprocess
targeted_evidence_recovery
```

Use targeted recovery first:

- rerun OCR only on a panel crop;
- re-transcribe one segment;
- extract frames around one timestamp;
- re-run one ambiguous ALU.

A full source reprocess is allowed only when:

- source changed;
- schema/pipeline version materially changed;
- previous evidence extraction was invalid;
- human review explicitly requests it.

---

# 15. Hard cost kill-switch

`TokenLedger` is not enough. Marinetime needs a blocking budget governor.

Example MVP config:

```yaml
budget:
  max_cost_per_video_usd: 0.50
  max_cost_per_job_usd: 2.00
  max_daily_cost_usd: 10.00
  max_auto_retries: 1
  max_llm_calls_per_video: 3
```

Before every paid call:

```text
estimate request cost
+ current video spend
+ current job spend
+ daily spend
```

If any limit would be exceeded:

```text
STOP JOB
status = BUDGET_BLOCKED
write alert
preserve resumable state
```

No automatic override.

Also log value metrics:

- `units_created`
- `units_accepted`
- `units_rejected`
- `claims_with_evidence`
- `claims_needing_verification`
- `duplicates_removed`
- `contradictions_found`
- `human_correction_count`

Derived metrics:

- `tokens_per_accepted_alu`
- `tokens_per_evidence_backed_claim`
- `tokens_per_useful_lesson`
- `cost_per_accepted_alu`

---

# 16. Prompt + model version registry

```text
prompts/
  alu_extraction_v1.txt
  lesson_builder_v1.txt
  assessment_eval_v1.txt
```

Every LLM-produced artifact stores:

```text
prompt_version
model_name
model_parameters
schema_version
pipeline_version
```

Do not rely on `CLAUDE.md` for runtime safety. `CLAUDE.md` is for coding-agent behavior; runtime invariants must live in schema, validators, configuration, tests, and code.

---

# 17. Storage and schemas for MVP

```text
marinetime/
├── README.md
├── CLAUDE.md
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml
├── pyproject.toml
├── requirements.lock
├── src/marinetime/
│   ├── ingest/
│   ├── preprocess/
│   ├── evidence/
│   ├── alu/
│   ├── validation/
│   ├── curation/
│   ├── retrieval/
│   ├── lesson/
│   ├── assessment/
│   ├── learner/
│   ├── feedback/
│   ├── budget/
│   ├── prompts/
│   └── providers/
├── storage/
│   ├── raw/
│   ├── evidence/
│   ├── frames/
│   ├── exports/
│   ├── cache/
│   └── manifests/
├── schemas/
│   ├── source.schema.json
│   ├── evidence.schema.json
│   ├── alu.schema.json
│   ├── frame.schema.json
│   ├── lesson.schema.json
│   ├── assessment.schema.json
│   ├── learner_state.schema.json
│   ├── feedback_report.schema.json
│   ├── contradiction.schema.json
│   ├── job_manifest.schema.json
│   └── token_ledger.schema.json
├── prompts/
├── migrations/
├── evals/golden_set/
├── tests/
├── docs/
└── scripts/
```

---

# 18. Minimal skills/rules

Only 5 project skills for MVP:

1. `token-governor`
2. `source-ingest`
3. `evidence-extractor`
4. `alu-extractor-curation-policy` (clear sub-ownership: extractor creates, curator validates/enriches)
5. `lesson-designer`

Future only if needed:

- external verifier;
- fault-reasoner;
- generic tutor;
- full research agent.

---

# 19. 3-video pilot -> 10-video MVP

## Phase A: 3-video pilot

Choose deliberately different videos:

1. clear technical explanation;
2. blurry/ambiguous visual or numeric reading;
3. creator heuristic / practical case.

Goal: validate contracts and safety behavior before scaling.

Required outputs:

- Source manifest;
- EvidencePack;
- ALUs;
- validator decisions;
- one bilingual lesson;
- one oral question;
- one troubleshooting scenario;
- one feedback report path;
- token/cost ledger.

## Phase B: 10-video MVP

Include:

- duplicate content;
- contradiction;
- unknown maker/model;
- safety-critical number;
- useless vlog-like clip;
- good equipment visual;
- procedure explanation;
- fault/troubleshooting case.

---

# 20. MVP evaluation

## Pipeline acceptance

- 100% sources have stable IDs + provenance metadata.
- unchanged sources are not reprocessed.
- every accepted ALU has valid evidence refs.
- unsupported/ambiguous claims are flagged.
- creator experience never becomes authoritative procedure automatically.
- safety-critical numeric ambiguity is withheld.
- lesson claims trace to ALUs.
- budget governor stops runaway jobs.

## Learning utility

Do not rely only on “I liked the lesson”.

For each topic compare raw-video learning vs Marinetime lesson on:

- recall;
- visual identification;
- oral explanation completeness;
- troubleshooting reasoning;
- time spent;
- confidence vs actual correctness.

For one learner, use sequential testing:

```text
video-only session
-> assessment
-> Marinetime lesson session
-> same-format assessment
-> delayed review after 2–3 days
```

The MVP succeeds only if Marinetime improves at least one meaningful learning outcome without creating unsafe or unsupported technical guidance.

---

# 21. Final build rule

Do not add a new agent, schema, service, or database unless it solves an observed failure in the 3-video/10-video MVP.

**Marinetime V2.2 is considered ready to code when:**

1. Source/Evidence/ALU/Lesson/Learner schemas validate.
2. Safety validator has unit tests.
3. Budget kill-switch has unit tests.
4. One end-to-end 3-video run completes with traceability.
5. A human can inspect every generated technical statement back to its source evidence.
