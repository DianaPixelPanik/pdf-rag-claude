# KYC Interview Agent

A Streamlit app that conducts automated KYC (Know Your Customer) onboarding interviews powered by **Anthropic Claude** (claude-sonnet-4-6).

The agent asks questions, collects identity documents, detects risk flags (expired docs, PEP status), and builds a structured client profile — all through natural conversation.

## Features

- Conversational onboarding interview driven by Claude
- Collects 15 required KYC fields one question at a time
- Requests document uploads (ID, proof of address) at the right moment
- Extracts field values directly from uploaded PDFs
- Real-time profile sidebar with completeness progress bar
- Multi-status review panel: Document verification / PEP review / Risk review
- Audit log (`audit.jsonl`) — records every turn, document upload, and completion event
- Export completed profile as JSON

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/DianaPixelPanik/pdf-rag-claude.git
cd pdf-rag-claude
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set your API key

```bash
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env
```

Or enter it directly in the sidebar when the app runs.

### 4. Run the app

```bash
streamlit run app.py
```

## How it works

```
Agent greets client
       │
       ▼
Ask one question → extract answer → update profile
       │
       ▼ (when identity info needed)
Request document upload → extract PDF text → verify with Claude
       │
       ▼
Repeat until all 15 fields collected
       │
       ▼
Generate review summary:
  Profile completeness   100%
  Document verification  Valid / Expired / Expiring soon
  PEP review             Cleared / Required
  Risk review            Pending / Elevated
```

## Collected profile fields

| Field | Description |
|---|---|
| full_name | Full legal name |
| date_of_birth | DD/MM/YYYY |
| nationality | Country of citizenship |
| country_of_residence | Current country |
| address | Full residential address |
| phone | Contact phone |
| email | Contact email |
| document_type | passport / national ID / driver's license |
| document_number | ID document number |
| document_expiry | Expiry date |
| occupation | Job title |
| employer | Employer name |
| source_of_funds | Salary / business / investments / other |
| pep_status | Politically Exposed Person — yes or no |
| account_purpose | Purpose of opening account |

## Review statuses

The system separates **data collection** from **compliance review**. A 100% complete profile does not mean it is approved.

| Status | Logic |
|---|---|
| Document verification | Parses expiry date; flags expired or expiring within 90 days |
| PEP review | Flags "Required" if pep_status contains "yes" |
| Risk review | Elevated automatically if document or PEP flags are active |

## Tech Stack

| Component | Library |
|---|---|
| UI | Streamlit |
| LLM | Anthropic Claude (claude-sonnet-4-6) |
| PDF parsing | PyPDF2 |
| Secrets | python-dotenv / st.secrets |

## Deployment

The app supports Streamlit Community Cloud out of the box. Set `ANTHROPIC_API_KEY` in the Secrets section of your app settings.

For a quick public URL without any account:

```bash
cloudflared tunnel --url http://localhost:8501
```

## Audit log

Every session writes to `audit.jsonl` (excluded from git). Each line is a JSON event:

```json
{"timestamp": "...", "event": "turn", "client": "...", "agent": "...", "extracted": {}, "profile": {}}
{"timestamp": "...", "event": "document_upload", "doc_type": "id", "filename": "passport.pdf", "extracted": {}}
{"timestamp": "...", "event": "interview_complete", "profile": {}, "review_statuses": {}}
```

## Get an API Key

Sign up at [console.anthropic.com](https://console.anthropic.com).

## License

MIT
