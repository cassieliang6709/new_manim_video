"""
test_executor.py

Unit tests for SandboxExecutor.  Docker-dependent behaviour (run_manim, execute,
is_available) is covered with unittest.mock so the tests run without a live
Docker daemon.  Pure-logic helpers (_parse_scene_class_name, _build_docker_command,
_collect_output_files) are exercised against real inputs.

Run with:
    python -m pytest test_executor.py -v
or:
    python -m unittest test_executor -v
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from executor import ExecutionResult, SandboxExecutor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_executor(**kwargs) -> SandboxExecutor:
    """Return a SandboxExecutor with sensible test defaults."""
    return SandboxExecutor(
        image="manimcommunity/manim:latest",
        timeout=30,
        memory_limit="1g",
        cpu_quota=50_000,
        **kwargs,
    )


SIMPLE_SCENE = """\
from manim import Scene, Circle

class BallScene(Scene):
    def construct(self):
        self.play(Circle().animate.scale(2))
        self.wait()
"""

MULTI_SCENE = """\
from manim import Scene, Square, Triangle

class SceneA(Scene):
    def construct(self):
        pass

class SceneB(Scene):
    def construct(self):
        pass
"""

THREE_D_SCENE = """\
from manim import ThreeDScene, Sphere

class MySphere(ThreeDScene):
    def construct(self):
        self.add(Sphere())
