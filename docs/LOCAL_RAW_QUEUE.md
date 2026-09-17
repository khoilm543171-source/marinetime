# Local raw-video queue

The queue lets Marinetime accept many files in `storage/raw/` while processing exactly one video at a time on the local machine.

## Safety boundary

The local queue does **not** call Opus or any other LLM provider. It stops each successful job at `EVIDENCE_READY / WAITING_FOR_ALU`.

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

Main states:

- `PENDING / QUEUED`
- `PREPROCESSING / LOCAL_PREPROCESS`
- `EVIDENCE_READY / WAITING_FOR_ALU`
- `FAILED_PREPROCESS / FAILED`

## 3. Run one local worker

```powershell
python scripts\run_local_queue.py
```

The worker processes pending jobs sequentially. A failed video is recorded as failed and does not prevent later pending videos from running.

To process only a bounded number of jobs:

```powershell
python scripts\run_local_queue.py --limit 3
```

To explicitly retry failed jobs:

```powershell
python scripts\run_local_queue.py --retry-failed
```

## Restart behavior

If the process or computer stops while a job is `PREPROCESSING`, the next worker run returns that job to `PENDING`. Partial artifacts under that source's dedicated evidence directory are cleared before the retry. If a complete, valid `evidence_pack.json` already exists, the queue adopts it and marks the job `EVIDENCE_READY` without re-running preprocessing.

## Output

Each successful source is written beneath:

```text
storage/evidence/<SOURCE_ID>/
```

The queue intentionally stops before ALU extraction. Provider-backed semantic processing remains a separate, budget-guarded step.
