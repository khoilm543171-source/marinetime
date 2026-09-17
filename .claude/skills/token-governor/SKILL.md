---
name: token-governor
description: Use before changing or implementing any Claude/LLM call, prompt, retry loop, context assembly, model routing, token budget, or usage logging in Marinetime.
---
# Token Governor

Goal: maximize useful Marine Engineering knowledge per token.

Before an LLM call, check in this order:
1. Can deterministic/local code do it?
2. Does a processed artifact already exist?
3. Can retrieval provide a smaller context?
4. Is the requested model strength necessary?
5. Will this call stay inside hard limits?

Rules:
- Never send whole Drive folders, databases, unrelated transcripts, old chats, duplicate frames, or full artifacts when IDs/slices are enough.
- Machine-to-machine output should be compact structured JSON.
- Keep static instructions stable and dynamic evidence separate.
- One automatic retry maximum, only for transport/schema failure.
- Do not retry a semantically bad answer blindly; create a FeedbackReport or targeted recovery task.
- Log input/output usage and accepted ALUs, not just call count.
- Stop immediately when acceptance criteria are met.
