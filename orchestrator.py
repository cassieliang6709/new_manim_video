"""
orchestrator.py

Implements the WorkflowOrchestrator using LangGraph 1.x.

The pipeline is a StateGraph whose nodes are bound methods of the orchestrator,
giving them access to the generator, auditors, and executor without globals.

Pipeline topology
-----------------
                        ┌──────────────────────┐
                        │                      │ audit failed
   START ──► generate ──► audit ──► execute ──►┘ (loop back to generate)
                  ▲               │
                  │               │ execute failed AND retry_count < max_retries
                  └───────────────┘
                                  │
                                  │ execute succeeded  ──► upload ──► END
                                  │ retry_count >= max_retries ──► END

Dependencies:
    pip install langgraph langchain-google-genai google-api-python-client google-auth
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, TypedDict

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from auditor import CodeAuditor
from executor import SandboxExecutor
from generator import ManimCodeGenerator, SceneDescription
from retriever import ApiLookup, RunsRetriever
from uploader import DriveUploader

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex for extracting Python code blocks from LLM responses
# ---------------------------------------------------------------------------

_CODE_FENCE_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)

# Traceback: last "File \"...\", line N" for error location
_FILE_LINE_RE = re.compile(r'File "([^"]+)", line (\d+)')

# Safe fallback Manim script when max_retries reached (unique name to avoid LLM copying)
SAFE_FALLBACK_SCRIPT = '''
from manim import Scene, Text

class VisocodeMaxRetriesScene(Scene):
    def construct(self):
        self.add(Text("Generation failed after max retries."))
        self.wait(1)
'''


def _compress_traceback(traceback: str, last_n_lines: int = 5) -> str:
    """Extract last N lines + last File/line; never drop the real error line.

    Executor often puts the real cause in the FIRST line (e.g. "No .mp4 under ...",
    "Timeout (120s)"). We prepend that line + a short hint so the generator
    always sees whether it was timeout, no output, or runtime error.
    """
    raw = traceback.strip()
    lines = [s for s in raw.splitlines() if s.strip()]
    if not lines:
        return raw[:500]
    # First line often is the actual error from executor — never drop it
    first_line = lines[0].strip()[:300]
    key_phrases = []
    if "Timeout" in raw or "TimeoutExpired" in raw:
        key_phrases.append("TIMEOUT: Manim ran too long; simplify the scene (fewer animations, shorter waits).")
        if "Timeout" in first_line or "timeout" in first_line.lower():
            key_phrases.append(f"Raw: {first_line}")
    elif "No .mp4" in raw or "No .mp4 under" in raw:
        key_phrases.append("NO OUTPUT: Manim did not produce a final .mp4 (crashed or only partial files); simplify or fix the scene.")
        if "No .mp4" in first_line or "No .mp4 under" in first_line:
            key_phrases.append(f"Raw: {first_line}")
    if "NameError" in raw or "AttributeError" in raw:
        key_phrases.append("RUNTIME ERROR: Missing import or wrong API; check manim imports and method names.")
    file_line_matches = list(_FILE_LINE_RE.finditer(traceback))
    location = ""
    if file_line_matches:
        m = file_line_matches[-1]
        location = f" (at {m.group(1)!r} line {m.group(2)})"
    tail = "\n".join(lines[-last_n_lines:])
    body = f"{tail}{location}" if location else tail
    if key_phrases:
        return "\n".join(key_phrases) + "\n\n" + body
    return body


def _extract_code_block(text: str) -> str:
    """Return the Python source inside a markdown fence, or the raw text.

    Handles both triple-backtick python fences and plain triple-backtick
    fences.  If no fence is found the full *text* is returned as-is so the
    caller always gets a non-empty string to work with.

    Args:
        text: Raw LLM response string.

    Returns:
        Extracted (or verbatim) Python source code.
    """
    match = _CODE_FENCE_RE.search(text)
    return match.group(1).strip() if match else text.strip()


# ---------------------------------------------------------------------------
# LangGraph state schema
# ---------------------------------------------------------------------------

class GraphState(TypedDict):
    """Shared mutable state threaded through every LangGraph node.

    All fields have sensible empty-string / zero defaults so the initial dict
    can be constructed without optional handling downstream.

    Attributes:
        user_prompt:   The raw natural-language request from the caller.
        current_code:  Latest Manim Python source produced by the generator.
        error_message: Most recent error from the auditor or executor.
                       Empty string signals "no error".
        retry_count:   How many execution failures have occurred so far.
                       Audit failures do *not* increment this counter.
        output_path:   Absolute host-side path to the rendered ``.mp4`` file.
                       Set only on successful execution.
        status:        Terminal state label written by the last node to run.
                       One of ``"success"`` | ``"max_retries_exceeded"`` | ``""``.
        drive_link:     Google Drive ``webViewLink`` set by ``upload_node`` on
                       a successful upload.  Empty string if upload was skipped
                       or failed.
        debugger_hint:   Optional diagnosis from ``debugger_node`` (only set after
                        execution failure); consumed by ``generate_node`` then cleared.
        is_fallback:    True when the rendered video came from the safe fallback script.
        audit_retry_count: Running count of consecutive audit-only failures.
                        Reset to 0 on audit pass.  When it reaches ``max_retries``
                        the pipeline routes to ``fallback_node`` instead of looping
                        forever (prevents ``GraphRecursionError``).
    """

    user_prompt: str
    current_code: str
    error_message: str
    retry_count: int
    output_path: str
    status: str
    drive_link: str
    debugger_hint: str
    is_fallback: bool
    audit_retry_count: int


# ---------------------------------------------------------------------------
# Pipeline-level enums and result dataclasses (public API)
# ---------------------------------------------------------------------------

class PipelineStatus(Enum):
    """Terminal status of a completed pipeline run."""

    SUCCESS = "success"
    AUDIT_FAILED = "audit_failed"
    EXECUTION_FAILED = "execution_failed"
    MAX_RETRIES_EXCEEDED = "max_retries_exceeded"
    CANCELLED = "cancelled"


@dataclass
class PipelineResult:
    """Final outcome returned to the caller after the graph finishes.

    Attributes:
        status:         Terminal :class:`PipelineStatus`.
        output_files:   Paths to rendered video artefacts (non-empty on success).
        total_attempts: Number of generate→audit→execute cycles that ran.
        drive_link:     Google Drive link if upload succeeded.
        is_fallback:    True if the video is the safe fallback (max_retries reached).
        final_state:    The raw :class:`GraphState` dict at graph termination.
    """

    status: PipelineStatus
    output_files: list[Path] = field(default_factory=list)
    total_attempts: int = 0
    drive_link: str = ""
    is_fallback: bool = False
    final_state: GraphState | None = None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class WorkflowOrchestrator:
    """Coordinates the Manim video generation pipeline via a LangGraph graph.

    The graph is compiled once at construction time (in :meth:`_build_graph`)
    and reused across multiple :meth:`run` calls.

    Node responsibilities
    ---------------------
    ``generate_node``
        Calls the LLM (Claude via ``langchain-anthropic``) to produce or refine
        a Manim scene script.  On the first attempt only *user_prompt* is used;
        on retries the previous *current_code* and *error_message* are included
        so the model can correct its mistakes.

    ``audit_node``
        Passes *current_code* through every :class:`~auditor.CodeAuditor` in
        :attr:`auditors`.  Uses fail-fast: the first failing auditor's issues
        are written to *error_message* and the node returns immediately.

    ``execute_node``
        Delegates to :attr:`executor`.run_manim().  On success it sets
        *output_path* and *status = "success"*.  On failure it increments
        *retry_count* and writes the container traceback to *error_message*.

    ``upload_node``
        Delegates to :attr:`_uploader`.upload_video() when a
        :class:`~uploader.DriveUploader` is configured.  On success it sets
        *drive_link* to the ``webViewLink``.  If no uploader is configured the
        node is a no-op and the graph proceeds directly to END.

    Routing
    -------
    * ``generate → audit``   — unconditional.
    * ``audit → generate``   — when *error_message* is non-empty (audit failed).
    * ``audit → execute``    — when *error_message* is empty (audit passed).
    * ``execute → generate`` — when execution failed AND ``retry_count < max_retries``.
    * ``execute → upload``   — when execution succeeded.
    * ``execute → END``      — when max retries exceeded.
    * ``upload → END``       — unconditional.

    Args:
        generator:   :class:`~generator.ManimCodeGenerator` instance (reserved
                     for future use; LLM calls are currently made directly).
        auditors:    Ordered list of :class:`~auditor.CodeAuditor` instances.
        executor:    :class:`~executor.SandboxExecutor` that runs Docker.
        working_dir: Host directory bind-mounted into the container.
        max_retries: Max number of *execution* failures before giving up.
        model_name:  Gemini model ID used by the generate node.
        drive_uploader: Optional :class:`~uploader.DriveUploader`.  When
                     provided, the rendered ``.mp4`` is uploaded to Google
                     Drive after successful execution and the ``webViewLink``
                     is stored in :attr:`PipelineResult.drive_link`.
    """

    # ------------------------------------------------------------------
    # LLM system prompt
    # ------------------------------------------------------------------

    _SYSTEM_PROMPT: str = """\
