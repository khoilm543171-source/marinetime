# Local raw-video queue

The queue lets Marinetime accept many files in `storage/raw/` while processing exactly one video at a time on the local machine.

## Default pipeline boundary

Local preprocessing is still sequential and deterministic. Each successful source becomes `EVIDENCE_READY / WAITING_FOR_ALU` first.

The normal worker now also checks the accumulated ALU backlog after local preprocessing finishes. When there are at least **20 validated EvidencePacks without `alus.json`**, Marinetime automatically starts guarded Opus ALU extraction for complete groups of 20.

Examples:

- 4 waiting -> no Opus, keep waiting
- 19 waiting -> no Opus, keep waiting
- 20 waiting -> process 20 with Opus
- 25 waiting -> process the oldest 20, keep 5 waiting
- 40 waiting -> process 40 as two complete threshold groups

Existing valid `alus.json` artifacts are skipped. The worker prints an `OPUS_NOTICE` before the first provider attempt so quota use is visible in the terminal.

Automatic Opus remains subject to Marinetime's per-call, per-video, closeout, and hard daily token guards. It stops before entering the 5.5M-token closeout boundary and never weakens the 7M hard stop.

For an explicitly local-only run, use:

```powershell
python scripts\run_local_queue.py --local-only
```

## 1. Add videos

Copy supported video files into `storage/raw/` (`.mp4`, `.mov`, `.mkv`, `.avi`, `.webm`, `.m4v`).

Then enqueue unseen content:

```powershell
python scripts\enqueue_raw_folder.py --input storage\raw --provenance creator_experience
```

The queue uses SHA-256 content identity. Re-running the scanner does not create a second job for the same video bytes.

## 2. Inspect the queue

```powershell
python scripts\queue_status.py
```

Main local states:

- `PENDING / QUEUED`
- `PREPROCESSING / LOCAL_PREPROCESS`
- `EVIDENCE_READY / WAITING_FOR_ALU`
- `FAILED_PREPROCESS / FAILED`

ALU completion is represented by `storage/evidence/<SOURCE_ID>/alus.json`. Sources with a valid ALU artifact are not selected again by the automatic batcher.

## 3. Run one worker

```powershell
python scripts\run_local_queue.py
```

The worker processes pending videos sequentially. A failed video is recorded as failed, reported immediately in the terminal, and does not prevent later pending videos from running. A final failure summary is printed at the end.

After local processing, the worker automatically evaluates the 20-video Opus threshold.

To process only a bounded number of local jobs:

```powershell
python scripts\run_local_queue.py --limit 20
```

To explicitly retry failed local jobs:

```powershell
python scripts\run_local_queue.py --retry-failed
```

## Restart behavior

If the process or computer stops while a job is `PREPROCESSING`, the next worker run returns that job to `PENDING`. Partial artifacts under that source's dedicated evidence directory are cleared before the retry. If a complete, valid `evidence_pack.json` already exists, the queue adopts it and marks the job `EVIDENCE_READY` without re-running preprocessing.

A later worker run also re-checks the automatic ALU backlog. Therefore a machine restart does not require manually selecting individual EvidencePacks for Opus.

## Output

Each successful source is written beneath:

```text
storage/evidence/<SOURCE_ID>/
```

Local artifacts include `evidence_pack.json`. After successful semantic extraction, the same source directory also contains `alus.json`.
