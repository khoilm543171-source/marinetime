# Claude API setup for Marinetime

## Secret rule
Never paste the API key into chat, source code, prompts, logs, screenshots, or Git commits.
Store it in a local `.env` file that is ignored by Git.

## Setup

```bash
cp .env.example .env
```

Edit only your local `.env`:

```env
CLAUDE_PROVIDER=nghimmo
CLAUDE_API_KEY=YOUR_PRIVATE_KEY
CLAUDE_BASE_URL=https://api.nghimmo.com
CLAUDE_MODEL=nghi/claude-opus-5
```

Then install the MVP package:

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

python -m pip install -e .
```

Run the tiny connectivity test (this consumes a very small API call):

```bash
python scripts/check_claude_connection.py
```

Expected shape:

```text
CONNECTED
provider=nghimmo
model=...
response=MARINETIME_OK
input_tokens=...
output_tokens=...
```

## Runtime path

```text
EvidencePack
  -> LLM Router
  -> token preflight guard
  -> ClaudeClient
  -> Claude/Opus API
  -> response usage log
  -> JSON/schema validation
  -> deterministic safety validation
  -> accepted artifact
```

The router is the only intended runtime doorway to Claude. Domain modules should not create random HTTP calls to the provider.

## Why there are three instruction layers
- `CLAUDE.md`: tiny always-on coding-agent brain.
- `RULES.md`: detailed engineering reference, loaded only for relevant changes.
- `.claude/skills/*/SKILL.md`: task-specific rules loaded only when needed.

Runtime API prompts live separately under `prompts/`. Do not send `CLAUDE.md`, `RULES.md`, and every Skill to the API on each request.