You are an expert Manim Community Edition developer (v0.18+).
Your sole task is to write correct, self-contained Manim animation code.

STRICT RULES — violating any rule causes the pipeline to reject your output:
1. Import ONLY from the `manim` package (e.g. `from manim import Scene, Circle`).
2. Define EXACTLY ONE class that subclasses `Scene`, `ThreeDScene`, or
   `MovingCameraScene`.  Name it with a descriptive CamelCase related to the
   topic (e.g. PermutationsDemoScene, BacktrackingScene). Never use FallbackScene
   or VisocodeMaxRetriesScene.
3. Implement `construct(self)` with all animation logic.
4. FORBIDDEN imports: os, sys, subprocess, pathlib, socket, urllib, requests,
   httpx, shutil.  Any of these will cause an immediate audit failure.
5. FORBIDDEN built-ins: exec(), eval(), open(), __import__(), compile().
6. Output ONLY a fenced Python code block — no prose, no explanations, no
   markdown outside the fence.
7. Do NOT use MathTex or Tex — they require LaTeX. Use Text() for labels/formulas.
8. In the opening line you MUST import every name from manim that you use in the
   code (e.g. Scene, Circle, Create, Write, FadeIn, FadeOut, Text, BLUE, UP, DOWN,
   Axes, Dot, Line, etc.). If you use Write(...) you must have Write in the import.
   Missing import = NameError at runtime.
