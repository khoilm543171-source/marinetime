# Tooling adoption decisions

These decisions capture approved engineering/tooling direction without making third-party systems runtime dependencies.

## ECC (`affaan-m/ECC`)

Decision: do **not** install the full ECC stack into Marinetime during the MVP pilot.

Adopt only these patterns for later developer-learning work:
- project-scoped observations/instincts to avoid cross-project contamination;
- evidence-backed confidence for learned behaviors;
- promotion from repeated observation -> rule/skill/workflow only after repeated evidence.

Do not treat ECC agent memory as Marinetime learner/domain memory. The learner state and Marine Engineering knowledge model remain Marinetime-owned.

Revisit full ECC only after the 3-video pilot, and only if its continuous-learning hooks provide measurable value. Native-Windows background-observer limitations are a known constraint; WSL2 may be evaluated later rather than changing the MVP environment now.

## Diagram Design (`cathrynlavery/diagram-design`)

Decision: adopt the diagram-design approach as an **optional authoring/teaching skill**, not a runtime dependency and never an evidence source.

Invariant:

> Diagram output is a teaching artifact. Factual nodes, labels, numeric values, causal links, procedures, and equipment relationships must be traceable to accepted ALUs/evidence. A diagram must not invent technical content to improve layout.

Use after the first real EvidencePack -> ALU -> lesson path works. Suitable Marine Engineering mappings include:
- architecture -> system/equipment overview;
- sequence/process -> operating procedures and watchkeeping flow;
- state machine -> equipment operating states;
- data flow -> fuel/LO/CW/air paths;
- fishbone -> fault root-cause teaching;
- tree -> component hierarchy;
- dependency graph -> troubleshooting dependencies;
- loop -> review/learning cycles.

Do not retrofit developer-facing ASCII diagrams merely for appearance. Retrofit earlier learner-facing visuals only when an existing artifact fails clarity, hierarchy, or traceability checks.

## Ordering

1. Finish deterministic local-video preflight.
2. Run the first real video through local preprocessing.
3. Build a real EvidencePack and ALUs.
4. Produce the first traced lesson.
5. Add diagram-design-based learner visuals where they materially improve understanding.
6. Evaluate ECC-style continuous developer learning after the 3-video pilot.
