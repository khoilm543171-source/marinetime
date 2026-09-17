---
name: safety-review
description: Use when modifying validators, retrieval permissions, numeric-claim handling, provenance rules, context requirements, or operational-safety behavior.
---
# Safety Review

Treat LLM output as untrusted.

Code must enforce at minimum:
- evidence refs exist;
- enum values are valid;
- required context exists for the declared context requirement;
- numeric claims include value, unit, measurement condition, equipment context, and source evidence;
- creator experience/onboard heuristic cannot become authoritative operational instruction;
- rejected verification cannot be used educationally/operationally as if valid.

Uncertainty behavior:
- keep reference evidence when useful;
- block unsafe instruction;
- never invent a plausible replacement value;
- preserve the reason code for every rejection.

Add/adjust tests whenever a safety rule changes.