"""

NO_SCENE = """\
x = 1 + 1
print(x)
"""

SYNTAX_ERROR_CODE = "def broken(:"


# ---------------------------------------------------------------------------
# _parse_scene_class_name  (pure logic, no Docker)
# ---------------------------------------------------------------------------

class TestParseSceneClassName(unittest.TestCase):

    def setUp(self) -> None:
        self.ex = _make_executor()

    def test_finds_simple_scene_subclass(self) -> None:
        result = self.ex._parse_scene_class_name(SIMPLE_SCENE)
        self.assertEqual(result, "BallScene")

    def test_finds_first_of_multiple_scenes(self) -> None:
        """Should return the first Scene subclass encountered."""
        result = self.ex._parse_scene_class_name(MULTI_SCENE)
        self.assertEqual(result, "SceneA")

    def test_finds_threedscene_subclass(self) -> None:
        """Subclasses of ThreeDScene (ends with 'Scene') should be found."""
        result = self.ex._parse_scene_class_name(THREE_D_SCENE)
        self.assertEqual(result, "MySphere")

    def test_returns_none_for_no_scene(self) -> None:
        result = self.ex._parse_scene_class_name(NO_SCENE)
        self.assertIsNone(result)

    def test_returns_none_for_syntax_error(self) -> None:
        result = self.ex._parse_scene_class_name(SYNTAX_ERROR_CODE)
        self.assertIsNone(result)

    def test_returns_none_for_empty_string(self) -> None:
        result = self.ex._parse_scene_class_name("")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# _build_docker_command  (pure logic, no Docker)
# ---------------------------------------------------------------------------

class TestBuildDockerCommand(unittest.TestCase):

    def setUp(self) -> None:
        self.ex = _make_executor()
        self.script = "/manim/workspace/scene_abc.py"

    def test_command_starts_with_manim(self) -> None:
        cmd = self.ex._build_docker_command(self.script, "MyScene")
        self.assertEqual(cmd[0], "manim")

    def test_medium_quality_flag_present(self) -> None:
        cmd = self.ex._build_docker_command(self.script, "MyScene")
        self.assertIn("-qm", cmd)

    def test_media_dir_flag_present(self) -> None:
        cmd = self.ex._build_docker_command(self.script, "MyScene")
        idx = cmd.index("--media_dir")
        self.assertEqual(cmd[idx + 1], SandboxExecutor._CONTAINER_WORKSPACE)

    def test_script_path_in_command(self) -> None:
        cmd = self.ex._build_docker_command(self.script, "MyScene")
        self.assertIn(self.script, cmd)

    def test_scene_class_appended_when_provided(self) -> None:
        cmd = self.ex._build_docker_command(self.script, "BallScene")
        self.assertIn("BallScene", cmd)
        self.assertNotIn("-a", cmd)

    def test_all_flag_used_when_no_scene_class(self) -> None:
        cmd = self.ex._build_docker_command(self.script, None)
        self.assertIn("-a", cmd)
        # No extra positional scene name beyond the script itself
        self.assertEqual(cmd[-1], "-a")


# ---------------------------------------------------------------------------
# _collect_output_files  (filesystem logic, no Docker)
# ---------------------------------------------------------------------------

class TestCollectOutputFiles(unittest.TestCase):

    def setUp(self) -> None:
        self.ex = _make_executor()

    def test_finds_mp4_files_recursively(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            nested = tmp_path / "videos" / "720p30"
            nested.mkdir(parents=True)
            (nested / "scene.mp4").touch()
            (nested / "scene2.mp4").touch()

            found = self.ex._collect_output_files(tmp_path)
            self.assertEqual(len(found), 2)
            self.assertTrue(all(p.suffix == ".mp4" for p in found))

    def test_ignores_non_mp4_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "scene.py").touch()
            (tmp_path / "debug.log").touch()

            found = self.ex._collect_output_files(tmp_path)
            self.assertEqual(found, [])

    def test_returns_empty_list_when_no_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            found = self.ex._collect_output_files(Path(tmp))
            self.assertEqual(found, [])

    def test_sorted_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            old = tmp_path / "old.mp4"
            new = tmp_path / "new.mp4"
            old.touch()
            new.touch()
            # Force different mtimes
            os.utime(old, (0, 0))

            found = self.ex._collect_output_files(tmp_path)
            self.assertEqual(found[0].name, "new.mp4")
            self.assertEqual(found[1].name, "old.mp4")


# ---------------------------------------------------------------------------
# run_manim  (mocked Docker)
# ---------------------------------------------------------------------------

class TestRunManimMocked(unittest.TestCase):
    """Test run_manim() with the Docker SDK fully mocked."""

    def setUp(self) -> None:
        self.ex = _make_executor()

    # ── Helper: build a mock container ─────────────────────────────────────

    @staticmethod
    def _mock_container(exit_code: int = 0, log_output: bytes = b"") -> MagicMock:
        container = MagicMock()
        container.wait.return_value = {"StatusCode": exit_code}
        container.logs.return_value = log_output
        return container

    # ── Success path ────────────────────────────────────────────────────────

    def test_success_returns_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Pre-create a fake .mp4 so _collect_output_files finds it
            mp4 = Path(tmp) / "videos" / "scene.mp4"
            mp4.parent.mkdir()
            mp4.touch()

            container = self._mock_container(exit_code=0, log_output=b"Rendered OK")
            mock_client = MagicMock()
            mock_client.containers.run.return_value = container

            with patch("executor.docker.from_env", return_value=mock_client):
                result = self.ex.run_manim(SIMPLE_SCENE, tmp)

            self.assertEqual(result["status"], "success")
            self.assertIn(".mp4", result["output_path"])

    # ── Non-zero exit code ───────────────────────────────────────────────────

    def test_nonzero_exit_returns_error_with_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            error_log = b"Error: scene class not found\nTraceback..."
            container = self._mock_container(exit_code=1, log_output=error_log)
            mock_client = MagicMock()
            mock_client.containers.run.return_value = container

            with patch("executor.docker.from_env", return_value=mock_client):
                result = self.ex.run_manim(SIMPLE_SCENE, tmp)

            self.assertEqual(result["status"], "error")
            self.assertIn("scene class not found", result["traceback"])

    # ── No MP4 produced despite exit 0 ──────────────────────────────────────

    def test_no_mp4_found_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            container = self._mock_container(exit_code=0, log_output=b"Done")
            mock_client = MagicMock()
            mock_client.containers.run.return_value = container

            with patch("executor.docker.from_env", return_value=mock_client):
                result = self.ex.run_manim(SIMPLE_SCENE, tmp)

            self.assertEqual(result["status"], "error")
            self.assertIn("no .mp4 file was found", result["traceback"])

    # ── Docker daemon unreachable ────────────────────────────────────────────

    def test_docker_daemon_unreachable(self) -> None:
        import docker.errors as _de

        with tempfile.TemporaryDirectory() as tmp:
            mock_client = MagicMock()
            mock_client.ping.side_effect = _de.DockerException("Connection refused")

            with patch("executor.docker.from_env", return_value=mock_client):
                result = self.ex.run_manim(SIMPLE_SCENE, tmp)

            self.assertEqual(result["status"], "error")
            self.assertIn("Docker daemon unreachable", result["traceback"])

    # ── Image not found ──────────────────────────────────────────────────────

    def test_image_not_found_error(self) -> None:
        import docker.errors as _de

        with tempfile.TemporaryDirectory() as tmp:
            mock_client = MagicMock()
            mock_client.containers.run.side_effect = _de.ImageNotFound("404")

            with patch("executor.docker.from_env", return_value=mock_client):
                result = self.ex.run_manim(SIMPLE_SCENE, tmp)

            self.assertEqual(result["status"], "error")
            self.assertIn("not found", result["traceback"])
            self.assertIn("docker pull", result["traceback"])

    # ── Container timeout ─────────────────────────────────────────────────────

    def test_container_timeout_kills_and_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            container = MagicMock()
            container.wait.side_effect = TimeoutError("timed out")
            mock_client = MagicMock()
            mock_client.containers.run.return_value = container

            with patch("executor.docker.from_env", return_value=mock_client):
                result = self.ex.run_manim(SIMPLE_SCENE, tmp)

            self.assertEqual(result["status"], "error")
            self.assertIn("timeout", result["traceback"].lower())
            container.kill.assert_called_once()

    # ── Output dir is created automatically ─────────────────────────────────

    def test_output_dir_created_if_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            new_dir = os.path.join(tmp, "nested", "output")
            mp4 = Path(new_dir) / "scene.mp4"

            container = self._mock_container(exit_code=0)
            mock_client = MagicMock()
            mock_client.containers.run.return_value = container

            # Pre-create the mp4 inside what will become the output dir
            # by wrapping _collect_output_files to inject a fake result
            with patch("executor.docker.from_env", return_value=mock_client), \
                 patch.object(self.ex, "_collect_output_files", return_value=[mp4]):
                result = self.ex.run_manim(SIMPLE_SCENE, new_dir)

            self.assertTrue(Path(new_dir).exists())

    # ── Temp script is cleaned up after run ──────────────────────────────────

    def test_temp_script_removed_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mp4 = Path(tmp) / "scene.mp4"
            mp4.touch()

            container = self._mock_container(exit_code=0)
            mock_client = MagicMock()
            mock_client.containers.run.return_value = container

            with patch("executor.docker.from_env", return_value=mock_client):
                self.ex.run_manim(SIMPLE_SCENE, tmp)

            remaining_py = list(Path(tmp).glob("*.py"))
            self.assertEqual(remaining_py, [], "Temp .py file should be deleted")

    def test_temp_script_removed_after_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            container = self._mock_container(exit_code=1, log_output=b"FAIL")
            mock_client = MagicMock()
            mock_client.containers.run.return_value = container

            with patch("executor.docker.from_env", return_value=mock_client):
                self.ex.run_manim(SIMPLE_SCENE, tmp)

            remaining_py = list(Path(tmp).glob("*.py"))
            self.assertEqual(remaining_py, [], "Temp .py file should be deleted even on failure")


# ---------------------------------------------------------------------------
# execute()  (BaseExecutor interface — mocked)
# ---------------------------------------------------------------------------

class TestExecuteInterface(unittest.TestCase):

    def setUp(self) -> None:
        self.ex = _make_executor()

    def test_execute_returns_execution_result_on_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_mp4 = str(Path(tmp) / "scene.mp4")
            with patch.object(
                self.ex,
                "run_manim",
                return_value={"status": "success", "output_path": fake_mp4},
            ):
                result = self.ex.execute(SIMPLE_SCENE, Path(tmp))

        self.assertIsInstance(result, ExecutionResult)
        self.assertTrue(result.success)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.output_files[0], Path(fake_mp4))

    def test_execute_returns_execution_result_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(
                self.ex,
                "run_manim",
                return_value={"status": "error", "traceback": "boom"},
            ):
                result = self.ex.execute(SIMPLE_SCENE, Path(tmp))

        self.assertIsInstance(result, ExecutionResult)
        self.assertFalse(result.success)
        self.assertEqual(result.exit_code, 1)
        self.assertIn("boom", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
