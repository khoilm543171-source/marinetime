# Marinetime Learning Web

This layer exists because ALU/Evidence artifacts are machine/audit artifacts, not a pleasant learner interface.

## What it does

The web surface reads the existing Course V2 artifacts and presents them as interactive study sessions:

- track and session navigation;
- Vietnamese learner explanation plus the English technical point;
- collapsible source evidence;
- safety/numeric/authority badges;
- retrieval questions with revealable answer anchors;
- oral-practice prompt;
- previous/next navigation;
- learner completion progress stored locally in the browser.

It does **not** modify ALUs, EvidencePacks, validation decisions, or authority status.

## Build from the current local ALUs

From the repository root:

```powershell
python scripts/build_full_learning_course.py
python scripts/build_learning_web.py --serve
```

Open:

```text
http://127.0.0.1:8765
```

The first command rebuilds Course V2 from every source that has both `evidence_pack.json` and `alus.json`.
A failed/missing ALU source does not prevent the other completed sources from becoming lessons.

The second command writes:

```text
storage/learning/web/
├─ index.html
├─ app.js
├─ styles.css
└─ data/
   └─ course.json
```

No provider/API call is made by the web builder.

## Why Drive is not polled directly in this layer

The repository is public and the existing architecture treats local source/evidence identity as canonical.
This web layer therefore does not embed Google credentials or copy private learning data into GitHub.

Use Drive as a backup/distribution boundary. Once new ALU artifacts are synchronized back to the local canonical
`storage/evidence/<source_id>/` layout, rebuild Course V2 and the web surface.

A future Drive-triggered automation should remain a thin ingestion trigger:

```text
Drive detects new/changed ALU artifact
    -> sync/download to canonical local source folder
    -> deterministic validation
    -> build_full_learning_course.py
    -> build_learning_web.py
    -> notify learner that the new session is ready
```

The trigger must not rewrite ALU facts. If an LLM instructional-designer step is added later, every generated
teaching section should retain explicit ALU IDs/evidence references and remain downstream of deterministic
validation.

## Useful commands

Build only:

```powershell
python scripts/build_learning_web.py
```

Serve on another port:

```powershell
python scripts/build_learning_web.py --serve --port 9000
```

Run web tests:

```powershell
python -m unittest tests.test_learning_web -v
```
