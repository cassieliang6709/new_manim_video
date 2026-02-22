"""
executor.py

Provides executors for running generated Manim scripts:
- SandboxExecutor: Docker container (manimcommunity/manim).
- LocalExecutor: local `manim` CLI via subprocess (no Docker).

Dependencies:
    SandboxExecutor: pip install docker
    LocalExecutor: pip install manim (local env)
"""

from __future__ import annotations

import ast as _ast
import logging
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import docker
import docker.errors
from docker.models.containers import Container

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers (used by SandboxExecutor and LocalExecutor)
# ---------------------------------------------------------------------------

def _parse_scene_class_name(source_code: str) -> str | None:
    """First Scene subclass name in *source_code*, or None."""
    try:
        tree = _ast.parse(source_code)
    except SyntaxError:
        return None
    for node in _ast.walk(tree):
        if not isinstance(node, _ast.ClassDef):
            continue
        for base in node.bases:
            base_name = ""
            if isinstance(base, _ast.Name):
                base_name = base.id
            elif isinstance(base, _ast.Attribute):
                base_name = base.attr
            if base_name.endswith("Scene"):
                return node.name
    return None


def _collect_output_files(working_dir: Path) -> list[Path]:
    """All .mp4 under *working_dir*, newest first."""
    mp4_files = list(working_dir.rglob("*.mp4"))
    mp4_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return mp4_files


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ExecutionResult:
    """Represents the outcome of a sandboxed script execution.

    Attributes:
        success: True if the script exited with code 0.
        exit_code: The raw process exit code returned by Docker.
        stdout: Captured standard output from the container.
        stderr: Captured standard error from the container.
        output_files: Paths on the *host* where output artefacts were written
            (e.g. the rendered ``.mp4`` file).
    """

    success: bool
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    output_files: list[Path] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseExecutor(ABC):
    """Abstract base for code executors.

    Concrete implementations may use Docker, subprocess sandboxes, remote
    kernels, etc.
    """

    @abstractmethod
    def execute(self, source_code: str, working_dir: Path) -> ExecutionResult:
        """Execute *source_code* and return a structured result.

        Args:
            source_code: Python source to run inside the sandbox.
            working_dir: Host-side directory used for mounting artefacts.

        Returns:
            An :class:`ExecutionResult` describing the outcome.
        """
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether the execution backend is reachable.

        Returns:
            ``True`` if the backend is ready to accept jobs.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Docker-backed implementation
# ---------------------------------------------------------------------------

