# EVALS.md — Evaluation Framework

## Philosophy

A KYC agent has two failure modes that matter in production:

1. **Under-collection** — the interview ends without all required fields. Compliance gap.
2. **Wrong extraction** — the agent extracts an incorrect value and it enters the profile undetected. Fraud or regulatory risk.

Evals exist to catch both before they reach real clients.

---

## Metric taxonomy

### 1. Field collection rate

Measures whether the interview terminates with all 15 fields populated.

| Metric | Definition | Target |
|---|---|---|
| Completion rate | interviews where status=complete / total interviews | ≥ 0.95 |
| Fields per session | mean filled fields at completion | 15.0 |
| Turn efficiency | mean turns to complete interview | ≤ 20 |

### 2. Extraction accuracy

Measures whether extracted field values match the ground truth.

```
For each (question, client_answer, expected_extracted_fields) tuple:
  run agent turn → compare extracted{} to expected{}
```

| Metric | Definition | Target |
|---|---|---|
| Field-level accuracy | correct extractions / total extractions | ≥ 0.95 |
| False positives | fields extracted when client did not provide them | ≤ 0.02 |
| Date format compliance | date fields in DD/MM/YYYY | ≥ 0.90 |

### 3. Document extraction accuracy

Measures whether the agent correctly pulls structured fields from PDF text.

| Field | Expected source | Target accuracy |
|---|---|---|
| document_number | ID document | ≥ 0.95 |
| document_expiry | ID document | ≥ 0.95 |
| full_name | ID document (cross-check) | ≥ 0.90 |
| address | Proof of address | ≥ 0.85 |

### 4. Review status correctness

Measures the deterministic post-interview logic (no LLM involved — these should be 1.0):

| Check | Logic | Expected |
|---|---|---|
| Expired doc detected | expiry < today → fail | 1.0 |
| PEP flag raised | "yes" in pep_status → fail | 1.0 |
| Risk elevated on fail | any fail → warn | 1.0 |

### 5. Latency

| Stage | p50 target | p95 target |
|---|---|---|
| Agent turn (LLM) | < 2 s | < 5 s |
| Document processing (PDF + LLM) | < 4 s | < 10 s |
| Total interview duration | < 5 min | < 10 min |

---

## Eval dataset structure

```
evals/
  dataset.jsonl        # canonical eval set
  documents/           # sample PDF fixtures
  results/
    YYYY-MM-DD.json    # snapshot per run
```

Each line in `dataset.jsonl` represents one agent turn:

```json
{
  "id": "t001",
  "scenario": "standard_onboarding",
  "profile_before": {"full_name": null, ...},
  "client_message": "My name is Jane Smith, born 15 June 1985.",
  "expected_extracted": {
    "full_name": "Jane Smith",
    "date_of_birth": "15/06/1985"
  },
  "expected_needs_document": null,
  "expected_status": "ongoing"
}
```

Document eval entries include `document_pdf_path` and `expected_extracted_from_doc`.

---

## Test scenarios

| Scenario | Purpose |
|---|---|
| Standard onboarding | Happy path — cooperative client, valid docs |
| PEP client | Verify PEP flag is raised and review status set correctly |
| Expired document | Verify expiry detection |
| Near-expiry document | Verify 90-day warning |
| Multilingual client | Client answers in Russian / French — fields extracted correctly |
| Incomplete answers | Client gives vague answers — agent asks follow-up |
| Adversarial PDF | Document contains prompt injection attempt |
| Name mismatch | Declared name differs from document name |

---

## Running evals

```python
# evals/run.py
import json, time

def run_eval(dataset_path: str, api_key: str):
    results = []
    for item in load_jsonl(dataset_path):
        start = time.time()
        result = agent_turn_isolated(
            client_text=item["client_message"],
            profile=item["profile_before"],
            api_key=api_key,
        )
        latency = time.time() - start

        extracted_match = result["extracted"] == item["expected_extracted"]
        doc_match = result.get("needs_document") == item["expected_needs_document"]
        status_match = result["status"] == item["expected_status"]

        results.append({
            **item,
            "result": result,
            "latency_s": round(latency, 2),
            "extracted_match": extracted_match,
            "doc_match": doc_match,
            "status_match": status_match,
        })

    save_results(results)
    print_summary(results)
```

---

## Self-improving loop

```
Eval run → failures → root cause → fix prompt or code → re-eval
```

Root cause taxonomy:

| Code | Cause | Fix |
|---|---|---|
| E1 | Field not extracted despite being in answer | Add extraction example to prompt |
| E2 | Wrong field extracted (e.g., DOB into name) | Add field format hints to prompt |
| E3 | Agent asks for already-collected field | Check missing fields list injection |
| E4 | Date format non-compliant | Add format normalisation in `parse_date()` |
| E5 | `needs_document` not triggered | Review document-request rules in prompt |
| E6 | `status=complete` with missing fields | Tighten completion condition in prompt |
| E7 | Prompt injection from document succeeded | Add `<document_context>` delimiter to prompt |

---

## Regression gate (CI)

```yaml
# .github/workflows/evals.yml
- name: Run KYC evals
  run: python evals/run.py --dataset evals/dataset.jsonl
- name: Check thresholds
  run: python evals/check_thresholds.py \
    --completion-rate 0.95 \
    --extraction-accuracy 0.95 \
    --review-status-accuracy 1.0
```

A regression on any metric blocks the merge.
