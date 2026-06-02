# 📚 PDF RAG Analyser — powered by Claude

A Streamlit app that lets you upload multiple PDFs and chat with them using **Anthropic Claude** (claude-sonnet-4-6) and local HuggingFace embeddings (no extra embedding API needed).

## Features

- Upload multiple PDF files at once
- Ask questions in natural language
- Answers grounded in your documents via RAG (FAISS + HuggingFace embeddings)
- Conversation history with CSV export
- Powered by Claude Sonnet — fast and accurate

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/pdf-rag-claude.git
cd pdf-rag-claude
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

> First run downloads the `all-MiniLM-L6-v2` embedding model (~90 MB) automatically.

### 3. Set your API key

Copy `.env.example` to `.env` and add your key:

```bash
cp .env.example .env
```

```env
ANTHROPIC_API_KEY=sk-ant-...
```

Or enter it directly in the sidebar when the app runs.

### 4. Run the app

```bash
streamlit run app.py
```

## How it works

1. **Upload PDFs** → text extracted with PyPDF2
2. **Chunking** → split into 10 000-character chunks with 1 000-character overlap
3. **Embeddings** → `all-MiniLM-L6-v2` via HuggingFace (runs locally, free)
4. **Vector store** → FAISS index saved locally
5. **Query** → top relevant chunks retrieved, sent to Claude with your question
6. **Answer** → Claude responds based only on your documents

## Tech Stack

| Component | Library |
|-----------|---------|
| UI | Streamlit |
| LLM | Anthropic Claude (claude-sonnet-4-6) |
| Embeddings | HuggingFace `all-MiniLM-L6-v2` |
| Vector store | FAISS |
| PDF parsing | PyPDF2 |
| LLM framework | LangChain |

## Get an API Key

Sign up at [console.anthropic.com](https://console.anthropic.com) to get your Anthropic API key.

## License

MIT