class SandboxExecutor(BaseExecutor):
    """Executes Manim scripts inside a Docker container.

    The executor writes the supplied source code to a temporary ``.py`` file
    inside *output_dir*, bind-mounts that directory into a
    ``manimcommunity/manim`` container, and runs the ``manim`` CLI with
    network access disabled and a 1 GB memory cap.

    Args:
        image: Docker image name (and optional tag) to use for execution.
        timeout: Maximum seconds to wait for the container before aborting.
        memory_limit: Docker memory constraint string (e.g. ``"1g"``).
        cpu_quota: Docker ``cpu_quota`` value in microseconds
            (e.g. ``50_000`` = 0.5 CPUs with the default 100 ms period).
    """

    DEFAULT_IMAGE: str = "manimcommunity/manim:latest"
    DEFAULT_TIMEOUT: int = 120          # seconds
    DEFAULT_MEMORY_LIMIT: str = "1g"
    DEFAULT_CPU_QUOTA: int = 50_000     # 0.5 CPUs

    # Fixed paths used *inside* every container
    _CONTAINER_WORKSPACE: str = "/manim/workspace"

    def __init__(
        self,
        image: str = DEFAULT_IMAGE,
        timeout: int = DEFAULT_TIMEOUT,
        memory_limit: str = DEFAULT_MEMORY_LIMIT,
        cpu_quota: int = DEFAULT_CPU_QUOTA,
    ) -> None:
        self.image = image
        self.timeout = timeout
        self.memory_limit = memory_limit
        self.cpu_quota = cpu_quota

    # ------------------------------------------------------------------
    # Primary public method (as specified)
    # ------------------------------------------------------------------

    def run_manim(self, code_string: str, output_dir: str) -> dict[str, Any]:
        """Execute a Manim script in a Docker sandbox.

        Steps:
        1. Create *output_dir* if necessary; write *code_string* to a
           temporary ``.py`` file inside it (so the file is reachable via
           the bind-mount without a second volume).
        2. Connect to the local Docker daemon via :func:`docker.from_env`.
        3. Run a ``manimcommunity/manim`` container with:
           - *output_dir* bind-mounted at :attr:`_CONTAINER_WORKSPACE` (rw)
           - ``network_disabled=True``
           - ``mem_limit="1g"``
        4. Wait up to :attr:`timeout` seconds for the container to finish and
           capture its combined stdout/stderr logs.
        5. Return ``{'status': 'success', 'output_path': '<path>'}`` when the
           container exits cleanly and an ``.mp4`` artefact is found, or
           ``{'status': 'error', 'traceback': '<logs>'}`` otherwise.

        Args:
            code_string: Raw Python source code for a Manim scene.
            output_dir: Host-side directory for the temp script and all
                rendered output. Created automatically if absent.

        Returns:
            On success::

                {'status': 'success', 'output_path': '/abs/path/to/scene.mp4'}

            On any failure::

                {'status': 'error', 'traceback': '<combined container logs or exception message>'}
        """
        output_path = Path(output_dir).resolve()
        output_path.mkdir(parents=True, exist_ok=True)

        # ── Step 1: Write the script to a temp file inside output_dir ──────
        tmp_file: tempfile.NamedTemporaryFile | None = None
        script_host_path: Path | None = None
        container: Container | None = None

        try:
            # delete=False because we control cleanup in finally
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                dir=output_path,
                delete=False,
                encoding="utf-8",
            ) as tmp_file:
                tmp_file.write(code_string)
                script_host_path = Path(tmp_file.name)

            _logger.debug("Temp script written to %s", script_host_path)

            # ── Step 2: Connect to Docker daemon ───────────────────────────
            try:
                client = docker.from_env()
                client.ping()  # Fail fast if the daemon is unreachable
            except docker.errors.DockerException as exc:
                return {
                    "status": "error",
                    "traceback": f"Docker daemon unreachable: {exc}",
                }

            # ── Step 3: Build the Manim command ────────────────────────────
            scene_class = _parse_scene_class_name(code_string)
            container_script_path = (
                f"{self._CONTAINER_WORKSPACE}/{script_host_path.name}"
            )
            command = self._build_docker_command(container_script_path, scene_class)

            _logger.info(
                "Running container %s — command: %s", self.image, " ".join(command)
            )

            # ── Step 4: Run the container (detached so we can enforce timeout)
            try:
                container = client.containers.run(
                    image=self.image,
                    command=command,
                    volumes={
                        str(output_path): {
                            "bind": self._CONTAINER_WORKSPACE,
                            "mode": "rw",
                        }
                    },
                    network_disabled=True,
                    mem_limit="1g",
                    cpu_quota=self.cpu_quota,
                    detach=True,
                    remove=False,   # Manual removal after log capture
                )
            except docker.errors.ImageNotFound as exc:
                return {
                    "status": "error",
                    "traceback": (
                        f"Docker image '{self.image}' not found. "
                        f"Pull it first with: docker pull {self.image}\n{exc}"
                    ),
                }
            except docker.errors.APIError as exc:
                return {
                    "status": "error",
                    "traceback": f"Docker API error while starting container: {exc}",
                }

            # ── Wait for completion (raises ReadTimeout on expiry) ──────────
            try:
                exit_result: dict[str, Any] = container.wait(timeout=self.timeout)
            except Exception as exc:  # requests.exceptions.ReadTimeout or similar
                _logger.warning("Container timed out after %ds — killing.", self.timeout)
                try:
                    container.kill()
                except docker.errors.APIError:
                    pass
                return {
                    "status": "error",
                    "traceback": (
                        f"Container exceeded timeout of {self.timeout}s "
                        f"and was killed.\n{exc}"
                    ),
                }

            exit_code: int = exit_result.get("StatusCode", -1)
            logs: str = container.logs(
                stdout=True, stderr=True
            ).decode("utf-8", errors="replace")

            _logger.debug("Container exited %d. Logs:\n%s", exit_code, logs)

            # ── Step 5: Evaluate outcome ────────────────────────────────────
            if exit_code != 0:
                return {"status": "error", "traceback": logs}

            mp4_files = _collect_output_files(output_path)
            if not mp4_files:
                return {
                    "status": "error",
                    "traceback": (
                        "Container exited with code 0 but no .mp4 file was found "
                        f"under '{output_path}'.\nContainer logs:\n{logs}"
                    ),
                }

            result_path = str(mp4_files[0])
            _logger.info("Render complete: %s", result_path)
            return {"status": "success", "output_path": result_path}

        finally:
            # Always remove the temp script and the container
            if script_host_path is not None:
                try:
                    script_host_path.unlink(missing_ok=True)
                except OSError as exc:
                    _logger.warning("Could not remove temp script: %s", exc)

            if container is not None:
                try:
                    container.remove(force=True)
                except docker.errors.APIError as exc:
                    _logger.warning("Could not remove container: %s", exc)

    # ------------------------------------------------------------------
    # BaseExecutor interface
    # ------------------------------------------------------------------

    def execute(self, source_code: str, working_dir: Path) -> ExecutionResult:
        """Run *source_code* inside a Docker sandbox.

        Delegates to :meth:`run_manim` and translates its ``dict`` return value
        into an :class:`ExecutionResult` for callers that use the abstract
        interface.

        Args:
            source_code: Python source code for a Manim scene.
            working_dir: Host directory bind-mounted into the container.

        Returns:
            An :class:`ExecutionResult` with captured logs and output paths.
        """
        outcome = self.run_manim(source_code, str(working_dir))

        if outcome["status"] == "success":
            return ExecutionResult(
                success=True,
                exit_code=0,
                stdout=outcome.get("output_path", ""),
                output_files=[Path(outcome["output_path"])],
            )

        return ExecutionResult(
            success=False,
            exit_code=1,
            stderr=outcome.get("traceback", ""),
        )

    def is_available(self) -> bool:
        """Ping the Docker daemon to verify it is running.

        Returns:
            ``True`` if the daemon responds to a ping, ``False`` otherwise.
        """
        try:
            docker.from_env().ping()
            return True
        except docker.errors.DockerException:
            return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_docker_command(
        self,
        container_script_path: str,
        scene_class_name: str | None,
    ) -> list[str]:
        """Build the ``manim`` CLI command executed inside the container.

        The command renders at medium quality (``-qm``) and writes all output
        to :attr:`_CONTAINER_WORKSPACE`.  When a scene class can be identified
        it is passed explicitly; otherwise the ``-a`` (render-all) flag is
        used.

        Args:
            container_script_path: Absolute path to the script *inside* the
                container (e.g. ``"/manim/workspace/scene_abc123.py"``).
            scene_class_name: Name of the ``Scene`` subclass to render, or
                ``None`` to render all scenes found in the file.

        Returns:
            A list of strings passed to :func:`docker.client.containers.run`
            as the ``command`` argument.
        """
        cmd = [
            "manim",
            "-qm",                          # medium quality
            "--media_dir", self._CONTAINER_WORKSPACE,
            container_script_path,
        ]
        if scene_class_name:
            cmd.append(scene_class_name)
        else:
            cmd.append("-a")                # render all scenes in the file
        return cmd

    def _parse_scene_class_name(self, source_code: str) -> str | None:
        return _parse_scene_class_name(source_code)

    def _collect_output_files(self, working_dir: Path) -> list[Path]:
        return _collect_output_files(working_dir)


