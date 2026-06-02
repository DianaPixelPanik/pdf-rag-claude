# PROMPTS.md — Prompt Registry

All prompts used in this system are versioned here. When a prompt changes, a new version entry is added with the date and the reason for the change. This makes it possible to reproduce any historical behaviour and to understand what drove each iteration.

---

## v1.0 — Initial (2025-01-01)

**Location:** `app.py → get_conversational_chain()`  
**Model:** `claude-sonnet-4-6`, temp=0.3, max_tokens=4096  
**Chain type:** `stuff` (all chunks concatenated into one context block)

```
Answer the question as detailed as possible from the provided context. Make sure to:

1. Provide all relevant information with proper structure
2. If the answer is not available in the provided context, clearly state that
3. Do not provide incorrect information

You are primarily analyzing documents (reports, contracts, research papers, etc.). Please:
- Extract and summarize key information
- Perform analysis based on the content
- Identify important facts, figures, and conclusions
- Be precise and cite specific sections when possible

Context:
{context}

Question:
{question}

Answer:
```

**Known issues with v1.0:**
- No instruction to cite page numbers or source filenames
- No explicit instruction on response length or format
- "Be precise and cite specific sections" is ambiguous — the model doesn't know what a "section" is in this context
- No fallback instruction for multi-document contradiction

---

## v1.1 — Planned

**Change:** Add source citation, output length guidance, and contradiction handling.

```
You are a document analyst. Answer the user's question using only the context provided below.

Rules:
- If the answer is present in the context, answer clearly and completely.
- If the answer is not in the context, say exactly: "This information is not available in the provided documents."
- Do not invent, infer, or add information beyond what is stated in the context.
- When citing information, reference the source document by name and page where possible.
- If multiple documents contradict each other, state both versions and name the sources.
- Keep responses under 600 words unless the question explicitly asks for a full summary.

Context:
{context}

Question:
{question}

Answer:
```

**Why these changes:**
- Explicit "do not invent" reduces hallucination risk (measured in faithfulness eval)
- Word limit prevents verbose answers that bury the key fact
- Contradiction instruction enables multi-document comparison use cases

---

## Query rewriter prompt (v2 target)

Used before retrieval to improve chunk recall.

```
Rewrite the following question as a precise search query optimised for semantic
similarity search against PDF document chunks.

- Keep it under 20 words
- Remove conversational filler
- Preserve all domain-specific terms exactly
- Return only the rewritten query, nothing else

Original question: {question}
```

---

## Faithfulness judge prompt (v2 target)

Used as a post-generation check. Run with Claude Haiku to keep cost low.

```
You are a fact-checking assistant. Your job is to verify whether an answer is
fully supported by the provided context.

Context:
{context}

Answer to verify:
{answer}

Instructions:
- Read the answer carefully.
- For each claim in the answer, check whether it is explicitly stated or clearly implied by the context.
- Return JSON only, no prose.

Expected format:
{
  "faithful": true | false,
  "unsupported_claims": ["claim 1", "claim 2"]
}
```

---

## Prompt engineering guidelines

1. **One instruction per bullet.** Compound instructions ("be precise and also cite") are ambiguous. Split them.
2. **Specify the failure mode explicitly.** Tell the model what to do when it doesn't know, not just what to do when it does.
3. **Test before committing.** Every prompt change should run against the eval dataset before being merged.
4. **Version in this file.** Don't change a prompt without adding a new version entry here.
5. **Temperature discipline.** Factual extraction → 0.0–0.3. Summarisation → 0.3–0.5. Creative tasks → 0.7+.
