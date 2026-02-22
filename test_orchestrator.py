"""
test_orchestrator.py

Unit tests for WorkflowOrchestrator.

All external dependencies (LLM, Docker, auditors) are mocked so the tests
run offline and without any infrastructure.  The focus is on:

1. Graph topology — does the routing logic visit the right nodes?
2. Retry mechanics — does retry_count increment correctly on execute failures?
3. Audit failures  — do audit failures loop back to generate without
                      touching retry_count?
4. Max retries      — does the pipeline stop and report the right status?
5. Success path     — is PipelineResult populated correctly?
6. Helper functions — _extract_code_block, _build_feedback, _state_to_result.

Run with:
    python -m pytest test_orchestrator.py -v
or:
    python -m unittest test_orchestrator -v
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from auditor import AuditResult, SecurityAuditor
from executor import SandboxExecutor
from generator import ManimCodeGenerator, SceneComplexity, SceneDescription
from orchestrator import (
    GraphState,
    PipelineResult,
    PipelineStatus,
    WorkflowOrchestrator,
    _extract_code_block,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CLEAN_CODE = """\
from manim import Scene, Circle, BLUE, Create

class BallScene(Scene):
    def construct(self):
        self.play(Create(Circle(color=BLUE)))
        self.wait(1)
"""

DIRTY_CODE = "import os\nos.system('rm -rf /')"


def _make_description(narrative: str = "Draw a blue circle") -> SceneDescription:
    return SceneDescription(
        title="TestScene",
        narrative=narrative,
        complexity=SceneComplexity.SIMPLE,
    )


def _make_orchestrator(
    auditors=None,
    executor_mock=None,
    max_retries: int = 3,
) -> tuple[WorkflowOrchestrator, MagicMock]:
    """Build a WorkflowOrchestrator with a mocked LLM and configurable mocks."""
    generator = MagicMock(spec=ManimCodeGenerator)
    executor = executor_mock or MagicMock(spec=SandboxExecutor)
    auditors = auditors or [SecurityAuditor()]

    with patch("orchestrator.ChatGoogleGenerativeAI"):
        orch = WorkflowOrchestrator(
            generator=generator,
            auditors=auditors,
            executor=executor,
            working_dir=Path("/tmp/test_output"),
            max_retries=max_retries,
            model_name="claude-sonnet-4-6",
        )

    return orch, executor


# ---------------------------------------------------------------------------
# Tests: _extract_code_block (module-level helper)
# ---------------------------------------------------------------------------

class TestExtractCodeBlock(unittest.TestCase):

    def test_extracts_python_fenced_block(self) -> None:
        text = "Some text\n```python\nx = 1\n```\nMore text"
        self.assertEqual(_extract_code_block(text), "x = 1")

    def test_extracts_plain_fenced_block(self) -> None:
        text = "```\nprint('hello')\n```"
        self.assertEqual(_extract_code_block(text), "print('hello')")

    def test_returns_raw_text_when_no_fence(self) -> None:
        text = "x = 1 + 2"
        self.assertEqual(_extract_code_block(text), "x = 1 + 2")

    def test_strips_whitespace(self) -> None:
        text = "```python\n\n  x = 1  \n\n```"
        self.assertEqual(_extract_code_block(text), "x = 1")

    def test_multiline_code_preserved(self) -> None:
        code = "def foo():\n    return 42"
        text = f"```python\n{code}\n```"
        self.assertEqual(_extract_code_block(text), code)


# ---------------------------------------------------------------------------
# Tests: individual nodes (called directly, no graph invocation)
# ---------------------------------------------------------------------------

class TestGenerateNode(unittest.TestCase):
    """Call generate_node directly to verify prompt selection."""

    def setUp(self) -> None:
        self.orch, _ = _make_orchestrator()
        # Patch the internal _llm to return deterministic output
        self.orch._llm = MagicMock()
        self.orch._llm.invoke.return_value = MagicMock(
            content=f"```python\n{CLEAN_CODE}\n```"
        )

    def _base_state(self, **overrides) -> GraphState:
        return {
            "user_prompt": "Draw a circle",
            "current_code": "",
            "error_message": "",
            "retry_count": 0,
            "output_path": "",
            "status": "",
            **overrides,
        }

    def test_first_call_clears_error_message(self) -> None:
        result = self.orch.generate_node(self._base_state())
        self.assertEqual(result["error_message"], "")

    def test_first_call_returns_code(self) -> None:
        result = self.orch.generate_node(self._base_state())
        self.assertIn("BallScene", result["current_code"])

    def test_retry_call_includes_previous_error_in_prompt(self) -> None:
        state = self._base_state(
            current_code=CLEAN_CODE,
            error_message="[EXECUTE] NameError: name 'x' is not defined",
        )
        self.orch.generate_node(state)

        # Inspect the HumanMessage content passed to the LLM
        human_msg = self.orch._llm.invoke.call_args[0][0][1]
        self.assertIn("NameError", human_msg.content)
        self.assertIn(CLEAN_CODE[:30], human_msg.content)

    def test_code_extracted_from_fenced_response(self) -> None:
        self.orch._llm.invoke.return_value = MagicMock(
            content="Here is the code:\n```python\nprint('hi')\n```\nDone."
        )
        result = self.orch.generate_node(self._base_state())
        self.assertEqual(result["current_code"], "print('hi')")


class TestAuditNode(unittest.TestCase):

    def setUp(self) -> None:
        self.orch, _ = _make_orchestrator(auditors=[SecurityAuditor()])

    def _state(self, code: str) -> GraphState:
        return {
            "user_prompt": "test",
            "current_code": code,
            "error_message": "",
            "retry_count": 0,
            "output_path": "",
            "status": "",
        }

    def test_clean_code_clears_error_message(self) -> None:
        result = self.orch.audit_node(self._state(CLEAN_CODE))
        self.assertEqual(result["error_message"], "")

    def test_dirty_code_sets_audit_error(self) -> None:
        result = self.orch.audit_node(self._state(DIRTY_CODE))
        self.assertIn("[AUDIT]", result["error_message"])
        self.assertIn("os", result["error_message"])

    def test_multiple_auditors_fail_fast(self) -> None:
        """First failing auditor stops the chain; second is never called."""
        a1 = MagicMock(spec=SecurityAuditor)
        a1.audit.return_value = AuditResult(passed=False, issues=["blocked import"])
        a2 = MagicMock(spec=SecurityAuditor)
        a2.audit.return_value = AuditResult(passed=True)

        orch, _ = _make_orchestrator(auditors=[a1, a2])
        result = orch.audit_node(self._state(DIRTY_CODE))

        a1.audit.assert_called_once()
        a2.audit.assert_not_called()
        self.assertIn("[AUDIT]", result["error_message"])

    def test_all_auditors_pass(self) -> None:
        a1 = MagicMock(spec=SecurityAuditor)
        a1.audit.return_value = AuditResult(passed=True)
        a2 = MagicMock(spec=SecurityAuditor)
        a2.audit.return_value = AuditResult(passed=True)

        orch, _ = _make_orchestrator(auditors=[a1, a2])
        result = orch.audit_node(self._state(CLEAN_CODE))
        self.assertEqual(result["error_message"], "")


class TestExecuteNode(unittest.TestCase):

    def _state(self, retry_count: int = 0) -> GraphState:
        return {
            "user_prompt": "test",
            "current_code": CLEAN_CODE,
            "error_message": "",
            "retry_count": retry_count,
            "output_path": "",
            "status": "",
        }

    def test_success_sets_output_path_and_status(self) -> None:
        executor = MagicMock(spec=SandboxExecutor)
        executor.run_manim.return_value = {
            "status": "success",
            "output_path": "/tmp/scene.mp4",
        }
        orch, _ = _make_orchestrator(executor_mock=executor)
        result = orch.execute_node(self._state())
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["output_path"], "/tmp/scene.mp4")
        self.assertEqual(result["error_message"], "")

    def test_failure_increments_retry_count(self) -> None:
        executor = MagicMock(spec=SandboxExecutor)
        executor.run_manim.return_value = {
            "status": "error",
            "traceback": "Traceback:\n  ...\nValueError",
        }
        orch, _ = _make_orchestrator(executor_mock=executor, max_retries=3)
        result = orch.execute_node(self._state(retry_count=0))
        self.assertEqual(result["retry_count"], 1)
        self.assertIn("[EXECUTE]", result["error_message"])

    def test_failure_at_max_retries_sets_status(self) -> None:
        executor = MagicMock(spec=SandboxExecutor)
        executor.run_manim.return_value = {
            "status": "error",
            "traceback": "Fatal error",
        }
        orch, _ = _make_orchestrator(executor_mock=executor, max_retries=3)
        # retry_count=2 means this is the 3rd failure → should hit max
        result = orch.execute_node(self._state(retry_count=2))
        self.assertEqual(result["retry_count"], 3)
        self.assertEqual(result["status"], "max_retries_exceeded")

    def test_failure_below_max_does_not_set_terminal_status(self) -> None:
        executor = MagicMock(spec=SandboxExecutor)
        executor.run_manim.return_value = {
            "status": "error",
            "traceback": "Some error",
        }
        orch, _ = _make_orchestrator(executor_mock=executor, max_retries=3)
        result = orch.execute_node(self._state(retry_count=1))
        self.assertNotIn("status", result)  # no status key means no override


# ---------------------------------------------------------------------------
# Tests: routing functions
# ---------------------------------------------------------------------------

class TestRoutingFunctions(unittest.TestCase):

    def setUp(self) -> None:
        self.orch, _ = _make_orchestrator()

    def _state(self, **kwargs) -> GraphState:
        base: GraphState = {
            "user_prompt": "test",
            "current_code": "",
            "error_message": "",
            "retry_count": 0,
            "output_path": "",
            "status": "",
        }
        base.update(kwargs)
        return base

    # ── _route_after_audit ──────────────────────────────────────────────────

    def test_audit_passed_routes_to_execute(self) -> None:
        state = self._state(error_message="")
        self.assertEqual(self.orch._route_after_audit(state), "execute_node")

    def test_audit_failed_routes_to_generate(self) -> None:
        state = self._state(error_message="[AUDIT] blocked import 'os'")
        self.assertEqual(self.orch._route_after_audit(state), "generate_node")

    # ── _route_after_execute ────────────────────────────────────────────────

    def test_execute_success_routes_to_upload_node(self) -> None:
        state = self._state(status="success", output_path="/tmp/x.mp4")
        self.assertEqual(self.orch._route_after_execute(state), "upload_node")

    def test_execute_failure_with_retries_routes_to_generate(self) -> None:
        state = self._state(
            error_message="[EXECUTE] crash",
            retry_count=1,
            status="",
        )
        self.assertEqual(self.orch._route_after_execute(state), "generate_node")

    def test_execute_failure_at_max_retries_routes_to_end(self) -> None:
        from langgraph.graph import END
        state = self._state(
            error_message="[EXECUTE] crash",
            retry_count=3,          # == max_retries
            status="max_retries_exceeded",
        )
        self.assertEqual(self.orch._route_after_execute(state), END)


# ---------------------------------------------------------------------------
# Tests: full graph via _graph.invoke() (all I/O mocked)
# ---------------------------------------------------------------------------

class TestFullGraphIntegration(unittest.TestCase):
    """Exercise the compiled graph end-to-end using fully mocked nodes."""

    def _build_orch(self, max_retries: int = 3) -> WorkflowOrchestrator:
        with patch("orchestrator.ChatGoogleGenerativeAI"):
            orch = WorkflowOrchestrator(
                generator=MagicMock(spec=ManimCodeGenerator),
                auditors=[SecurityAuditor()],
                executor=MagicMock(spec=SandboxExecutor),
                working_dir=Path("/tmp/test"),
                max_retries=max_retries,
            )
        return orch

    def test_happy_path_succeeds(self) -> None:
        orch = self._build_orch()

        orch._llm = MagicMock()
        orch._llm.invoke.return_value = MagicMock(
            content=f"```python\n{CLEAN_CODE}\n```"
        )
        orch.executor.run_manim.return_value = {
            "status": "success",
            "output_path": "/tmp/output/scene.mp4",
        }

        result = orch.run(_make_description())

        self.assertEqual(result.status, PipelineStatus.SUCCESS)
        self.assertEqual(result.output_files, [Path("/tmp/output/scene.mp4")])
        self.assertEqual(result.total_attempts, 1)

    def test_audit_failure_then_success(self) -> None:
        """First LLM call produces dirty code; second produces clean code."""
        orch = self._build_orch()

        call_count = 0

        def _llm_side_effect(messages, **kwargs):
            nonlocal call_count
            call_count += 1
            code = DIRTY_CODE if call_count == 1 else CLEAN_CODE
            return MagicMock(content=f"```python\n{code}\n```")

        orch._llm = MagicMock()
        orch._llm.invoke.side_effect = _llm_side_effect
        orch.executor.run_manim.return_value = {
            "status": "success",
            "output_path": "/tmp/output/scene.mp4",
        }

        result = orch.run(_make_description())

        self.assertEqual(result.status, PipelineStatus.SUCCESS)
        # LLM called twice (first dirty, then clean)
        self.assertEqual(orch._llm.invoke.call_count, 2)
        # Audit failure doesn't increment retry_count, so total_attempts == 1
        self.assertEqual(result.total_attempts, 1)

    def test_execute_failure_retries_and_succeeds(self) -> None:
        """First execution fails; second succeeds."""
        orch = self._build_orch(max_retries=3)

        orch._llm = MagicMock()
        orch._llm.invoke.return_value = MagicMock(
            content=f"```python\n{CLEAN_CODE}\n```"
        )

        run_call_count = 0

        def _executor_side_effect(code, output_dir):
            nonlocal run_call_count
            run_call_count += 1
            if run_call_count == 1:
                return {"status": "error", "traceback": "NameError: 'x'"}
            return {"status": "success", "output_path": "/tmp/scene.mp4"}

        orch.executor.run_manim.side_effect = _executor_side_effect

        result = orch.run(_make_description())

        self.assertEqual(result.status, PipelineStatus.SUCCESS)
        self.assertEqual(orch.executor.run_manim.call_count, 2)
        # One execution failure increments retry_count to 1 → total_attempts = 2
        self.assertEqual(result.total_attempts, 2)

    def test_max_retries_exceeded(self) -> None:
        """All execution attempts fail → MAX_RETRIES_EXCEEDED."""
        orch = self._build_orch(max_retries=3)

        orch._llm = MagicMock()
        orch._llm.invoke.return_value = MagicMock(
            content=f"```python\n{CLEAN_CODE}\n```"
        )
        orch.executor.run_manim.return_value = {
            "status": "error",
            "traceback": "Fatal render error",
        }

        result = orch.run(_make_description())

        self.assertEqual(result.status, PipelineStatus.MAX_RETRIES_EXCEEDED)
        self.assertEqual(result.output_files, [])
        self.assertEqual(orch.executor.run_manim.call_count, 3)

    def test_final_state_attached_to_result(self) -> None:
        orch = self._build_orch()

        orch._llm = MagicMock()
        orch._llm.invoke.return_value = MagicMock(
            content=f"```python\n{CLEAN_CODE}\n```"
        )
        orch.executor.run_manim.return_value = {
            "status": "success",
            "output_path": "/tmp/scene.mp4",
        }

        result = orch.run(_make_description())

        self.assertIsNotNone(result.final_state)
        self.assertEqual(result.final_state["status"], "success")


# ---------------------------------------------------------------------------
# Tests: _build_feedback helper
# ---------------------------------------------------------------------------

class TestBuildFeedback(unittest.TestCase):

    def setUp(self) -> None:
        self.orch, _ = _make_orchestrator()

    def _state(self, error_message: str) -> GraphState:
        return {
            "user_prompt": "test",
            "current_code": "",
            "error_message": error_message,
            "retry_count": 0,
            "output_path": "",
            "status": "",
        }

    def test_audit_error_mentions_dangerous_constructs(self) -> None:
        fb = self.orch._build_feedback(
            self._state("[AUDIT] Blocked import 'os' at line 1")
        )
        self.assertIn("audit", fb.lower())
        self.assertIn("os", fb)

    def test_execute_error_includes_traceback(self) -> None:
        tb = "Traceback (most recent call last):\n  File scene.py\nValueError"
        fb = self.orch._build_feedback(self._state(f"[EXECUTE] {tb}"))
        self.assertIn("ValueError", fb)

    def test_long_traceback_is_truncated(self) -> None:
        long_tb = "x" * 3000
        fb = self.orch._build_feedback(self._state(f"[EXECUTE] {long_tb}"))
        self.assertLess(len(fb), 2500)
        self.assertIn("truncated", fb)

    def test_empty_error_returns_fallback_message(self) -> None:
        fb = self.orch._build_feedback(self._state(""))
        self.assertIn("unknown error", fb.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