9. Use relative positioning (e.g. .next_to(), .align_to()) instead of absolute
   coordinates (e.g. UP * 3) so elements do not overlap and stay within screen
   bounds.
10. Keep the scene SHORT so it renders within the timeout: total animation
    under ~20–30 seconds. Prefer 3–5 self.play() calls total; avoid long
    self.wait() or many sequential animations. Long scenes often hit timeouts
    and only produce partial_movie_files, causing "No .mp4" failures.

CORRECT OUTPUT FORMAT:
```python
from manim import Scene, Circle, BLUE, Create, Write

class ExampleScene(Scene):
    def construct(self):
        circle = Circle(color=BLUE)
        self.play(Create(circle))
        self.play(Write(Text("hello")))
        self.wait(1)
```
"""

    _DEBUGGER_SYSTEM = """You are a debugger for Manim (math animation) Python code.
Given the code and the error output, reply with exactly two lines:
Line 1: DIAGNOSIS: <one short sentence: what went wrong>
Line 2: FIX: <one short sentence: what to change>
No code, no preamble. Only these two lines."""

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        auditors: list[CodeAuditor],
        executor: SandboxExecutor,
        working_dir: Path,
        max_retries: int = 3,
        model_name: str = "gemini-2.5-pro",
        temperature: float = 0.2,
        top_p: float = 0.95,
        drive_uploader: DriveUploader | None = None,
        generator: ManimCodeGenerator | None = None,
    ) -> None:
        self.generator = generator
        self.auditors = auditors
        self.executor = executor
        self.working_dir = Path(working_dir)
        self.max_retries = max_retries
        self.drive_uploader: DriveUploader | None = drive_uploader

        self._llm = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temperature,
            top_p=top_p,
        )
        # RAG retriever: finds similar past successful scenes from runs.json.
        # Gracefully returns [] when the file is missing or has no valid entries.
        self._retriever = RunsRetriever(
            runs_path=self.working_dir / "runs.json",
            top_k=2,
        )
        # API lookup: error-driven; extracts symbol names from NameError /
        # AttributeError tracebacks and returns matching Manim API docs.
        self._api_lookup = ApiLookup(
            index_path=Path(__file__).resolve().parent / "manim_api_index.json",
        )
        # Compile the graph once; reuse across run() calls.
        self._graph: CompiledStateGraph = self._build_graph()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, description: SceneDescription) -> PipelineResult:
        """Execute the full generation pipeline and return the result.

        Constructs an initial :class:`GraphState`, invokes the compiled
        LangGraph graph, and translates the final state into a
        :class:`PipelineResult`.

        Args:
            description: High-level specification of the scene to render.

        Returns:
            A :class:`PipelineResult` describing the outcome.
        """
        initial_state: GraphState = {
            "user_prompt": description.narrative,
            "current_code": "",
            "error_message": "",
            "retry_count": 0,
            "output_path": "",
            "status": "",
            "drive_link": "",
            "debugger_hint": "",
            "is_fallback": False,
            "audit_retry_count": 0,
        }

        _logger.info(
            "Starting pipeline for: '%s'  (max_retries=%d)",
            description.narrative[:80],
            self.max_retries,
        )

        # recursion_limit caps total node invocations to prevent infinite loops
        # from audit-only cycles.  50 is generous for a 3-retry pipeline.
        final_state: GraphState = self._graph.invoke(
            initial_state,
            config={"recursion_limit": 50},
        )

        _logger.info("Pipeline finished — status=%s", final_state.get("status"))
        return self._state_to_result(final_state)

    # ------------------------------------------------------------------
    # LangGraph nodes
    # Each node receives the full GraphState and returns a *partial* dict
    # containing only the keys it wants to update.
    # ------------------------------------------------------------------

    def generate_node(self, state: GraphState) -> dict[str, Any]:
        """Generate or refine Manim source code using the LLM.

        Calls the Gemini LLM (via ``langchain-google-genai``) to produce or
        refine a Manim scene script.  Detects whether this is a first attempt
        or a retry by inspecting *current_code* and *error_message*:

        * **First attempt** — sends only *user_prompt*.
        * **Retry** — sends *user_prompt*, the previous *current_code*, and
          the structured *error_message* so the model can self-correct.

        Args:
            state: Current pipeline state.

        Returns:
            Partial state update with ``current_code`` set to the newly
            generated source, ``error_message`` cleared, and
            ``audit_retry_count`` reset to 0.
        """
        is_retry = bool(state["current_code"] or state["error_message"])

        if is_retry:
            feedback = self._build_feedback(state)
            user_content = (
                f"Scene request: {state['user_prompt']}\n\n"
                f"Your previous Manim code failed with the following error.\n"
                f"Fix the problem and return the complete corrected code.\n\n"
                f"--- Previous code ---\n"
                f"```python\n{state['current_code']}\n```\n\n"
                f"--- Error ---\n{feedback}\n\n"
                f"Generate the corrected Manim scene:"
            )
        else:
            # ── RAG: inject similar successful past scenes as few-shot context ──
            # Only on the first attempt; retries focus on the specific error instead.
            few_shot = ""
            try:
                examples = self._retriever.get_examples(state["user_prompt"])
                if examples:
                    parts = [
                        f"Request: {ex['prompt']}\n"
                        f"```python\n{ex['code']}\n```"
                        for ex in examples
                    ]
                    few_shot = (
                        "Here are similar successful Manim scenes for reference "
                        "(study their style and structure — do NOT copy verbatim):\n\n"
                        + "\n\n---\n\n".join(parts)
                        + "\n\n---\n\n"
                    )
                    _logger.info(
                        "generate_node: injecting %d RAG example(s)", len(examples)
                    )
                else:
                    _logger.debug("generate_node: no RAG examples (cold start)")
            except Exception as exc:
                _logger.warning("generate_node: RAG retrieval failed — %s", exc)
            # ─────────────────────────────────────────────────────────────────
            user_content = (
                f"{few_shot}"
                f"Create a Manim animation scene for the following request:\n\n"
                f"{state['user_prompt']}"
            )

        messages = [
            SystemMessage(content=self._SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]

        _logger.info(
            "generate_node: calling LLM (is_retry=%s, retry_count=%d)",
            is_retry,
            state["retry_count"],
        )

        response = self._llm.invoke(messages)
        code = _extract_code_block(str(response.content))

        _logger.debug("generate_node: received %d chars of code", len(code))

        return {
            "current_code": code,
            "error_message": "",
            "debugger_hint": "",    # consumed; clear for next round
            "audit_retry_count": 0, # fresh code → reset audit counter
        }

    def audit_node(self, state: GraphState) -> dict[str, Any]:
        """Run all registered auditors against *current_code*.

        Iterates :attr:`auditors` in order and returns immediately on the first
        failure (fail-fast).  If every auditor passes, *error_message* is set
        to an empty string to signal success.

        Args:
            state: Current pipeline state (must have *current_code* populated).

        Returns:
            Partial state update with ``error_message`` set to the failure
            reason, or empty string on full pass.
        """
        code = state["current_code"]
        _logger.info("audit_node: running %d auditor(s)", len(self.auditors))

        ctx = {"user_prompt": state["user_prompt"]}
        for auditor in self.auditors:
            result = auditor.audit(code, context=ctx)
            if not result.passed:
                reason = "; ".join(result.issues)
                new_audit_count = state["audit_retry_count"] + 1
                _logger.warning(
                    "audit_node: FAILED (audit_retry_count=%d) — %s",
                    new_audit_count,
                    reason,
                )
                return {
                    "error_message": f"[AUDIT] {reason}",
                    "audit_retry_count": new_audit_count,
                }

        _logger.info("audit_node: all auditors passed")
        return {"error_message": "", "audit_retry_count": 0}

    def execute_node(self, state: GraphState) -> dict[str, Any]:
        """Execute *current_code* inside the Docker sandbox.

        Delegates to :meth:`~executor.SandboxExecutor.run_manim`.

        * **Success** — sets ``output_path``, clears ``error_message``, and
          marks ``status = "success"``.
        * **Failure** — appends the container traceback to ``error_message``
          and increments ``retry_count``.  When ``retry_count`` reaches
          :attr:`max_retries`, also sets ``status = "max_retries_exceeded"``
          so the routing function can route to END without another loop.

        Args:
            state: Current pipeline state (must have passed audit).

        Returns:
            Partial state update reflecting success or failure.
        """
        _logger.info(
            "execute_node: launching sandbox (retry_count=%d)",
            state["retry_count"],
        )

        outcome = self.executor.run_manim(
            state["current_code"],
            str(self.working_dir),
        )

        if outcome["status"] == "success":
            _logger.info("execute_node: success — %s", outcome["output_path"])
            return {
                "output_path": outcome["output_path"],
                "error_message": "",
                "status": "success",
            }

        # ── Execution failed ────────────────────────────────────────────────
        traceback: str = outcome.get("traceback", "Unknown execution error")
        new_retry_count = state["retry_count"] + 1

        _logger.warning(
            "execute_node: FAILED (new retry_count=%d)\n%s",
            new_retry_count,
            traceback[:600],
        )

        updates: dict[str, Any] = {
            "error_message": f"[EXECUTE] {traceback}",
            "retry_count": new_retry_count,
        }

        if new_retry_count >= self.max_retries:
            updates["status"] = "max_retries_exceeded"
            _logger.error(
                "execute_node: max retries (%d) reached — stopping.",
                self.max_retries,
            )

        return updates

    def debugger_node(self, state: GraphState) -> dict[str, Any]:
        """Run after execution failure: ask LLM for a short diagnosis + fix hint.

        Result is stored in *debugger_hint* and consumed by generate_node in
        _build_feedback(); generate_node clears it after use.
        """
        err = (state.get("error_message") or "").strip()
        if not err.startswith("[EXECUTE]"):
            return {"debugger_hint": ""}
        traceback = _compress_traceback(err[len("[EXECUTE]"):].strip(), last_n_lines=5)
        code = state.get("current_code", "")

        messages = [
            SystemMessage(content=self._DEBUGGER_SYSTEM),
            HumanMessage(content=f"Code:\n```python\n{code[:3000]}\n```\n\nError:\n{traceback}"),
        ]
        try:
            response = self._llm.invoke(messages)
            text = (response.content or "").strip()
        except Exception as e:
            _logger.warning("debugger_node: LLM call failed — %s", e)
            return {"debugger_hint": ""}
        if not text:
            return {"debugger_hint": ""}

        # ── API lookup: append relevant Manim docs for any NameError / AttributeError
        api_snippet = self._api_lookup.suggest_for_error(err)
        if api_snippet:
            _logger.info("debugger_node: api_lookup found relevant docs")
            hint = f"{text[:400]}\n\n{api_snippet}"
        else:
            hint = text[:500]

        _logger.info("debugger_node: hint length=%d", len(hint))
        return {"debugger_hint": hint[:800]}

    def fallback_node(self, state: GraphState) -> dict[str, Any]:
        """Run a minimal safe Manim script when max_retries was reached.

        Renders a short fallback video so the user still gets an output.
        On success: sets output_path, status="success", is_fallback=True.
        On failure: sets status="max_retries_exceeded" (no video).
        """
        _logger.info("fallback_node: running safe fallback script")
        outcome = self.executor.run_manim(SAFE_FALLBACK_SCRIPT, str(self.working_dir))

        if outcome["status"] == "success":
            _logger.info("fallback_node: success — %s", outcome["output_path"])
            return {
                "output_path": outcome["output_path"],
                "status": "success",
                "is_fallback": True,
            }
        _logger.error("fallback_node: safe script failed — %s", outcome.get("traceback", "")[:400])
        return {"status": "max_retries_exceeded"}

    def upload_node(self, state: GraphState) -> dict[str, Any]:
        """Upload the rendered video to Google Drive.

        Runs only when :attr:`_uploader` is configured.  If no uploader is
        set this node is a transparent pass-through (returns an empty dict)
        and the graph proceeds to END without modification.

        On a successful upload, ``drive_link`` is set to the ``webViewLink``
        returned by :meth:`~uploader.DriveUploader.upload_video`.  On failure
        (the uploader returns an empty string) the node logs a warning and
        still allows the graph to finish — a failed upload does not invalidate
        a successfully rendered video.

        Args:
            state: Current pipeline state (must have ``output_path`` set).

        Returns:
            Partial state update with ``drive_link`` populated, or an empty
            dict if no uploader is configured.
        """
        if self.drive_uploader is None:
            _logger.debug("upload_node: no uploader configured — skipping")
            return {}

        output_path = state["output_path"]
        file_name = Path(output_path).name

        _logger.info("upload_node: uploading '%s' to Google Drive", file_name)
        drive_link = self.drive_uploader.upload_video(output_path, file_name)

        if drive_link:
            _logger.info("upload_node: drive_link=%s", drive_link)
        else:
            _logger.warning(
                "upload_node: upload failed for '%s' — drive_link left empty",
                file_name,
            )

        return {"drive_link": drive_link}

    # ------------------------------------------------------------------
    # Conditional edge routing functions
    # Must accept (state) and return a node name string or END.
    # ------------------------------------------------------------------

    def _route_after_audit(self, state: GraphState) -> str:
        """Route after ``audit_node``.

        Returns:
            * ``"execute_node"``   — audit passed.
            * ``"generate_node"``  — audit failed and retries remain.
            * ``"fallback_node"``  — audit failed ``max_retries`` times in a
              row without any execution attempt; prevents ``GraphRecursionError``
              from exhausting ``recursion_limit``.
        """
        if state["error_message"]:
            if state["audit_retry_count"] >= self.max_retries:
                _logger.warning(
                    "route_after_audit → fallback_node "
                    "(audit_retry_count=%d reached cap of %d)",
                    state["audit_retry_count"],
                    self.max_retries,
                )
                return "fallback_node"
            _logger.info(
                "route_after_audit → generate_node "
                "(audit failed, audit_retry_count=%d)",
                state["audit_retry_count"],
            )
            return "generate_node"
        _logger.info("route_after_audit → execute_node (audit passed)")
        return "execute_node"

    def _route_after_execute(self, state: GraphState) -> str:
        """Route after ``execute_node``.

        Returns:
            * ``"upload_node"`` — execution succeeded (upload or pass-through).
            * ``"generate_node"`` — execution failed but retries remain.
            * ``END`` — max retries reached (``status`` carries the reason).
        """
        if state["status"] == "success":
            _logger.info("route_after_execute → upload_node (success)")
            return "upload_node"

        if state["retry_count"] < self.max_retries:
            _logger.info(
                "route_after_execute → debugger_node (retry %d/%d)",
                state["retry_count"],
                self.max_retries,
            )
            return "debugger_node"

        _logger.warning(
            "route_after_execute → fallback_node (max_retries=%d exhausted)",
            self.max_retries,
        )
        return "fallback_node"

    def _route_after_fallback(self, state: GraphState) -> str:
        """Route after fallback_node: upload on success, else END."""
        if state.get("status") == "success":
            return "upload_node"
        return END

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build_graph(self) -> CompiledStateGraph:
        """Construct and compile the LangGraph ``StateGraph``.

        Graph structure::

            START
              │
              ▼
         generate_node
              │ (always)
              ▼
          audit_node ──── audit failed ──────────────────┐
              │                                           │
          audit passed                                   │
              │                                           ▼
              ▼                                    generate_node
         execute_node                                (retry loop)
              │ success                                   ▲
              ▼                                           │
         upload_node      execute failed, retries left ───┘
              │
              ▼
             END           execute failed, no retries left ──► END

        Returns:
            A compiled :class:`~langgraph.graph.state.CompiledStateGraph`
            ready for ``.invoke()``.
        """
        graph: StateGraph = StateGraph(GraphState)

        # ── Register nodes ──────────────────────────────────────────────────
        graph.add_node("generate_node", self.generate_node)
        graph.add_node("audit_node", self.audit_node)
        graph.add_node("execute_node", self.execute_node)
        graph.add_node("debugger_node", self.debugger_node)
        graph.add_node("fallback_node", self.fallback_node)
        graph.add_node("upload_node", self.upload_node)

        # ── Entry point ─────────────────────────────────────────────────────
        graph.set_entry_point("generate_node")

        # ── Fixed edge: generate → audit (unconditional) ────────────────────
        graph.add_edge("generate_node", "audit_node")

        # ── Fixed edge: upload → END (unconditional) ─────────────────────────
        graph.add_edge("upload_node", END)

        # ── Conditional edge: audit → generate | execute | fallback ─────────
        graph.add_conditional_edges(
            "audit_node",
            self._route_after_audit,
            {
                "generate_node": "generate_node",
                "execute_node": "execute_node",
                "fallback_node": "fallback_node",
            },
        )

        # ── Conditional edge: execute → upload | debugger | fallback ─────────
        graph.add_conditional_edges(
            "execute_node",
            self._route_after_execute,
            {
                "upload_node": "upload_node",
                "debugger_node": "debugger_node",
                "fallback_node": "fallback_node",
            },
        )

        # ── Fixed edge: debugger → generate (retry path) ─────────────────────
        graph.add_edge("debugger_node", "generate_node")

        # ── Conditional edge: fallback → upload | END ───────────────────────
        graph.add_conditional_edges(
            "fallback_node",
            self._route_after_fallback,
            {"upload_node": "upload_node", END: END},
        )

        return graph.compile()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_feedback(self, state: GraphState) -> str:
        """Compile a structured feedback string for the LLM refinement prompt.

        Formats the *error_message* from the previous node (audit or execute)
        into a short block the model can act on.

        Args:
            state: The pipeline state after a failed attempt.

        Returns:
            A formatted, human-readable feedback string.
        """
        msg = state.get("error_message", "").strip()
        if not msg:
            return "An unknown error occurred during the previous attempt."

        if msg.startswith("[AUDIT]"):
            return (
                "Security audit failed — the following dangerous constructs "
                f"were detected and must be removed:\n{msg[len('[AUDIT]'):].strip()}"
            )

        if msg.startswith("[EXECUTE]"):
            traceback = msg[len("[EXECUTE]"):].strip()
            compressed = _compress_traceback(traceback, last_n_lines=5)
            base = f"The Manim render failed. Fix the code using this error (last 5 lines + location):\n{compressed}"
            hint = state.get("debugger_hint", "").strip()
            if hint:
                base = f"Diagnosis from debugger:\n{hint}\n\n{base}"
            return base

        return msg

    def _collect_outputs(self, final_state: GraphState) -> list[Path]:
        """Extract output file paths from a successful final state.

        Args:
            final_state: The graph state after execution.

        Returns:
            A list containing the single rendered ``.mp4`` path, or an empty
            list if execution did not succeed.
        """
        output_path = final_state.get("output_path", "")
        return [Path(output_path)] if output_path else []

    def _state_to_result(self, final_state: GraphState) -> PipelineResult:
        """Translate a raw :class:`GraphState` into a :class:`PipelineResult`.

        Args:
            final_state: The terminal state dict produced by the graph.

        Returns:
            A :class:`PipelineResult` with the appropriate :class:`PipelineStatus`.
        """
        raw_status = final_state.get("status", "")

        if raw_status == "success":
            pipeline_status = PipelineStatus.SUCCESS
        elif raw_status == "max_retries_exceeded":
            pipeline_status = PipelineStatus.MAX_RETRIES_EXCEEDED
        elif final_state.get("error_message", "").startswith("[AUDIT]"):
            # Graph ended mid-audit-loop (shouldn't normally happen)
            pipeline_status = PipelineStatus.AUDIT_FAILED
        else:
            pipeline_status = PipelineStatus.EXECUTION_FAILED

        return PipelineResult(
            status=pipeline_status,
            output_files=self._collect_outputs(final_state),
            total_attempts=final_state.get("retry_count", 0) + 1,
            drive_link=final_state.get("drive_link", ""),
            is_fallback=bool(final_state.get("is_fallback", False)),
            final_state=final_state,
        )
