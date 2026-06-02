# AGENTS.md — KYC Interview Agent Architecture

## Overview

This document describes the agent design behind the KYC onboarding system: how the interview loop works, what decisions the agent makes autonomously, and the roadmap for future improvements.

---

## Current architecture (v1)

```
Session start
     │
     ▼
┌───────────────────────────────────────┐
│  Bootstrap turn                       │
│  Agent receives: empty profile        │
│  Agent responds: greeting + Q1        │
└──────────────────┬────────────────────┘
                   │
                   ▼  (loop)
┌───────────────────────────────────────┐
│  User turn                            │
│  Input to agent:                      │
│    - Profile snapshot (filled fields) │
│    - Missing fields list              │
│    - Client's latest message          │
│  Agent decides:                       │
│    - What to extract from the answer  │
│    - What to ask next                 │
│    - Whether a document is needed     │
│    - Whether interview is complete    │
└──────────────────┬────────────────────┘
                   │
          ┌────────┴────────┐
          │                 │
    needs_document?      status=complete?
          │                 │
          ▼                 ▼
  ┌──────────────┐   ┌─────────────────┐
  │ File upload  │   │ Review summary  │
  │ PDF → text   │   │ Doc / PEP / Risk│
  │ → agent turn │   └─────────────────┘
  └──────────────┘
```

### Agent response contract

Every agent response is strict JSON — no prose, no markdown:

```json
{
  "message": "conversational message to the client",
  "extracted": {"field_name": "value"},
  "needs_document": "id" | "proof_of_address" | null,
  "status": "ongoing" | "complete"
}
```

The agent operates as a **structured extraction machine** wrapped in a conversational persona. The JSON contract enforces machine-readable output while the system prompt shapes tone and sequencing.

### Key design choices

| Decision | Rationale |
|---|---|
| Profile snapshot in every user turn | Agent always has full context; no long-term memory needed |
| Missing fields list in prompt | Prevents agent from re-asking collected questions |
| JSON-only response format | Enables deterministic field extraction without NLP parsing |
| `max_tokens=1024` | Interview responses are short; limits cost and latency |
| `temperature` default (1.0) | Conversational variation is desirable; lower temp makes answers robotic |
| Regex fallback for JSON parse | Handles rare cases where Claude wraps JSON in markdown fences |

---

## Interview state machine

```
INIT → ONGOING → COMPLETE
          │
          ├── pending_document: "id"
          │       └── after upload → ONGOING
          └── pending_document: "proof_of_address"
                  └── after upload → ONGOING
```

State lives in `st.session_state`. Fields:

| Key | Type | Description |
|---|---|---|
| `profile` | dict | 15 KYC fields, None until collected |
| `history` | list | Visible chat (agent / user / document bubbles) |
| `api_msgs` | list | Full Anthropic messages array |
| `status` | str | `"ongoing"` or `"complete"` |
| `pending_doc` | `str\|None` | Document type currently awaited |
| `docs_uploaded` | `set[str]` | Prevents showing uploader after submit |

---

## Post-interview review

After `status=complete`, three statuses are computed deterministically from the profile (no LLM call):

**Document verification** — parses `document_expiry` field, compares to today:
- `< today` → Expired (fail)
- `< 90 days` → Expiring soon (warn)
- otherwise → Valid (ok)

**PEP review** — checks `pep_status` for "yes":
- match → Required (fail)
- no match → Cleared (ok)

**Risk review** — derived from the above:
- any fail flag → Elevated — manual review (warn)
- all clear → Pending (manual gate, never auto-approved)

Risk review is intentionally a manual gate. The system flags; a human approves.

---

## Limitations of v1

1. **Re-reads PDFs on every document turn** — no caching of extracted text.
2. **No cross-field validation** — agent does not catch inconsistencies (e.g., name on document ≠ declared name).
3. **No liveness / authenticity check** — document text is trusted as-is.
4. **Single language** — system prompt is in English; client answers in other languages are handled by Claude's multilingual capability but not formally tested.
5. **No session persistence** — profile is lost on browser refresh.

---

## Roadmap (v2)

**Cross-field validation turn** — after document upload, run a dedicated Claude call:
```
Compare the following declared profile with the extracted document content.
List any discrepancies.
```

**Multilingual support** — detect client language from first message, switch system prompt language.

**Session persistence** — write profile to SQLite on every turn; resume from last state on reconnect.

**Sanctions screening hook** — after profile is complete, call a sanctions/PEP API (e.g., Comply Advantage) and surface results alongside the manual risk review status.
