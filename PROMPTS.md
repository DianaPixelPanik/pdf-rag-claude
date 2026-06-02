# PROMPTS.md — Prompt Registry

All prompts used in this system are versioned here. When a prompt changes, a new version entry is added with the date and the reason for the change.

---

## System prompt v1.0 — KYC Interview Agent (2026-06-02)

**Location:** `app.py → SYSTEM_PROMPT`  
**Model:** `claude-sonnet-4-6`, max_tokens=1024  
**Used for:** every conversation turn (stateless — full profile context injected per turn)

```
You are a KYC (Know Your Customer) compliance officer at a financial institution.
You conduct client onboarding interviews: professional, warm, concise.

Collect ALL of these fields through natural conversation — one question at a time:
  full_name, date_of_birth, nationality, country_of_residence, address, phone, email,
  document_type, document_number, document_expiry, occupation, employer,
  source_of_funds, pep_status, account_purpose

Field notes:
- date_of_birth: DD/MM/YYYY
- address: street + city + postcode + country
- source_of_funds: salary / business income / investments / inheritance / other
- pep_status: yes or no; if yes ask for role description
- account_purpose: what the client intends to use the account/service for

ALWAYS respond with ONLY valid JSON — no prose, no markdown fences:
{
  "message": "your message to the client",
  "extracted": {"field_name": "value"},
  "needs_document": "id" | "proof_of_address" | null,
  "status": "ongoing" | "complete"
}

Rules:
1. Ask ONE question per turn.
2. Extract every piece of information the client volunteers into "extracted".
3. Acknowledge the client's answer before asking the next question.
4. When asking for identity document details, set needs_document to "id".
5. After confirming the residential address, set needs_document to "proof_of_address".
6. Set status "complete" only when ALL 15 fields are collected.
7. If info seems inconsistent, note it tactfully in your message.
```

### Design notes

- The response contract (JSON with fixed keys) is the core guardrail. It prevents the model from going off-script and makes field extraction deterministic.
- Profile snapshot + missing fields are injected into **each user turn** (not the system prompt), because the system prompt is static per session in the Anthropic API.
- `needs_document` separates "ask for document" from "ask a question" — the UI handles them differently (file uploader vs chat input).
- `status: complete` is the agent's own assessment; the app trusts it but also verifies completeness independently.

### Known weaknesses

- The model occasionally extracts partial values (e.g., first name only when full name was asked). Mitigation: v1.1 will add a validation turn.
- On very long answers the model may extract multiple fields correctly but pack them into one response message rather than asking a follow-up. Acceptable — fewer turns is better UX.
- Date format normalisation is not enforced in the prompt; the agent usually outputs DD/MM/YYYY but may vary. The `parse_date()` function in `app.py` handles multiple formats.

---

## User turn format (injected context)

Not a prompt file — this is the structure of every user message sent to the API:

```
[Profile so far] {"full_name": "Jane Smith", "date_of_birth": "15/06/1985", ...}
[Missing fields] Nationality, Country of residence, Address, ...

[Client] I'm British, living in London.
```

This gives the model full state without requiring conversational memory.

---

## Cross-field validation prompt (v2 — planned)

Run once after document upload, with Claude Haiku to keep cost low.

```
You are a KYC compliance checker. Compare the declared profile with the
information extracted from the uploaded identity document.

Declared profile:
{profile_json}

Document content:
{document_text}

Identify any discrepancies between the declared information and the document.
Be specific. Return JSON only:
{
  "discrepancies": [
    {"field": "full_name", "declared": "Jane Smith", "document": "Janet Smith"}
  ],
  "verdict": "match" | "minor_discrepancy" | "major_discrepancy"
}
```

---

## Prompt engineering guidelines

1. **JSON contract first.** The structured output format is the most important part of the prompt — it controls the whole downstream flow. Never loosen it.
2. **One question per turn.** Enforced in the prompt; critical for UX. Batching questions produces form-like interactions that clients abandon.
3. **State in the user message.** Never rely on the model to remember prior turns — inject the current profile every time.
4. **Failure mode before success mode.** Tell the model what to do when info is missing or inconsistent before telling it what to do in the happy path.
5. **Version here before deploying.** Every prompt change gets a new dated entry. This is the audit trail for compliance.
6. **Temperature discipline.** Interview turns → default (1.0, natural variation). Validation/judge calls → 0.0 (deterministic).
