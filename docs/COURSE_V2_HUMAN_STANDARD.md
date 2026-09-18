# Marinetime Course V2 — Human Learning Standard

Course V2 starts at the point where validated ALUs become something a person can learn.

## Audience

Primary learner: Vietnamese Engine Cadet / Engine Department student.

The learner should never need to understand JSON, ALU schemas, provenance enums, QA gates, or internal agent terminology in order to learn a lesson.

## Language policy

- **Vietnamese explains.**
- **English stays visible for maritime terminology, onboard communication, manuals and interviews.**
- Evidence may preserve the source language exactly.
- Do not replace a technical English term with a Vietnamese-only label when the learner will need the English term onboard.
- Do not pretend a deterministic fallback is a full technical translation. If the system cannot safely explain more, keep the explanation bounded to the source.

## Every learner lesson must contain

1. What the learner will learn.
2. A 10–15 minute study routine.
3. A compact mental model.
4. English technical vocabulary with Vietnamese meaning where known.
5. For each learning point:
   - English technical point.
   - Vietnamese explanation.
   - evidence hidden behind a collapsible section.
6. Retrieval practice.
7. Oral practice.
8. A short human-readable safety note when relevant.
9. Internal authority/provenance details hidden at the bottom.

## What must not dominate the learner view

- ALU IDs.
- support_level / rendering_scope enums.
- provider/model metadata.
- raw QA check names.
- token counts.
- long authority queues.
- repeated safety disclaimers after every sentence.
- one source video presented as if it were a complete curriculum module.

## Curriculum structure

The home page is organized as:

Track → Module → Lesson

Recommended Engine Cadet order:

1. Engine Room & Machinery
2. Watchkeeping & Shipboard Operations
3. Safety, Regulation & Emergency
4. Technical English & Communication
5. Career, Interview & Onboard Practice
6. Navigation as cross-department reference

A video is evidence input, not the curriculum structure. Multiple source lessons may belong to one learning module.

## Safety writing rule

Safety should read like guidance for a learner:

> Đây là kiến thức để học và luyện phỏng vấn, không phải lệnh thao tác trên tàu. Khi áp dụng thực tế, ưu tiên SMS/checklist, maker manual, standing orders và người phụ trách.

Machine-facing details remain available but collapsed.

## Definition of done

A Course V2 build passes only when learner-facing QA confirms:

- Vietnamese is present.
- English technical points are present.
- Vietnamese explanations are present.
- retrieval and oral practice are present.
- evidence is available but collapsed.
- internal authority targets are not exposed in the main learning flow.
- course navigation uses learner tracks/modules rather than a flat artifact dump.
