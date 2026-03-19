"""
app.py

Streamlit frontend for the AI-powered Manim video generator.
Styled as a "Knowledge Laboratory / Director's Studio."

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import traceback
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(_PROJECT_ROOT / ".env")

import streamlit as st

from auditor import LLMJudgeAuditor, SecurityAuditor
from executor import LocalExecutor, SandboxExecutor
from generator import SceneDescription, SceneComplexity
from orchestrator import PipelineStatus, WorkflowOrchestrator

# ── Early API key check (prevents DefaultCredentialsError on first load) ──────
if not os.environ.get("GOOGLE_API_KEY"):
    st.warning(
        "⚠️  **GOOGLE_API_KEY not set.** "
        "Copy `.env.example` → `.env` and fill in your key to enable video generation. "
        "Demo videos still work without a key.",
        icon="🔑",
    )

# ── Page configuration ───────────────────────────────────────────────────────
st.set_page_config(
    page_title="Visocode | Knowledge Laboratory",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* ── Gradient header ─────────────────────────────────────────────────── */
    .lab-header {
        background: linear-gradient(135deg, #0d1117 0%, #161b27 40%, #0f3460 100%);
        padding: 2.2rem 2rem 1.8rem;
        border-radius: 14px;
        margin-bottom: 1.6rem;
        text-align: center;
        border: 1px solid rgba(100, 140, 220, 0.25);
        box-shadow: 0 4px 24px rgba(0, 0, 0, 0.4);
    }
    .lab-header h1 {
        font-size: 2.6rem;
        font-weight: 800;
        margin: 0 0 0.4rem;
        background: linear-gradient(90deg, #a8edea 0%, #fed6e3 60%, #a8edea 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    .lab-header p {
        color: #8892b0;
        font-size: 1rem;
        margin: 0;
        letter-spacing: 0.04em;
    }

    /* ── Rounded video container ─────────────────────────────────────────── */
    .video-wrap {
        border-radius: 16px;
        overflow: hidden;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
        border: 1px solid rgba(100, 140, 220, 0.2);
        margin-top: 0.5rem;
    }
    .video-wrap video {
        width: 100%;
        display: block;
    }

    /* ── History gallery card ────────────────────────────────────────────── */
    .history-card {
        background: linear-gradient(135deg, #1c2340 0%, #252d50 100%);
        border-radius: 12px;
        padding: 1rem 1rem 0.8rem;
        border: 1px solid rgba(100, 120, 220, 0.25);
        margin-bottom: 0.6rem;
        font-size: 0.85rem;
    }
    .history-card .card-title {
        color: #a8b4e0;
        font-weight: 700;
        margin-bottom: 0.3rem;
    }
    .history-card .card-prompt {
        color: #7a87b0;
        font-size: 0.78rem;
        line-height: 1.4;
    }
    .history-card .card-time {
        color: #50597a;
        font-size: 0.72rem;
        margin-top: 0.4rem;
    }

    /* ── Template / action buttons ───────────────────────────────────────── */
    div[data-testid="stButton"] button {
        border-radius: 8px;
        font-size: 0.83rem;
        transition: box-shadow 0.2s, transform 0.15s;
    }
    div[data-testid="stButton"] button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(100, 140, 220, 0.3);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Constants ─────────────────────────────────────────────────────────────────
_WORKING_DIR = _PROJECT_ROOT / "manim_output"
_RUNS_FILE = _WORKING_DIR / "runs.json"
_DEMOS_JSON = _PROJECT_ROOT / "manim_output" / "demos" / "demos.json"


def _load_demos() -> dict:
    """Load pre-generated demo video index."""
    if not _DEMOS_JSON.exists():
        return {}
    try:
        with open(_DEMOS_JSON, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _load_runs() -> list[dict]:
    if not _RUNS_FILE.exists():
        return []
    try:
        with open(_RUNS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _append_run(
    prompt: str,
    status: str,
    video_path: str | None = None,
    drive_link: str = "",
    attempts: int = 0,
    code: str = "",
) -> None:
    _WORKING_DIR.mkdir(parents=True, exist_ok=True)
    runs = _load_runs()
    first_try = status == "success" and attempts == 1
    runs.insert(
        0,
        {
            "ts": datetime.now().isoformat(),
            "prompt": (prompt[:200] + "…") if len(prompt) > 200 else prompt,
            "status": status,
            "video_path": video_path or "",
            "drive_link": drive_link,
            "attempts": attempts,
            "first_try": first_try,
            "code": code,  # stored for RAG retrieval by RunsRetriever
        },
    )
    runs = runs[:100]
    with open(_RUNS_FILE, "w", encoding="utf-8") as f:
        json.dump(runs, f, ensure_ascii=False, indent=2)


def _through_rate_stats(runs: list[dict]) -> dict:
    """From runs list compute: total, first_try_success count, rate (0–1)."""
    total = len(runs)
    first_try = sum(
        1 for r in runs
        if r.get("first_try", r.get("status") == "success" and r.get("attempts") == 1)
    )
    return {
        "total": total,
        "first_try_success": first_try,
        "rate": (first_try / total) if total else 0.0,
    }

_STYLE_PRESETS: dict[str, str] = {
    "Minimalist Dark": (
        "\n\nVISUAL STYLE DIRECTIVE — Minimalist Dark:\n"
        "- Background: pure black (#000000).\n"
        "- Text / main elements: white (#FFFFFF).\n"
        "- Accent: muted gray (#888888) for secondary elements.\n"
        "- Animations: FadeIn / FadeOut, slow and deliberate (wait >= 1 s).\n"
        "- Absolutely no decorative geometry — let the content speak.\n"
        "- Prefer Write() for text and Create() for shapes.\n"
    ),
    "Classic Blackboard": (
        "\n\nVISUAL STYLE DIRECTIVE — Classic Blackboard:\n"
        "- Background: dark green (#1a4a2e) to evoke a chalkboard.\n"
        "- Text: cream-white (#F5F5DC) as chalk strokes.\n"
        "- Use Write() for all text, DrawBorderThenFill() for shapes.\n"
        "- Colours: soft yellow, chalk pink, and light blue — like colored chalk.\n"
        "- Use Text() for equations (no LaTeX/MathTex); animate them as if handwritten.\n"
        "- Pacing: moderate (wait ~0.8 s between steps).\n"
    ),
    "Futuristic Tech": (
        "\n\nVISUAL STYLE DIRECTIVE — Futuristic Tech:\n"
        "- Background: very dark navy (#050A1A).\n"
        "- Primary accent: electric cyan (#00FFFF).\n"
        "- Secondary accents: purple (#7B2FBE) and hot pink (#FF006E).\n"
        "- Animations: GrowFromCenter(), Create() — fast and energetic.\n"
        "- Shorten wait() calls (0.3 – 0.5 s) for a rapid, dynamic feel.\n"
        "- Math elements should look like holographic read-outs.\n"
    ),
}

_QUICK_TEMPLATES: dict[str, str] = {
    "Pythagorean Theorem": (
        "Explain and visualize the Pythagorean theorem (a^2 + b^2 = c^2). "
        "Show a right triangle with labeled sides a, b, c, then animate squares "
        "growing on each side to prove why a^2 + b^2 = c^2. End with the formula."
    ),
    "Bubble Sort": (
        "Visualize Bubble Sort on an array of 6 numbers. "
        "Represent elements as vertical bars of different heights. "
        "Highlight the pair being compared, animate swaps with smooth movement, "
        "and show the fully sorted array with a success animation at the end."
    ),
    "Fourier Series": (
        "Demonstrate how a Fourier series approximates a square wave. "
        "Start with the fundamental frequency and add harmonics one by one, "
        "showing how the superposition converges. Label each harmonic n=1,3,5..."
    ),
    "Gradient Descent": (
        "Visualize gradient descent on a 2D parabolic loss curve. "
        "Show a dot rolling down the curve, arrows indicating gradient direction, "
        "and annotate each step with the learning-rate update rule."
    ),
}


# ── Logging capture helper ────────────────────────────────────────────────────

class _ListHandler(logging.Handler):
    """Append formatted log records to an external list."""

    def __init__(self, store: list[tuple[str, str]]) -> None:
        super().__init__()
        self.store = store

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.store.append((record.levelname, self.format(record)))
        except Exception:
            self.handleError(record)


# ── Session-state initialisation ──────────────────────────────────────────────

def _init_state() -> None:
    defaults: dict = {
        "history": [],
        "current_code": "",
        "thought_process": [],
        "last_video_path": None,
        "last_drive_link": "",
        "script_input": "",
        "last_run_status": "",
        "last_run_error": "",
        "last_run_is_fallback": False,
        "demo_video_path": None,   # pre-generated demo selected by template button
        "demo_title": "",
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


_init_state()


# ── Orchestrator factory ──────────────────────────────────────────────────────

def _build_orchestrator(
    model_name: str,
    temperature: float,
    top_p: float,
    use_local_manim: bool = False,
) -> WorkflowOrchestrator:
    """Construct a WorkflowOrchestrator with UI settings passed through constructor."""
    _WORKING_DIR.mkdir(parents=True, exist_ok=True)
    executor = LocalExecutor() if use_local_manim else SandboxExecutor()
    return WorkflowOrchestrator(
        auditors=[SecurityAuditor(), LLMJudgeAuditor()],
        executor=executor,
        working_dir=_WORKING_DIR,
        max_retries=3,
        model_name=model_name,
        temperature=temperature,
        top_p=top_p,
    )


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="lab-header">
        <h1>Visocode &mdash; Knowledge Laboratory</h1>
        <p>Transform plain explanations into professional Manim animations with AI</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ── Sidebar — Control Tower ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## Control Tower")

    # Model settings
    st.markdown("### Model Settings")
    model_name = st.selectbox(
        "LLM Model",
        ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
        index=0,
    )
    temperature = st.slider(
        "Temperature",
        min_value=0.0,
        max_value=1.0,
        value=0.2,
        step=0.05,
        help="Higher = more creative / experimental output.",
    )
    top_p = st.slider(
        "Top-p",
        min_value=0.1,
        max_value=1.0,
        value=0.95,
        step=0.05,
        help="Nucleus sampling — controls diversity of tokens considered.",
    )

    st.divider()

    # Visual style preset
    st.markdown("### Visual Style")
    style_preset = st.selectbox("Preset", list(_STYLE_PRESETS.keys()), index=0)
    st.caption(
        {
            "Minimalist Dark": "Clean black-and-white. No distractions.",
            "Classic Blackboard": "Hand-drawn chalk aesthetic on dark green.",
            "Futuristic Tech": "Neon glows, fast cuts, holographic feel.",
        }[style_preset]
    )

    st.divider()

    # Output / upload settings
    st.markdown("### Output Settings")
    use_local_manim = st.checkbox(
        "Use local Manim (no Docker)",
        value=False,
        help="Run manim on this machine. Requires: pip install manim.",
    )
    st.caption("Videos saved locally to the working directory.")

    st.divider()

    # Pipeline info (single-process: pipeline runs inside this Streamlit app)
    st.markdown("### Pipeline")
    exec_label = "Local Manim" if use_local_manim else "Docker (Manim)"
    st.caption(f"Executor: **{exec_label}**")
    st.caption(f"Working dir: `{_WORKING_DIR}`")
    has_key = bool(os.environ.get("GOOGLE_API_KEY"))
    st.caption(f"API key: **{'loaded' if has_key else 'not set'}**" + (" ⚠️" if not has_key else ""))
    # When local Manim is selected, check if manim/ffmpeg are in PATH (same terminal as Streamlit)
    if use_local_manim:
        manim_path = shutil.which("manim")
        ffmpeg_path = shutil.which("ffmpeg")
        st.caption(f"manim: **{'✓ ' + manim_path if manim_path else '✗ not in PATH'}**")
        st.caption(f"ffmpeg: **{'✓ ' + ffmpeg_path if ffmpeg_path else '✗ not in PATH'}**")
        if not manim_path or not ffmpeg_path:
            st.caption("💡 Launch from the same terminal where `manim` works: `streamlit run app.py`")
    st.markdown("### About")
    st.info(
        f"Gemini → LangGraph → Audit → {exec_label}",
        icon="⚙️",
    )


# ── Main Split View ───────────────────────────────────────────────────────────
left_col, right_col = st.columns([1, 1], gap="large")

# ── Left Column: Input ────────────────────────────────────────────────────────
with left_col:
    st.markdown("### Script Input")

    # Quick template buttons — 2-column grid
    st.caption("Quick Templates  ·  click to preview pre-generated demo")
    _demos = _load_demos()
    btn_cols = st.columns(2)
    for idx, (label, prompt) in enumerate(_QUICK_TEMPLATES.items()):
        with btn_cols[idx % 2]:
            if st.button(label, use_container_width=True, key=f"tpl_{idx}"):
                st.session_state.script_input = prompt
                # Load pre-generated demo video if available
                demo = _demos.get(label)
                if demo:
                    demo_path = _PROJECT_ROOT / demo["video"]
                    if demo_path.exists():
                        st.session_state.demo_video_path = str(demo_path)
                        st.session_state.demo_title = label
                    else:
                        st.session_state.demo_video_path = None
                        st.session_state.demo_title = ""
                st.rerun()

    # Main textarea — key binds it to session_state.script_input
    st.text_area(
        "Explanation Script",
        key="script_input",
        height=280,
        placeholder=(
            "Describe what you want to visualize...\n\n"
            "Example: Show how the Fibonacci sequence grows and\n"
            "animate the first 10 terms as a growing bar chart."
        ),
        label_visibility="collapsed",
    )

    generate_btn = st.button(
        "Generate Video",
        type="primary",
        use_container_width=True,
    )

# ── Right Column: Director's Monitor ─────────────────────────────────────────
with right_col:
    st.markdown("### Director's Monitor")
    demo_tab, scripting_tab, thought_tab = st.tabs(["Demo Preview", "Live Scripting", "Thought Process"])

    with demo_tab:
        demo_path = st.session_state.get("demo_video_path")
        demo_title = st.session_state.get("demo_title", "")
        if demo_path and Path(demo_path).exists():
            st.caption(f"Pre-generated demo: **{demo_title}**")
            st.video(demo_path)
        else:
            st.info("Click a Quick Template to preview its pre-generated demo video.")

    with scripting_tab:
        if st.session_state.current_code:
            st.code(st.session_state.current_code, language="python")
        else:
            st.info("Generated Manim source code will appear here after a run.")

    with thought_tab:
        if st.session_state.thought_process:
            log_text = "\n".join(
                f"[{lvl}]  {msg}"
                for lvl, msg in st.session_state.thought_process
            )
            st.code(log_text, language="text")
        else:
            st.info(
                "Pipeline log messages and reasoning steps will appear here "
                "after a run."
            )


# ── Pipeline Execution ────────────────────────────────────────────────────────
if generate_btn:
    user_script: str = st.session_state.script_input.strip()

    if not user_script:
        st.warning("Please enter an explanation script or pick a Quick Template.")
    else:
        # Build style-injected narrative
        narrative = user_script + _STYLE_PRESETS[style_preset]
        description = SceneDescription(
            title="GeneratedScene",
            narrative=narrative,
            complexity=SceneComplexity.MODERATE,
        )

        # Set up log capture
        captured_logs: list[tuple[str, str]] = []
        log_handler = _ListHandler(captured_logs)
        log_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s  %(name)s — %(message)s", datefmt="%H:%M:%S"
            )
        )
        root_logger = logging.getLogger()
        prev_level = root_logger.level
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(log_handler)

        pipeline_result = None
        pipeline_error: str | None = None

        try:
            orchestrator = _build_orchestrator(
                model_name=model_name,
                temperature=temperature,
                top_p=top_p,
                use_local_manim=use_local_manim,
            )

            with st.status("Generating Manim Video...", expanded=True) as status:
                st.write("Pipeline running in this app (no separate backend).")
                st.write("Synthesizing Script — calling Gemini LLM...")

                try:
                    pipeline_result = orchestrator.run(description)
                except Exception as exc:
                    pipeline_error = traceback.format_exc()
                    status.update(
                        label="Pipeline Error", state="error", expanded=True
                    )

                if pipeline_result is not None:
                    if pipeline_result.status == PipelineStatus.SUCCESS:
                        st.write("Compiling Manim Code — audit passed, code is safe.")
                        st.write("Rendering Frames — Docker sandbox complete.")
                        status.update(
                            label="Video Ready!", state="complete", expanded=False
                        )
                    else:
                        st.write(
                            f"Pipeline finished with status: "
                            f"{pipeline_result.status.value}"
                        )
                        status.update(
                            label="Generation Failed", state="error", expanded=True
                        )

        finally:
            root_logger.removeHandler(log_handler)
            root_logger.setLevel(prev_level)

        # ── Update session state ──────────────────────────────────────────────
        st.session_state.thought_process = captured_logs

        if pipeline_error:
            st.session_state.last_run_status = "exception"
            st.session_state.last_run_error = pipeline_error
            _append_run(user_script, "exception")
            with st.expander("Debug Info", expanded=True):
                st.error("An unexpected exception was raised during the pipeline run.")
                st.code(pipeline_error, language="text")

        elif pipeline_result is not None:
            final_state = pipeline_result.final_state or {}
            st.session_state.current_code = final_state.get("current_code", "")

            st.session_state.last_run_status = pipeline_result.status.value
            if pipeline_result.status == PipelineStatus.SUCCESS:
                video_path = (
                    str(pipeline_result.output_files[0])
                    if pipeline_result.output_files
                    else None
                )
                st.session_state.last_video_path = video_path
                st.session_state.last_drive_link = ""
                st.session_state.last_run_error = ""
                st.session_state.last_run_is_fallback = getattr(
                    pipeline_result, "is_fallback", False
                )

                _append_run(
                    user_script,
                    pipeline_result.status.value,
                    video_path=video_path,
                    drive_link="",
                    attempts=pipeline_result.total_attempts,
                    code=st.session_state.current_code,  # persisted for RAG
                )

                # Prepend to history (keep last 3)
                history_entry: dict = {
                    "prompt": (
                        user_script[:90] + "..."
                        if len(user_script) > 90
                        else user_script
                    ),
                    "video_path": video_path,
                    "drive_link": "",
                    "code": st.session_state.current_code,
                    "timestamp": datetime.now().strftime("%H:%M  %d %b"),
                    "attempts": pipeline_result.total_attempts,
                }
                st.session_state.history.insert(0, history_entry)
                st.session_state.history = st.session_state.history[:3]

            else:
                st.session_state.last_run_is_fallback = False
                error_msg = final_state.get(
                    "error_message", "No error detail available."
                )
                st.session_state.last_run_error = error_msg
                _append_run(
                    user_script,
                    pipeline_result.status.value,
                    attempts=pipeline_result.total_attempts,
                )
                with st.expander("Debug Info", expanded=True):
                    st.warning(
                        f"Pipeline status: `{pipeline_result.status.value}`  |  "
                        f"Total attempts: {pipeline_result.total_attempts}"
                    )
                    st.code(error_msg, language="text")

        # Rerun to refresh the Director's Monitor tabs with updated state
        st.rerun()


# ── Output — Video Player ─────────────────────────────────────────────────────
st.markdown("---")
st.markdown("### Output")

last_status = st.session_state.get("last_run_status", "")
last_error = st.session_state.get("last_run_error", "")

# Last run failed: show reason persistently in Output section (survives rerun)
if last_status and last_status != "success":
    if st.session_state.current_code:
        st.warning(
            "**Last run produced code but no video** — rendering failed. "
            "Check: «Use local Manim» + manim/ffmpeg in PATH, or Docker running."
        )
    else:
        st.warning("**Last run failed** (no code or exception).")
    if last_error:
        with st.expander("Last run error (copy to fix)", expanded=True):
            st.code(last_error, language="text")

if st.session_state.last_video_path:
    video_path_obj = Path(st.session_state.last_video_path)
    if video_path_obj.exists():
        st.markdown('<div class="video-wrap">', unsafe_allow_html=True)
        st.video(str(video_path_obj))
        if st.session_state.get("last_run_is_fallback"):
            st.caption("Fallback video (max retries reached — generation failed)")
        st.markdown("</div>", unsafe_allow_html=True)

        link_col, dl_col = st.columns([3, 1])
        with link_col:
            if st.session_state.last_drive_link:
                st.markdown(
                    f"[Open on Google Drive]({st.session_state.last_drive_link})"
                )
        with dl_col:
            with open(str(video_path_obj), "rb") as fh:
                st.download_button(
                    "Download MP4",
                    data=fh,
                    file_name=video_path_obj.name,
                    mime="video/mp4",
                    use_container_width=True,
                )
    else:
        st.warning(
            f"Video file not found at `{video_path_obj}`. "
            "It may have been removed from the working directory."
        )
elif not (last_status and last_status != "success"):
    st.info("Your generated video will appear here after a successful run.")


# ── History Gallery ───────────────────────────────────────────────────────────
if st.session_state.history:
    st.markdown("---")
    st.markdown("### History Gallery")

    n = min(len(st.session_state.history), 3)
    gallery_cols = st.columns(n, gap="medium")

    for i, entry in enumerate(st.session_state.history[:n]):
        with gallery_cols[i]:
            st.markdown(
                f"""
                <div class="history-card">
                    <div class="card-title">Video {i + 1}</div>
                    <div class="card-prompt">{entry['prompt']}</div>
                    <div class="card-time">
                        {entry['timestamp']} &nbsp;&middot;&nbsp;
                        {entry['attempts']} attempt(s)
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            vp = entry.get("video_path")
            if vp and Path(str(vp)).exists():
                st.video(str(vp))

            dl = entry.get("drive_link")
            if dl:
                st.markdown(f"[View on Drive]({dl})")
            else:
                st.caption("No Drive link")


# ── Run History (persisted to runs.json, visible after browser refresh) ──────
st.markdown("---")
st.markdown("### Run History")
runs = _load_runs()
if runs:
    stats = _through_rate_stats(runs)
    st.caption(
        f"First-try success rate: **{stats['first_try_success']}/{stats['total']}** "
        f"({100 * stats['rate']:.0f}%)  |  Log file: `{_RUNS_FILE}`"
    )
else:
    st.caption(f"Log file: **`{_RUNS_FILE}`**")
st.caption("Every run is saved locally — results persist after closing the browser.")
if not runs:
    st.info("No runs yet. Generate a video (success or failure) and it will appear here.")
else:
    for r in runs[:30]:
        ts = r.get("ts", "")[:19].replace("T", " ")
        st.markdown(f"**{ts}** — {r.get('status', '')} ({r.get('attempts', 0)} attempt(s))")
        st.caption(r.get("prompt", "")[:120])
        if r.get("drive_link"):
            st.markdown(f"[📁 Open on Drive]({r['drive_link']})")
        if r.get("video_path") and Path(r["video_path"]).exists():
            st.caption(f"Local: `{r['video_path']}`")
        st.divider()
