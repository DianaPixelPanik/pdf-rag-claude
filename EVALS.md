# EVALS.md — Evaluation Framework

## Philosophy

Evals are the feedback loop that turns a demo into a product. Without them, prompt and pipeline changes are just guesses. This document defines what "good" means for this RAG system and how to measure it automatically.

---

## Metric taxonomy

### 1. Retrieval quality

Measures whether the right chunks are fetched before the LLM sees them.

| Metric | Formula | Target |
|---|---|---|
| Recall@4 | chunks containing answer / total relevant chunks | ≥ 0.80 |
| MRR | mean(1 / rank of first relevant chunk) | ≥ 0.65 |
| Chunk utilisation | retrieved chunks cited in answer / 4 | ≥ 0.50 |

To compute these you need a **labelled retrieval dataset**: question → list of chunk ids that contain the answer. Build it once per representative PDF by manually annotating 50–100 Q&A pairs.

### 2. Answer faithfulness

Measures whether the answer is grounded in the retrieved context (no hallucination).

```
Prompt:
  Context: {context}
  Answer: {answer}

  Does the answer contain any claim NOT supported by the context above?
  Respond with JSON: {"faithful": true/false, "unsupported_claims": [...]}
```

Run this judge call (Claude Haiku for cost) on every eval example. Target: **faithfulness ≥ 0.95**.

### 3. Answer relevance

Measures whether the answer actually addresses the question.

```
Prompt:
  Question: {question}
  Answer: {answer}

  Score how well the answer addresses the question on a scale of 1–5.
  Respond with JSON: {"score": int, "reason": str}
```

Target: **mean score ≥ 4.0**.

### 4. Latency

| Stage | p50 target | p95 target |
|---|---|---|
| Embedding (cold) | < 3 s | < 8 s |
| Retrieval | < 200 ms | < 500 ms |
| LLM first token | < 1 s | < 3 s |
| Total response | < 8 s | < 15 s |

---

## Eval dataset structure

```
evals/
  dataset.jsonl        # canonical eval set
  results/
    YYYY-MM-DD.json    # snapshot per run
```

Each line in `dataset.jsonl`:

```json
{
  "id": "q001",
  "pdf": "annual_report_2024.pdf",
  "question": "What was the revenue in Q3?",
  "reference_answer": "Revenue in Q3 was $4.2M, up 18% YoY.",
  "relevant_chunk_ids": ["chunk_042", "chunk_043"]
}
```

---

## Running evals

```python
# evals/run.py
import json, time
from pathlib import Path

def run_eval(dataset_path: str, api_key: str):
    results = []
    for item in load_jsonl(dataset_path):
        start = time.time()
        answer = query_pipeline(item["question"], item["pdf"], api_key)
        latency = time.time() - start

        faithful = judge_faithfulness(answer, api_key)
        relevance = judge_relevance(item["question"], answer, api_key)

        results.append({
            **item,
            "answer": answer,
            "latency_s": latency,
            "faithful": faithful,
            "relevance_score": relevance,
        })

    save_results(results)
    print_summary(results)
```

Run before and after any prompt or pipeline change:

```bash
python evals/run.py --dataset evals/dataset.jsonl
```

---

## Self-improving loop

```
Eval run → identify failures → categorise root cause → fix → re-eval
```

Root cause taxonomy for this system:

| Code | Cause | Fix |
|---|---|---|
| R1 | Wrong chunks retrieved | Tune chunk size / overlap, or add query rewriting |
| R2 | Answer faithful but incomplete | Increase top-k or add second retrieval pass |
| R3 | Hallucination | Tighten system prompt, add faithfulness check |
| R4 | Answer correct but poorly formatted | Improve output format instructions in prompt |
| R5 | Slow response | Add embedding cache, reduce max_tokens |

Track metric trends across runs in `results/`. A regression on any metric blocks a merge.

---

## Regression gate (CI)

```yaml
# .github/workflows/evals.yml
- name: Run evals
  run: python evals/run.py
- name: Check thresholds
  run: python evals/check_thresholds.py --faithfulness 0.95 --relevance 4.0 --recall 0.80
```

If thresholds are not met, the workflow fails and the change is blocked.
