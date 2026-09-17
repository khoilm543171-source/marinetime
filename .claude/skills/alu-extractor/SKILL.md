---
name: alu-extractor
description: Use when implementing, reviewing, or prompting the expensive semantic pass that converts one EvidencePack into Atomic Learning Units (ALUs).
---
# ALU Extractor

Input: one EvidencePack or a targeted evidence window.
Output: ALU JSON conforming to the current schema.

The extractor may identify statements, context, provenance candidates, relationships, safety candidates, and uncertainty. It must not claim external verification.

Required behavior:
- Preserve evidence refs and timestamps.
- Distinguish creator statement, observed fact, inference, procedure, recommendation, question, unknown.
- Use `unsupported`/uncertain states rather than filling gaps.
- Do not promote creator experience to standard procedure.
- Do not auto-correct OCR or numeric values.
- Keep claims atomic; split when one unit contains multiple independent assertions.

The extractor does **not** decide final operational eligibility. Deterministic validators do.
