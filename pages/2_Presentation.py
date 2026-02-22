"""
pages/2_Presentation.py

Visocode — Technical Interview Presentation
White & blue theme, Streamlit-native, slide-by-slide navigation.
"""

from __future__ import annotations

import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Visocode | Presentation",
    page_icon="🎞️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS: white & blue theme ───────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* Global white background */
    .stApp { background-color: #ffffff; }
    section[data-testid="stSidebar"] { background-color: #f0f6ff; border-right: 1px solid #bfdbfe; }

    /* Typography */
    .slide-label {
        font-size: 0.65rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 2px; color: #60a5fa; margin-bottom: 4px;
    }
    .slide-title {
        font-size: 1.9rem; font-weight: 800; color: #1e3a5f;
        line-height: 1.25; margin: 0 0 1.2rem;
    }
    .slide-subtitle {
        font-size: 1rem; color: #475569; margin: 0 0 1.4rem; font-style: italic;
    }

    /* Cards */
    .card {
        background: #f0f7ff;
        border: 1px solid #bfdbfe;
        border-radius: 12px;
        padding: 18px 20px;
        height: 100%;
    }
    .card-title {
        font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 1px; margin-bottom: 8px;
    }
    .card-blue   { border-left: 4px solid #3b82f6; }
    .card-green  { border-left: 4px solid #22c55e; }
    .card-orange { border-left: 4px solid #f59e0b; }
    .card-purple { border-left: 4px solid #a855f7; }
    .card-red    { border-left: 4px solid #ef4444; }

    /* Metric */
    .metric-box {
        text-align: center;
        background: #eff6ff;
        border: 1px solid #bfdbfe;
        border-radius: 12px;
        padding: 18px 10px;
    }
    .metric-val { font-size: 2rem; font-weight: 800; display: block; color: #1d4ed8; }
    .metric-lbl { font-size: 0.72rem; color: #64748b; display: block; margin-top: 4px; }

    /* Flow node */
    .flow-wrap {
        display: flex; align-items: center; justify-content: center;
        gap: 0; flex-wrap: wrap; margin: 10px 0;
    }
    .flow-node {
        background: #eff6ff; border: 2px solid #3b82f6;
        border-radius: 8px; padding: 10px 18px;
        font-size: 0.82rem; font-weight: 700; color: #1d4ed8;
        text-align: center; min-width: 95px;
    }
    .flow-node.ok     { border-color: #22c55e; color: #15803d; background: #f0fdf4; }
    .flow-node.warn   { border-color: #f59e0b; color: #b45309; background: #fffbeb; }
    .flow-node.danger { border-color: #ef4444; color: #b91c1c; background: #fef2f2; }
    .flow-node.muted  { border-color: #94a3b8; color: #64748b; background: #f8fafc; }
    .flow-arrow       { color: #94a3b8; font-size: 1.1rem; padding: 0 4px; }

    /* Q&A row */
    .qa-row {
        background: #f8fafc; border: 1px solid #e2e8f0;
        border-radius: 10px; padding: 12px 16px;
        display: flex; gap: 20px; align-items: flex-start;
        margin-bottom: 8px;
    }
    .qa-q { color: #2563eb; font-weight: 600; font-size: 0.82rem; min-width: 200px; }
    .qa-a { color: #334155; font-size: 0.82rem; line-height: 1.5; }

    /* Quote */
    .quote-box {
        border-left: 4px solid #3b82f6;
        padding: 14px 20px;
        background: #eff6ff;
        border-radius: 0 10px 10px 0;
        font-size: 1rem;
        color: #1e3a5f;
        margin: 16px 0;
    }

    /* Progress pill */
    .slide-pill {
        display: inline-block; padding: 4px 14px;
        border-radius: 20px; font-size: 0.72rem; font-weight: 700;
        cursor: pointer; margin: 2px 3px;
    }
    .pill-active { background: #2563eb; color: white; }
    .pill-idle   { background: #e0ecff; color: #2563eb; }

    /* Hide default Streamlit header branding */
    header[data-testid="stHeader"] { background: transparent; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Slide definitions ─────────────────────────────────────────────────────────

SLIDES = [
    "Title",
    "01 · Hook & Problem",
    "02 · Architecture",
    "02b · Tech Stack",
    "03 · Engineering Challenges",
    "03b · ApiLookup Deep Dive",
    "04 · RAG System Design",
    "05 · Results & Next Steps",
    "06 · Q&A Prep",
]


# ── Sidebar navigation ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🎞️ Visocode Slides")
    st.markdown("---")
    if "slide_index" not in st.session_state:
        st.session_state.slide_index = 0

    for i, name in enumerate(SLIDES):
        label = f"{'▶ ' if i == st.session_state.slide_index else ''}{name}"
        if st.button(label, key=f"nav_{i}", use_container_width=True):
            st.session_state.slide_index = i

    st.markdown("---")
    st.caption("← Back to Generator: use the sidebar Pages")

# ── Prev / Next buttons ───────────────────────────────────────────────────────
idx = st.session_state.slide_index
total = len(SLIDES)

col_prev, col_counter, col_next = st.columns([1, 4, 1])
with col_prev:
    if st.button("← Prev", disabled=(idx == 0), use_container_width=True):
        st.session_state.slide_index -= 1
        st.rerun()
with col_counter:
    st.markdown(
        f"<div style='text-align:center; color:#64748b; font-size:0.85rem; padding-top:6px;'>"
        f"Slide {idx + 1} / {total} — <strong>{SLIDES[idx]}</strong></div>",
        unsafe_allow_html=True,
    )
with col_next:
    if st.button("Next →", disabled=(idx == total - 1), use_container_width=True):
        st.session_state.slide_index += 1
        st.rerun()

st.markdown("<hr style='margin: 8px 0 24px; border-color: #e2e8f0;'>", unsafe_allow_html=True)

idx = st.session_state.slide_index  # re-read after potential rerun


# ═══════════════════════════════════════════════════════════════════════════════
# SLIDE 0 — Title
# ═══════════════════════════════════════════════════════════════════════════════
if idx == 0:
    st.markdown(
        """
        <div style="text-align:center; padding: 40px 0 20px;">
          <div style="font-size:0.7rem; font-weight:700; text-transform:uppercase;
                      letter-spacing:3px; color:#60a5fa; margin-bottom:12px;">
            Portfolio Project
          </div>
          <h1 style="font-size:3.4rem; font-weight:900; color:#1e3a5f;
                     letter-spacing:-1px; margin:0 0 12px;">
            Visocode
          </h1>
          <p style="font-size:1.15rem; color:#475569; margin-bottom:32px;">
            From Natural Language to Manim Animation —<br>
            <strong style="color:#1d4ed8;">with a Reliability-First AI Pipeline</strong>
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    for col, label, color in [
        (c1, "LangGraph", "#3b82f6"),
        (c2, "Gemini 2.5", "#22c55e"),
        (c3, "Docker Sandbox", "#f59e0b"),
        (c4, "RAG", "#a855f7"),
        (c5, "Streamlit", "#ef4444"),
        (c6, "Google Drive", "#3b82f6"),
    ]:
        col.markdown(
            f"<div style='text-align:center; background:{color}18; border:1px solid {color}44; "
            f"border-radius:20px; padding:6px 4px; font-size:0.75rem; font-weight:700; "
            f"color:{color};'>{label}</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        "<div style='text-align:center; color:#94a3b8; font-size:0.8rem;'>"
        "Use ← → buttons or the sidebar to navigate</div>",
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SLIDE 1 — Hook & Problem
# ═══════════════════════════════════════════════════════════════════════════════
elif idx == 1:
    st.markdown('<div class="slide-label">01 / Hook &amp; Problem</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="slide-title">"From Text to Animation in 30 Seconds —<br>'
        '<span style="color:#2563eb;">with a Reliability-First AI Pipeline</span>"</div>',
        unsafe_allow_html=True,
    )

    col_l, col_r = st.columns(2, gap="large")

    with col_l:
        st.markdown(
            """
            <div class="card card-red">
              <div class="card-title" style="color:#ef4444;">The Problem</div>
              <ul style="padding-left:18px; margin:0;">
                <li style="padding:4px 0; font-size:0.88rem; color:#334155;">
                  Manim has a steep learning curve</li>
                <li style="padding:4px 0; font-size:0.88rem; color:#334155;">
                  LLM code has hallucinated APIs</li>
                <li style="padding:4px 0; font-size:0.88rem; color:#334155;">
                  Passes static checks, crashes at runtime</li>
                <li style="padding:4px 0; font-size:0.88rem; color:#334155;">
                  "Correct" code generates a blank video</li>
              </ul>
              <hr style="margin:12px 0; border-color:#fecaca;"/>
              <p style="font-size:0.82rem; color:#64748b; margin:0;">
                The hard part isn't generating code.<br>
                <strong style="color:#1e293b;">The hard part is making it reliably work.</strong>
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_r:
        st.markdown(
            """
            <div class="card card-blue" style="margin-bottom:14px;">
              <div class="card-title" style="color:#3b82f6;">The Solution</div>
              <p style="font-size:0.88rem; color:#334155; margin:0;">
                User types: <em style="color:#2563eb;">"Visualize bubble sort step by step"</em><br>
                30 seconds later → an <code>.mp4</code>, uploaded to Google Drive.
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        m1, m2, m3 = st.columns(3)
        for col, val, lbl in [
            (m1, "2", "Safety layers\nAST + LLM Judge"),
            (m2, "~30s", "Avg generation\ntime"),
            (m3, "5", "Node types\nin LangGraph DAG"),
        ]:
            col.markdown(
                f"<div class='metric-box'>"
                f"<span class='metric-val'>{val}</span>"
                f"<span class='metric-lbl'>{lbl}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )


# ═══════════════════════════════════════════════════════════════════════════════
# SLIDE 2 — Architecture
# ═══════════════════════════════════════════════════════════════════════════════
elif idx == 2:
    st.markdown('<div class="slide-label">02 / Architecture</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="slide-title">"A LangGraph Pipeline with<br>'
        '<span style="color:#2563eb;">Deterministic Safety Layers</span>"</div>',
        unsafe_allow_html=True,
    )

    # Flow diagram
    st.markdown(
        """
        <div class="flow-wrap">
          <div class="flow-node">GENERATE<br><span style="font-size:0.6rem;font-weight:400;color:#64748b;">Gemini 2.5 Pro</span></div>
          <div class="flow-arrow">→</div>
          <div class="flow-node warn">AUDIT<br><span style="font-size:0.6rem;font-weight:400;color:#64748b;">AST + LLM Judge</span></div>
          <div class="flow-arrow">→</div>
          <div class="flow-node ok">EXECUTE<br><span style="font-size:0.6rem;font-weight:400;color:#64748b;">Docker sandbox</span></div>
          <div class="flow-arrow">→</div>
          <div class="flow-node ok">UPLOAD<br><span style="font-size:0.6rem;font-weight:400;color:#64748b;">Google Drive</span></div>
        </div>
        <div style="text-align:center; font-size:0.72rem; color:#94a3b8; margin-bottom:16px;">
          audit fail → retry generate &nbsp;|&nbsp;
          exec fail → DEBUGGER → generate &nbsp;|&nbsp;
          max retries → FALLBACK
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3, gap="medium")

    with c1:
        st.markdown(
            """
            <div class="card card-blue">
              <div class="card-title" style="color:#3b82f6;">Why LangGraph?</div>
              <p style="font-size:0.82rem; color:#334155; margin:0;">
                Control flow isn't linear — audit fail and exec fail route differently.
                LangGraph separates <strong>topology</strong> from <strong>business logic</strong>.
                Adding a node doesn't touch others.
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c2:
        st.markdown(
            """
            <div class="card card-orange">
              <div class="card-title" style="color:#f59e0b;">Two-Layer Audit</div>
              <p style="font-size:0.82rem; color:#334155; margin:0;">
                <strong>Layer 1:</strong> AST static scan — deterministic, blocks dangerous imports.<br><br>
                <strong>Layer 2:</strong> LLM Judge (Flash) — semantic check, 3–5× cheaper than Pro.
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c3:
        st.markdown(
            """
            <div class="card card-purple">
              <div class="card-title" style="color:#a855f7;">Debugger Node</div>
              <p style="font-size:0.82rem; color:#334155; margin:0;">
                Compresses 2000-char traceback → 2 lines:<br><br>
                <code style="color:#f59e0b;">DIAGNOSIS:</code> root cause<br>
                <code style="color:#22c55e;">FIX:</code> concrete action<br><br>
                SNR ↑ &nbsp;·&nbsp; token cost ↓ &nbsp;·&nbsp; fix rate ↑
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SLIDE 2b — Tech Stack
# ═══════════════════════════════════════════════════════════════════════════════
elif idx == 3:
    st.markdown('<div class="slide-label">02b / Tech Stack</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="slide-title">Technology Choices &amp; <span style="color:#2563eb;">Trade-offs</span></div>',
        unsafe_allow_html=True,
    )

    col_l, col_r = st.columns(2, gap="large")

    with col_l:
        for card_data in [
            ("3b82f6", "LangGraph StateGraph", "Orchestration",
             "TypedDict state shared across all nodes. Conditional edges at runtime. "
             "<code>recursion_limit=50</code> as hard safety cap."),
            ("f59e0b", "Docker Sandbox", "Execution",
             "<code>manimcommunity/manim</code> · network_disabled · mem 1 GB · "
             "cpu_quota · timeout 120s. Container removed after every run."),
            ("22c55e", "Gemini 2.5 Pro / Flash", "LLM",
             "Pro for generation (quality), Flash for Judge (cost). "
             "Architecture is model-agnostic — swap to GPT-4 in one line."),
        ]:
            color, title, badge, body = card_data
            st.markdown(
                f"""
                <div class="card" style="border-left:4px solid #{color}; margin-bottom:12px;">
                  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <span style="font-size:0.82rem; font-weight:700; color:#1e293b;">{title}</span>
                    <span style="background:#{color}18; color:#{color}; border:1px solid #{color}44;
                                 border-radius:20px; font-size:0.65rem; font-weight:700;
                                 padding:2px 10px;">{badge}</span>
                  </div>
                  <p style="font-size:0.78rem; color:#475569; margin:0;">{body}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with col_r:
        st.markdown(
            """
            <div class="card card-purple" style="margin-bottom:12px;">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <span style="font-size:0.82rem; font-weight:700; color:#1e293b;">RAG — Two Tiers</span>
                <span style="background:#a855f718; color:#a855f7; border:1px solid #a855f744;
                             border-radius:20px; font-size:0.65rem; font-weight:700;
                             padding:2px 10px;">Retrieval</span>
              </div>
              <p style="font-size:0.78rem; color:#475569; margin:0;">
                <strong>Tier 1:</strong> <code>sentence-transformers</code> over <code>runs.json</code>
                — few-shot examples at generation time.<br><br>
                <strong>Tier 2:</strong> <code>manim_api_index.json</code> (57 entries)
                — error-driven doc injection at debug time.
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            "<div style='font-size:0.78rem; font-weight:700; color:#64748b; "
            "margin-bottom:6px;'>GraphState — shared data contract</div>",
            unsafe_allow_html=True,
        )
        st.code(
            """\
class GraphState(TypedDict):
    user_prompt:       str
    generated_code:    str
    audit_result:      str   # PASS | FAIL
    audit_retry_count: int   # circuit breaker
    execution_result:  dict
    debugger_hint:     str
    output_path:       str
    is_fallback:       bool""",
            language="python",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SLIDE 3 — 3 Engineering Challenges
# ═══════════════════════════════════════════════════════════════════════════════
elif idx == 4:
    st.markdown('<div class="slide-label">03 / Engineering Challenges</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="slide-title">"Three Problems I Didn\'t Expect —<br>'
        '<span style="color:#f59e0b;">and How I Solved Them</span>"</div>',
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3, gap="medium")

    with c1:
        st.markdown(
            """
            <div class="card card-red" style="height:100%;">
              <div class="card-title" style="color:#ef4444;">Problem 1 · Infinite Loop</div>
              <p style="font-size:0.8rem; color:#334155; margin:0 0 10px;">
                LLM Judge kept returning FAIL.<br>
                No audit retry cap →<br>
                <code style="color:#ef4444;">GraphRecursionError</code> at limit 50.<br>
                User sees: blank screen.
              </p>
              <hr style="border-color:#fecaca; margin:10px 0;"/>
              <div style="font-size:0.65rem; font-weight:700; text-transform:uppercase;
                          letter-spacing:1px; color:#22c55e; margin-bottom:6px;">Fix</div>
              <p style="font-size:0.8rem; color:#334155; margin:0 0 10px;">
                Added <code style="color:#22c55e;">audit_retry_count</code> to GraphState.
                Increments on each audit fail.
                Routes to <code style="color:#f59e0b;">fallback_node</code> at cap.
                Resets on new code generation.
              </p>
              <hr style="border-color:#fecaca; margin:10px 0;"/>
              <p style="font-size:0.72rem; color:#64748b; margin:0;">
                <strong style="color:#1e293b;">Different failure types need separate counters.</strong>
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c2:
        st.markdown(
            """
            <div class="card card-orange" style="height:100%;">
              <div class="card-title" style="color:#f59e0b;">Problem 2 · Traceback Noise</div>
              <p style="font-size:0.8rem; color:#334155; margin:0 0 10px;">
                Full tracebacks = 2000+ chars.<br>
                Real error buried in the middle.<br>
                LLM "fixed" wrong lines.<br>
                Retry success rate: low.
              </p>
              <hr style="border-color:#fed7aa; margin:10px 0;"/>
              <div style="font-size:0.65rem; font-weight:700; text-transform:uppercase;
                          letter-spacing:1px; color:#22c55e; margin-bottom:6px;">Fix</div>
              <p style="font-size:0.8rem; color:#334155; margin:0 0 10px;">
                <code>_compress_traceback()</code>:<br>
                Extract last 5 lines + last <code>File "...", line N</code>.
                Prepend structured signal:<br>
                <code style="font-size:0.72rem; color:#f59e0b;">TIMEOUT / NO_OUTPUT / RUNTIME_ERROR</code><br>
                2000 chars → 200, structured.
              </p>
              <hr style="border-color:#fed7aa; margin:10px 0;"/>
              <p style="font-size:0.72rem; color:#64748b; margin:0;">
                <strong style="color:#1e293b;">Root-cause classification before LLM = better fix direction.</strong>
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c3:
        st.markdown(
            """
            <div class="card card-purple" style="height:100%;">
              <div class="card-title" style="color:#a855f7;">Problem 3 · NameError Guessing</div>
              <p style="font-size:0.8rem; color:#334155; margin:0 0 10px;">
                <code style="font-size:0.72rem; color:#ef4444;">NameError: name 'Write' is not defined</code><br><br>
                LLM guesses from memory.<br>
                Manim API versions differ.<br>
                Fix is imprecise or wrong.
              </p>
              <hr style="border-color:#e9d5ff; margin:10px 0;"/>
              <div style="font-size:0.65rem; font-weight:700; text-transform:uppercase;
                          letter-spacing:1px; color:#22c55e; margin-bottom:6px;">Fix</div>
              <p style="font-size:0.8rem; color:#334155; margin:0 0 10px;">
                <code>ApiLookup</code>: regex extracts symbol →
                looks up <code>manim_api_index.json</code> →
                injects exact signature + runnable example into debugger hint.
              </p>
              <hr style="border-color:#e9d5ff; margin:10px 0;"/>
              <p style="font-size:0.72rem; color:#64748b; margin:0;">
                <strong style="color:#1e293b;">Tell LLM the right answer, not just the error.</strong>
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SLIDE 3b — ApiLookup code walkthrough
# ═══════════════════════════════════════════════════════════════════════════════
elif idx == 5:
    st.markdown('<div class="slide-label">03b / Code Deep Dive · Error-Driven RAG</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="slide-title">From <span style="color:#ef4444;">NameError</span> to '
        '<span style="color:#22c55e;">Correct Fix</span> — in One Lookup</div>',
        unsafe_allow_html=True,
    )

    col_l, col_r = st.columns(2, gap="large")

    with col_l:
        st.markdown(
            "<div style='font-size:0.75rem; color:#64748b; margin-bottom:6px;'>"
            "1. Traceback arrives at debugger_node</div>",
            unsafe_allow_html=True,
        )
        st.code(
            """\
NameError: name 'Write' is not defined
  File "scene_abc.py", line 14
    self.play(Write(title))""",
            language="text",
        )

        st.markdown(
            "<div style='font-size:0.75rem; color:#64748b; margin:10px 0 6px;'>"
            "2. ApiLookup extracts symbol name via regex</div>",
            unsafe_allow_html=True,
        )
        st.code(
            """\
_NAMEERROR_RE = re.compile(r"name '(\\w+)' is not defined")

# Matches → "Write"
# Looks up manim_api_index.json
# Returns entry with signature + example""",
            language="python",
        )

    with col_r:
        st.markdown(
            "<div style='font-size:0.75rem; color:#64748b; margin-bottom:6px;'>"
            "3. Debugger hint injected into next generate call</div>",
            unsafe_allow_html=True,
        )
        st.code(
            """\
DIAGNOSIS: Missing import for Write animation class.
FIX: Add Write to the manim import statement.

[Manim API — Write]
  Animates writing a Text or VMobject stroke by stroke.
  Signature: Write(mobject, run_time=1, **kwargs)
  Example:   self.play(Write(Text('Hello')))""",
            language="text",
        )
        st.markdown(
            """
            <div class="card card-green" style="margin-top:12px;">
              <p style="font-size:0.85rem; margin:0; color:#334155;">
                Generator receives <strong>the correct answer</strong>, not just the error.
                NameError fix precision improves significantly.
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SLIDE 4 — RAG System Design
# ═══════════════════════════════════════════════════════════════════════════════
elif idx == 6:
    st.markdown('<div class="slide-label">04 / RAG System Design</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="slide-title">Two-Tier Retrieval: '
        '<span style="color:#a855f7;">Generation</span> + '
        '<span style="color:#f59e0b;">Debug</span></div>',
        unsafe_allow_html=True,
    )

    col_l, spacer, col_r = st.columns([10, 1, 10])

    with col_l:
        st.markdown(
            """
            <div class="card card-purple">
              <div class="card-title" style="color:#a855f7;">Tier 1 — Few-shot at Generation Time</div>
              <p style="font-size:0.82rem; color:#334155; margin:0;">
                <strong>Source:</strong> <code>runs.json</code> (successful past scenes)<br>
                <strong>Model:</strong> <code>all-MiniLM-L6-v2</code> (sentence-transformers)<br>
                <strong>Strategy:</strong> Cosine similarity → top-2 examples injected as few-shot<br>
                <strong>Cold start:</strong> Returns <code>[]</code> gracefully → zero-shot fallback
              </p>
              <div style="background:#f5f3ff; border-radius:6px; padding:8px 12px;
                          font-size:0.75rem; color:#6b21a8; margin-top:12px;">
                Only on first attempt — retry path has specific error feedback already
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_r:
        st.markdown(
            """
            <div class="card card-orange">
              <div class="card-title" style="color:#f59e0b;">Tier 2 — Error-Driven at Debug Time</div>
              <p style="font-size:0.82rem; color:#334155; margin:0;">
                <strong>Source:</strong> <code>manim_api_index.json</code> (57 hand-curated entries)<br>
                <strong>Model:</strong> Regex — deterministic, no ML needed<br>
                <strong>Strategy:</strong> Extract symbol → exact doc lookup<br>
                <strong>SNR:</strong> Only injects docs for the exact failing symbol
              </p>
              <div style="background:#fffbeb; border-radius:6px; padding:8px 12px;
                          font-size:0.75rem; color:#b45309; margin-top:12px;">
                Error-driven fine-grained retrieval &gt; broad retrieval at generation time
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        """
        <div class="card card-blue">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <p style="font-size:0.85rem; margin:0; color:#334155;">
              <span style="color:#2563eb; font-weight:700;">Future:</span>
              Full Manim v0.18 docs vectorized by class/method as chunk unit →
              vector DB → two-level lookup (static index first, vector DB on miss)
            </p>
            <span style="background:#dbeafe; color:#2563eb; border:1px solid #bfdbfe;
                         border-radius:20px; font-size:0.65rem; font-weight:700;
                         padding:4px 14px; white-space:nowrap; margin-left:16px;">
              What's Next
            </span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SLIDE 5 — Results & What's Next
# ═══════════════════════════════════════════════════════════════════════════════
elif idx == 7:
    st.markdown('<div class="slide-label">05 / Results &amp; What\'s Next</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="slide-title">"What It Can Do Now —<br>'
        '<span style="color:#22c55e;">and What I\'d Build Next</span>"</div>',
        unsafe_allow_html=True,
    )

    col_l, col_r = st.columns(2, gap="large")

    with col_l:
        st.markdown("#### Current Capabilities")
        m1, m2 = st.columns(2)
        m3, m4 = st.columns(2)
        for col, val, lbl in [(m1, "2", "Safety layers\nAST + LLM Judge"),
                               (m2, "57", "Manim APIs\nindexed"),
                               (m3, "120s", "Max sandbox\ntimeout"),
                               (m4, "5", "Max retries\nbefore fallback")]:
            col.markdown(
                f"<div class='metric-box'>"
                f"<span class='metric-val'>{val}</span>"
                f"<span class='metric-lbl'>{lbl}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        st.markdown(
            """
            <div class="quote-box" style="margin-top:16px; font-size:0.9rem;">
              "Reliability in LLM pipelines comes from
              <strong>deterministic layers</strong>, not better prompts."
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_r:
        st.markdown("#### If I Had More Time")
        for priority, color, title, desc in [
            ("Priority 1", "#f59e0b", "Task queue (Celery + Redis)",
             "Non-blocking UI, real-time progress via WebSocket. MVP → production."),
            ("Priority 2", "#3b82f6", "Per-task UUID directories",
             "Eliminate file race condition in concurrent usage."),
            ("Priority 3", "#22c55e", "Streaming progress",
             "stream=True for LLM + tail Docker logs for render progress."),
            ("Design", "#a855f7", "Full Manim docs RAG",
             "Chunk by class/method, two-level retrieval with vector DB."),
        ]:
            st.markdown(
                f"""
                <div style="display:flex; gap:10px; align-items:flex-start; margin-bottom:10px;">
                  <span style="background:{color}18; color:{color}; border:1px solid {color}44;
                               border-radius:20px; font-size:0.65rem; font-weight:700;
                               padding:3px 10px; white-space:nowrap; margin-top:2px;">{priority}</span>
                  <div>
                    <div style="font-size:0.82rem; font-weight:700; color:#1e293b;">{title}</div>
                    <div style="font-size:0.78rem; color:#64748b;">{desc}</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ═══════════════════════════════════════════════════════════════════════════════
# SLIDE 6 — Q&A Prep
# ═══════════════════════════════════════════════════════════════════════════════
elif idx == 8:
    st.markdown('<div class="slide-label">06 / Q&amp;A Prep</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="slide-title">Common Follow-up Questions</div>',
        unsafe_allow_html=True,
    )

    qa_pairs = [
        ("Why LangGraph over a while loop?",
         "Control flow isn't linear — different failures route differently. Graph topology + business logic stay separate. Adding a node doesn't touch others."),
        ("Can LLM Judge give false positives?",
         "Yes — but misclassification costs one extra retry, not a wrong video. Execution layer still catches runtime errors. Soft constraint, not hard gate."),
        ("Why Gemini not GPT-4?",
         "Free API quota for development; architecture is model-agnostic — swap to GPT-4 in one line. The engineering decisions don't change."),
        ("Docker cold start latency?",
         "First pull is slow; subsequent runs use local cache. Production: pre-warmed container pool. MVP tradeoff: isolation over speed."),
        ("Concurrent write to runs.json?",
         "Not handled in MVP — single-user scenario. Next: SQLite with WAL mode for native concurrent write support."),
        ("What's the pass rate?",
         "From runs.json data — tell the real number honestly. Prompt optimization, stricter Judge, and RAG injection of successful examples all improve it."),
    ]

    for q, a in qa_pairs:
        st.markdown(
            f"""
            <div class="qa-row">
              <div class="qa-q">"{q}"</div>
              <div class="qa-a">{a}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
