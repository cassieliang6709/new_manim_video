# Visocode

> **Natural language → Manim animation video, in under 30 seconds.**

Visocode is a production-grade AI pipeline that transforms plain English descriptions into rendered mathematical animation videos (`.mp4`). It combines **LangGraph** agentic orchestration, **dual-layer code auditing**, **Docker sandbox isolation**, **two-tier RAG**, and **Google Drive auto-upload** — with automatic self-correction when generation fails.

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-agentic%20DAG-orange)
![Gemini](https://img.shields.io/badge/LLM-Gemini%202.5%20Pro%2FFlash-green)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-red)
![Docker](https://img.shields.io/badge/Sandbox-Docker-2496ED)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## Demo

| Input | Output |
|-------|--------|
| *"Visualize bubble sort step by step"* | Rendered `.mp4` with animated comparison + swap operations |
| *"Show the Fourier series approximation of a square wave"* | Animated sum of sinusoids converging to a square wave |
| *"Explain the Pythagorean theorem visually"* | Right triangle with labeled sides + area squares |

---

## How It Works

```
User types: "Visualize Fibonacci as a growing bar chart"
                        │
                        ▼
         ┌──────────────────────────┐
         │      generate_node       │  ← Gemini 2.5 Pro
         │  RAG: few-shot examples  │  ← Top-2 similar past successes
         │  from runs.json via      │    (sentence-transformers)
         │  sentence-transformers   │
         └────────────┬─────────────┘
                      │
                      ▼
         ┌──────────────────────────┐
         │       audit_node         │  ← Layer 1: AST security scan
         │  SecurityAuditor (AST)   │    (blocks os, subprocess, eval…)
         │  LLMJudgeAuditor (Flash) │  ← Layer 2: Gemini Flash PASS/FAIL
         └────────────┬─────────────┘
              PASS    │    FAIL (≥3 retries)
                      │         └──► fallback_node (safe minimal scene)
                      ▼
         ┌──────────────────────────┐
         │      execute_node        │  ← Docker: manimcommunity/manim
         │  SandboxExecutor         │    no network · 1 GB RAM · 120s limit
         └────────────┬─────────────┘
          success     │    failure
              │       └──► debugger_node
              │              ├─ compress traceback → structured signal
              │              ├─ Gemini Flash: DIAGNOSIS + FIX (2 lines)
              │              ├─ ApiLookup: inject exact Manim API doc
              │              └─ loop back to generate_node (max 3x)
              ▼
         ┌──────────────────────────┐
         │      upload_node         │  ← Google Drive (OAuth or service acct)
         └────────────┬─────────────┘
                      │
                      ▼
         Video player · Drive link · Download button
```

**Key reliability guarantees:**
- Separate `audit_retry_count` and `retry_count` caps prevent infinite loops (`GraphRecursionError`)
- Hard recursion limit (50 steps) as a safety valve
- Fallback node always produces output — users never see a blank result
- Traceback compressed to ≤200 chars before sending to LLM, reducing context noise

---

## Features

| Feature | Detail |
|---------|--------|
| **Natural language input** | Plain English → working Manim animation |
| **Agentic retry loop** | Auto-corrects on audit or execution failure, up to 3 retries |
| **Dual-layer audit** | AST security check + Gemini Flash semantic judge |
| **Docker sandbox** | No network, 1 GB RAM cap, 0.5 CPU, 120 s timeout |
| **Two-tier RAG** | Few-shot from past successes + error-driven Manim API injection |
| **Error-driven API lookup** | NameError → exact signature + example from `manim_api_index.json` |
| **Visual style presets** | Minimalist Dark, Classic Blackboard, Futuristic Tech |
| **Google Drive upload** | Public "view-only" link auto-generated after render |
| **First-try success tracking** | Persisted to `runs.json`, displayed in sidebar |
| **Fallback scene** | Safe minimal animation rendered when max retries exceeded |
| **CLI mode** | `python run.py "description"` — no UI required |
| **VPS one-command deploy** | `bash deploy.sh` on any Linux VPS with Docker |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) `StateGraph` DAG |
| Code generation | Gemini 2.5 Pro (`langchain-google-genai`) |
| Code auditing | Gemini 2.5 Flash (LLM Judge) + Python `ast` (SecurityAuditor) |
| Execution sandbox | Docker (`manimcommunity/manim:latest`) |
| RAG — few-shot | `sentence-transformers` `all-MiniLM-L6-v2` over `runs.json` |
| RAG — API lookup | Hand-curated `manim_api_index.json` (57 entries) |
| UI | Streamlit |
| Cloud storage | Google Drive API v3 (OAuth 2.0 + service account) |
| Container runtime | Docker Engine + Docker-in-Docker via socket mount |

---

## Project Structure

```
visocode/
├── app.py                   # Streamlit UI, session state, run history
├── orchestrator.py          # LangGraph StateGraph: 6 nodes, conditional routing
├── executor.py              # SandboxExecutor (Docker) + LocalExecutor (subprocess)
├── auditor.py               # SecurityAuditor (AST) + LLMJudgeAuditor (Gemini Flash)
├── generator.py             # Data structures: SceneDescription, GeneratedCode
├── retriever.py             # RunsRetriever (few-shot) + ApiLookup (error-driven)
├── uploader.py              # DriveUploader (service acct) + DriveUploaderOAuth (personal)
├── run.py                   # CLI entry point
├── manim_api_index.json     # Hand-curated Manim API reference (57 entries)
├── deploy.sh                # One-command VPS deployment script
├── Dockerfile               # App container (python:3.11-slim + Streamlit)
├── docker-compose.yml       # Multi-container: app + Docker socket mount
├── requirements.txt
├── pages/
│   └── 2_Presentation.py   # 9-slide interactive technical presentation
└── docs/
    ├── ARCHITECTURE.md
    ├── RAG_AND_AGENTIC_STRATEGY.md
    ├── INTERVIEW_QUESTIONS.md
    └── DRIVE_OAUTH_SETUP.md
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Docker Desktop (running)
- [Gemini API key](https://aistudio.google.com/apikey)
- (Optional) Google Cloud project with Drive API enabled, for video upload

### 1. Clone & Install

```bash
git clone https://github.com/YOUR_USERNAME/visocode.git
cd visocode

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt

# Pull the Manim Docker image (~2 GB, one-time)
docker pull manimcommunity/manim:latest
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env`:

```env
GEMINI_API_KEY=your_gemini_api_key_here
GOOGLE_DRIVE_FOLDER_ID=your_drive_folder_id_here   # optional
```

**Environment variables:**

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Yes | Google AI Studio API key |
| `GOOGLE_DRIVE_FOLDER_ID` | No | Target Drive folder for video uploads |

**Google Drive credentials (optional):**
- `token.json` — OAuth2 token for personal Gmail upload (generated on first authorization)
- `client_secrets.json` — Service account key for shared Drive upload

See [`docs/DRIVE_OAUTH_SETUP.md`](docs/DRIVE_OAUTH_SETUP.md) for the full Drive setup guide.

### 3. Run

```bash
streamlit run app.py
# → http://localhost:8501
```

---

## Usage

### Web UI

1. Open `http://localhost:8501`
2. Type an animation description in the left panel (or pick a template: Bubble Sort, Fourier Series, etc.)
3. Adjust model, temperature, and visual style in the sidebar
4. Click **Generate Video**
5. Watch live code and thought-process logs stream in the Director's Monitor
6. Download the `.mp4` or copy the Google Drive link

### CLI

```bash
export GEMINI_API_KEY=your_key

# Basic usage
python run.py "Visualize bubble sort step by step"

# With Drive upload and custom retry limit
python run.py "Show Fourier series approximation" \
  --folder-id YOUR_DRIVE_FOLDER_ID \
  --max-retries 3

# Use local Manim instead of Docker (requires: pip install manim)
python run.py "Pythagorean theorem" --local
```

---

## RAG System Design

### Tier 1 — Few-shot retrieval (generation time)

- Encodes the user's prompt and all past successful entries in `runs.json` using `sentence-transformers/all-MiniLM-L6-v2`
- Returns the Top-2 most similar successful Manim scenes
- These are injected as few-shot examples into the generation prompt
- Cold start: gracefully returns `[]` → zero-shot fallback, no crash

### Tier 2 — Error-driven API lookup (debug time)

- Triggered when `execute_node` fails with a `NameError`, `AttributeError`, or `ImportError`
- Extracts the offending symbol name from the compressed traceback via regex
- Looks up the exact entry in `manim_api_index.json` (57 hand-curated Manim APIs)
- Injects the matching signature + example code into `debugger_hint` for the next generation attempt

Together, these two strategies raise first-try success rate over multiple sessions while keeping fallback latency low (static JSON lookup, no network call).

---

## Agentic Pipeline Details

### GraphState (shared across all nodes)

```python
class GraphState(TypedDict):
    user_prompt: str
    current_code: str
    error_message: str
    retry_count: int           # execution failures
    audit_retry_count: int     # audit failures (separate cap)
    output_path: str
    drive_link: str
    debugger_hint: str
    is_fallback: bool
```

### Nodes

| Node | LLM Used | Purpose |
|------|----------|---------|
| `generate_node` | Gemini 2.5 Pro | Generate/refine Manim code with RAG context |
| `audit_node` | Gemini 2.5 Flash | Dual-layer safety + quality check |
| `execute_node` | — | Run code in Docker, collect `.mp4` output |
| `debugger_node` | Gemini 2.5 Flash | Compress traceback, get DIAGNOSIS + FIX |
| `fallback_node` | — | Render a safe minimal scene on max retries |
| `upload_node` | — | Upload `.mp4` to Google Drive |

### Routing logic

```
audit_node  → PASS              → execute_node
            → FAIL, retries < 3 → generate_node (with error feedback)
            → FAIL, retries ≥ 3 → fallback_node

execute_node → success          → upload_node
             → failure          → debugger_node → generate_node
```

---

## Deployment

### VPS (one command)

```bash
git clone https://github.com/YOUR_USERNAME/visocode.git
cd visocode
# Place .env, client_secrets.json, token.json
bash deploy.sh
# → http://<your-vps-ip>:8501
```

`deploy.sh` installs Docker, pulls the Manim image, builds the app container, and starts via `docker compose`.

### Docker Compose (manual)

```bash
docker compose build
docker compose up -d
docker compose logs -f
docker compose down
```

**Note:** The app container mounts `/var/run/docker.sock` to launch Manim sandbox containers at runtime (Docker-in-Docker pattern).

---

## License

MIT

---

## Acknowledgements

- [Manim Community](https://www.manim.community/) — animation engine
- [LangGraph](https://github.com/langchain-ai/langgraph) — agentic workflow orchestration
- [Google AI Studio](https://aistudio.google.com/) — Gemini 2.5 Pro/Flash API
- [Sentence Transformers](https://www.sbert.net/) — semantic embedding for RAG
