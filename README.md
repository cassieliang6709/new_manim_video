# Visocode

An AI-powered pipeline that turns natural language descriptions into Manim animation videos — with an agentic retry loop, LLM-as-Judge quality audit, and RAG-enhanced code generation.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-agentic-orange)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-red)
![Gemini](https://img.shields.io/badge/LLM-Gemini%202.5-green)

---

## What It Does

1. User describes an animation in plain English (e.g. *"visualize bubble sort step by step"*)
2. Gemini 2.5 Pro generates Manim Python code
3. An **LLM Judge** audits the code for quality before execution
4. Code runs inside a **Docker sandbox** (`manimcommunity/manim`) — isolated, no network, memory-limited
5. On failure, a **debugger node** compresses the traceback, looks up relevant Manim API docs, and prompts Gemini to fix the code
6. The final `.mp4` is uploaded to **Google Drive**

---

## Architecture

```
User Prompt
    │
    ▼
generate_node  ◄──────────────────────────────────────┐
    │  (Gemini 2.5 Pro + RAG few-shot examples)        │
    ▼                                                   │
audit_node                                             │
    │  (LLM Judge: Gemini 2.5 Flash)                  │
    ├── FAIL (≥3 retries) ──► fallback_node            │
    ▼                                                   │
execute_node                                           │
    │  (Docker sandbox: manimcommunity/manim)          │
    ├── success ──► upload_node ──► DONE               │
    └── failure ──► debugger_node ──────────────────────┘
                    (ApiLookup: error-driven doc injection)
```

**Key design decisions:**
- `audit_retry_count` cap prevents infinite LLM Judge loops (was root cause of `GraphRecursionError`)
- RAG retrieves similar successful past scenes as few-shot examples on first attempt
- `ApiLookup` injects precise Manim API docs (from `manim_api_index.json`) based on the specific symbol that caused a `NameError` / `AttributeError`
- Traceback compression (`_compress_traceback`) extracts key signals to reduce LLM context noise

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) StateGraph |
| LLM | Gemini 2.5 Pro (generation) + Gemini 2.5 Flash (judge) |
| Execution sandbox | Docker (`manimcommunity/manim`) |
| RAG — few-shot | `sentence-transformers` (`all-MiniLM-L6-v2`) over `runs.json` |
| RAG — API lookup | Hand-curated `manim_api_index.json` (57 entries) |
| UI | Streamlit |
| Storage | Google Drive API |

---

## Getting Started

### Prerequisites

- Python 3.10+
- Docker Desktop running locally
- Gemini API key ([get one here](https://aistudio.google.com/apikey))
- (Optional) Google Cloud project with Drive API enabled

### Installation

```bash
git clone https://github.com/YOUR_USERNAME/visocode.git
cd visocode

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt

# Pull the Manim Docker image (one-time, ~2 GB)
docker pull manimcommunity/manim
```

### Configuration

```bash
cp .env.example .env
# Edit .env with your GEMINI_API_KEY
```

For Google Drive upload, place your `client_secrets.json` in the project root (downloaded from Google Cloud Console → OAuth 2.0 credentials). On first run, a browser window will open for authorization.

### Run

```bash
streamlit run app.py
```

---

## Project Structure

```
visocode/
├── app.py                  # Streamlit UI + session management
├── orchestrator.py         # LangGraph workflow (main pipeline)
├── executor.py             # Docker sandbox + LocalExecutor
├── auditor.py              # LLM Judge + AST security auditor
├── generator.py            # Manim code generator (legacy, kept for reference)
├── retriever.py            # RAG: RunsRetriever + ApiLookup
├── uploader.py             # Google Drive upload
├── manim_api_index.json    # Hand-curated Manim API reference (57 entries)
├── requirements.txt
├── .env.example
└── docs/
    ├── PRESENTATION_SLIDES.md      # 20-min technical interview presentation
    ├── INTERVIEW_QUESTIONS.md      # 17 interview Q&A (system design, LLM, security)
    └── RAG_AND_AGENTIC_STRATEGY.md # RAG & agentic workflow design notes
```

---

## RAG System

Two complementary retrieval strategies:

**1. Few-shot retrieval (generation time)**
- Embeds past successful `runs.json` entries using `sentence-transformers`
- Top-2 similar scenes injected as examples into the generation prompt
- Cold start: gracefully returns empty list (zero-shot fallback)

**2. Error-driven API lookup (debug time)**
- Extracts symbol names from `NameError` / `AttributeError` / `ImportError` tracebacks
- Looks up matching entries in `manim_api_index.json`
- Injects precise signature + example into the debugger hint

---

## License

MIT