# ---------------------------------------------------------------------------
# Local execution (no Docker)
# ---------------------------------------------------------------------------

class LocalExecutor(BaseExecutor):
    """Runs Manim via local `manim` CLI. No Docker required.

    Requires: pip install manim (and system deps: ffmpeg, sox, etc.).
    Same run_manim(code_string, output_dir) -> dict contract as SandboxExecutor.
    """

    DEFAULT_TIMEOUT: int = 180  # 场景稍长时避免 120s 超时只出 partial

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout

    def run_manim(self, code_string: str, output_dir: str) -> dict[str, Any]:
        output_path = Path(output_dir).resolve()
        output_path.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                dir=output_path,
                delete=False,
                encoding="utf-8",
            ) as f:
                f.write(code_string)
                script_path = Path(f.name)
        except OSError as exc:
            return {"status": "error", "traceback": f"Failed to write script: {exc}"}

        try:
            scene_class = _parse_scene_class_name(code_string)
            cmd = [
                "manim",
                "-qm",
                "--media_dir", str(output_path),
                str(script_path),
                scene_class if scene_class else "-a",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(output_path),
            )
            combined = (result.stdout or "") + (result.stderr or "")
            if result.returncode != 0:
                return {"status": "error", "traceback": combined or f"Exit code {result.returncode}"}
            mp4_files = _collect_output_files(output_path)
            if not mp4_files:
                return {
                    "status": "error",
                    "traceback": f"No .mp4 under {output_path}\n{combined}",
                }
            return {"status": "success", "output_path": str(mp4_files[0])}
        except subprocess.TimeoutExpired as exc:
            return {"status": "error", "traceback": f"Timeout ({self.timeout}s): {exc}"}
        except FileNotFoundError:
            return {
                "status": "error",
                "traceback": "`manim` not found. Install with: pip install manim",
            }
        finally:
            script_path.unlink(missing_ok=True)

    def execute(self, source_code: str, working_dir: Path) -> ExecutionResult:
        outcome = self.run_manim(source_code, str(working_dir))
        if outcome["status"] == "success":
            return ExecutionResult(
                success=True,
                exit_code=0,
                output_files=[Path(outcome["output_path"])],
            )
        return ExecutionResult(
            success=False,
            exit_code=1,
            stderr=outcome.get("traceback", ""),
        )

    def is_available(self) -> bool:
        try:
            r = subprocess.run(
                ["manim", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return r.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

