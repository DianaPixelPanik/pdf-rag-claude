# AGENTS.md — PDF RAG Agent Architecture

## Overview

This document describes the agent pipeline behind the PDF Analyser, the design decisions made at each stage, and the roadmap for evolving it from a single-turn RAG into a self-correcting, multi-step agent.

---

## Current Pipeline (v1)

```
User question
     │
     ▼
┌─────────────────────────────┐
│  1. PDF Ingestion           │  PyPDF2 → raw text
│  2. Chunking                │  RecursiveCharacterTextSplitter (10k / 1k overlap)
│  3. Embedding               │  HuggingFace all-MiniLM-L6-v2 (local, free)
│  4. Vector Store            │  FAISS (saved to disk)
│  5. Retrieval               │  similarity_search (top-k = 4)
│  6. Prompt Assembly         │  stuff-chain: context + question → prompt
│  7. LLM Call                │  Claude claude-sonnet-4-6 (temp=0.3, max_tokens=4096)
│  8. Response                │  streamed to Streamlit UI
└─────────────────────────────┘
```

### Key design choices

| Decision | Rationale |
|---|---|
| Local embeddings (MiniLM) | No extra API cost; good enough for semantic retrieval on domain docs |
| FAISS over cloud vector DB | Simpler ops for single-user app; no latency to external store |
| `stuff` chain type | Documents fit in context window; no summarization overhead |
| `temperature=0.3` | Factual extraction tasks benefit from lower randomness |
| Overlap of 1 000 chars | Prevents answers from being split across chunk boundaries |

---

## Limitations of v1

1. **Re-embeds on every question** — `get_vector_store` is called each time a question is submitted, even if the PDFs haven't changed. Cost: ~2–5 s per query on CPU.
2. **No query rewriting** — user's raw question goes straight to retrieval; ambiguous or short queries return poor chunks.
3. **Single retrieval pass** — no re-ranking, no second-pass verification.
4. **No citation grounding** — response doesn't reference page numbers or chunk sources.
5. **No memory across sessions** — conversation history lives in `st.session_state` only.

---

## Target Pipeline (v2 — Agentic RAG)

```
User question
     │
     ▼
┌──────────────────────┐
│  Query Rewriter      │  LLM rewrites question for better retrieval
└─────────┬────────────┘
          │
          ▼
┌──────────────────────┐
│  Retriever           │  FAISS similarity_search (top-k = 8)
└─────────┬────────────┘
          │
          ▼
┌──────────────────────┐
│  Re-ranker           │  Cross-encoder scores chunks → keep top 4
└─────────┬────────────┘
          │
          ▼
┌──────────────────────┐
│  Answer Generator    │  Claude with grounding prompt
└─────────┬────────────┘
          │
          ▼
┌──────────────────────┐
│  Faithfulness Check  │  Claude verifies answer is supported by chunks
└─────────┬────────────┘
          │
     ┌────┴────┐
   PASS      FAIL → re-trigger with "answer must stay within context" instruction
     │
     ▼
  Final response with source citations
```

### New components

**Query Rewriter** — a small Claude call before retrieval:
```
Given the user's question, rewrite it as a precise search query
optimised for semantic similarity against PDF document chunks.
Return only the rewritten query.
```

**Faithfulness Check** — a binary post-generation check:
```
Does the following answer contain only information present in the provided context?
Answer YES or NO, then list any unsupported claims.
```
If `NO` → retry with stricter constraint in the prompt.

**Source citations** — each retrieved chunk should carry metadata:
- `source` (filename)
- `page` (page number from PyPDF2 `page_number` attribute)
- `chunk_id`

These are surfaced in the response as footnotes.

---

## Caching strategy

To fix re-embedding on every query:

```python
@st.cache_resource
def build_vector_store(file_hashes: tuple[str, ...]):
    # keyed on MD5 of each uploaded file
    ...
```

Cache is invalidated only when the set of uploaded files changes.

---

## Multi-document reasoning

When multiple PDFs are loaded, retrieval should be aware of document identity so the model can compare across sources:

```
Context from "contract_v1.pdf" (p.3):
...

Context from "contract_v2.pdf" (p.3):
...

Question: What changed between the two versions?
```

This requires tagging chunks with their source at ingestion time.
