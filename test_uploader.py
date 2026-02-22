"""
test_uploader.py

Unit tests for DriveUploader.  The Google API client and service account
credentials are fully mocked — no network calls or real credentials required.

Run with:
    python -m pytest test_uploader.py -v
or:
    python -m unittest test_uploader -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, call, patch

from googleapiclient.errors import HttpError

from uploader import DriveUploader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_uploader() -> DriveUploader:
    """Return a DriveUploader with a fully mocked service, skipping I/O."""
    with patch("uploader.service_account.Credentials.from_service_account_file"), \
         patch("uploader.build") as mock_build:
        mock_build.return_value = MagicMock()
        uploader = DriveUploader(
            credentials_path="credentials.json",
            folder_id="FOLDER_ID_123",
        )
    return uploader


def _http_error(status: int = 403, reason: str = "Forbidden") -> HttpError:
    """Construct a minimal googleapiclient HttpError for testing."""
    resp = MagicMock()
    resp.status = status
    resp.reason = reason
    return HttpError(resp=resp, content=b"")


# ---------------------------------------------------------------------------
# Tests: _build_service
# ---------------------------------------------------------------------------

class TestBuildService(unittest.TestCase):

    def test_uses_service_account_credentials(self) -> None:
        with patch(
            "uploader.service_account.Credentials.from_service_account_file"
        ) as mock_creds, patch("uploader.build") as mock_build:
            mock_build.return_value = MagicMock()
            DriveUploader("creds.json", "FOLDER")

        mock_creds.assert_called_once_with(
            "creds.json",
            scopes=["https://www.googleapis.com/auth/drive"],
        )

    def test_builds_drive_v3_service(self) -> None:
        with patch(
            "uploader.service_account.Credentials.from_service_account_file"
        ), patch("uploader.build") as mock_build:
            mock_build.return_value = MagicMock()
            DriveUploader("creds.json", "FOLDER")

        mock_build.assert_called_once()
        call_kwargs = mock_build.call_args
        self.assertEqual(call_kwargs[0][0], "drive")
        self.assertEqual(call_kwargs[0][1], "v3")

    def test_cache_discovery_disabled(self) -> None:
        with patch(
            "uploader.service_account.Credentials.from_service_account_file"
        ), patch("uploader.build") as mock_build:
            mock_build.return_value = MagicMock()
            DriveUploader("creds.json", "FOLDER")

        _, kwargs = mock_build.call_args
        self.assertFalse(kwargs.get("cache_discovery", True))


# ---------------------------------------------------------------------------
# Tests: _create_file
# ---------------------------------------------------------------------------

class TestCreateFile(unittest.TestCase):
    """MediaFileUpload opens the file on __init__, so it must always be mocked."""

    def setUp(self) -> None:
        self.uploader = _make_uploader()

    def test_calls_files_create_with_correct_metadata(self) -> None:
        mock_files = MagicMock()
        mock_files.create.return_value.execute.return_value = {"id": "FILE_ID"}
        self.uploader._service.files.return_value = mock_files

        with patch("uploader.MediaFileUpload"):
            file_id = self.uploader._create_file("/tmp/scene.mp4", "scene.mp4")

        self.assertEqual(file_id, "FILE_ID")
        mock_files.create.assert_called_once()
        _, kwargs = mock_files.create.call_args
        self.assertEqual(kwargs["body"]["name"], "scene.mp4")
        self.assertEqual(kwargs["body"]["parents"], ["FOLDER_ID_123"])
        self.assertEqual(kwargs["fields"], "id")

    def test_returns_file_id_string(self) -> None:
        mock_files = MagicMock()
        mock_files.create.return_value.execute.return_value = {"id": "XYZ789"}
        self.uploader._service.files.return_value = mock_files

        with patch("uploader.MediaFileUpload"):
            result = self.uploader._create_file("/tmp/video.mp4", "video.mp4")
        self.assertEqual(result, "XYZ789")


# ---------------------------------------------------------------------------
# Tests: _make_public
# ---------------------------------------------------------------------------

class TestMakePublic(unittest.TestCase):

    def setUp(self) -> None:
        self.uploader = _make_uploader()

    def test_creates_anyone_reader_permission(self) -> None:
        mock_permissions = MagicMock()
        self.uploader._service.permissions.return_value = mock_permissions

        self.uploader._make_public("FILE_ID_ABC")

        mock_permissions.create.assert_called_once_with(
            fileId="FILE_ID_ABC",
            body={"type": "anyone", "role": "reader"},
        )
        mock_permissions.create.return_value.execute.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: upload_video (public interface)
# ---------------------------------------------------------------------------

class TestUploadVideo(unittest.TestCase):

    def setUp(self) -> None:
        self.uploader = _make_uploader()

    def _mock_drive(self, file_id: str = "FILE_123") -> None:
        """Wire up service mocks for a successful upload."""
        mock_files = MagicMock()
        mock_files.create.return_value.execute.return_value = {"id": file_id}
        self.uploader._service.files.return_value = mock_files

        mock_permissions = MagicMock()
        self.uploader._service.permissions.return_value = mock_permissions

    def test_success_returns_web_view_link(self) -> None:
        self._mock_drive("ABC123")
        with patch("uploader.MediaFileUpload"):
            result = self.uploader.upload_video("/tmp/scene.mp4", "scene.mp4")
        self.assertEqual(result, "https://drive.google.com/file/d/ABC123/view")

    def test_web_view_link_contains_file_id(self) -> None:
        self._mock_drive("UNIQUE_ID_XYZ")
        with patch("uploader.MediaFileUpload"):
            result = self.uploader.upload_video("/tmp/video.mp4", "video.mp4")
        self.assertIn("UNIQUE_ID_XYZ", result)

    def test_http_error_returns_empty_string(self) -> None:
        mock_files = MagicMock()
        mock_files.create.return_value.execute.side_effect = _http_error(403)
        self.uploader._service.files.return_value = mock_files

        with patch("uploader.MediaFileUpload"):
            result = self.uploader.upload_video("/tmp/scene.mp4", "scene.mp4")
        self.assertEqual(result, "")

    def test_file_not_found_returns_empty_string(self) -> None:
        # MediaFileUpload itself raises FileNotFoundError when the file is absent
        with patch("uploader.MediaFileUpload", side_effect=FileNotFoundError("missing")):
            result = self.uploader.upload_video("/tmp/missing.mp4", "missing.mp4")
        self.assertEqual(result, "")

    def test_unexpected_exception_returns_empty_string(self) -> None:
        mock_files = MagicMock()
        mock_files.create.return_value.execute.side_effect = RuntimeError("boom")
        self.uploader._service.files.return_value = mock_files

        with patch("uploader.MediaFileUpload"):
            result = self.uploader.upload_video("/tmp/scene.mp4", "scene.mp4")
        self.assertEqual(result, "")

    def test_permission_error_returns_empty_string(self) -> None:
        """Upload succeeds but setting permission raises HttpError."""
        mock_files = MagicMock()
        mock_files.create.return_value.execute.return_value = {"id": "FILE_ID"}
        self.uploader._service.files.return_value = mock_files

        mock_permissions = MagicMock()
        mock_permissions.create.return_value.execute.side_effect = _http_error(403)
        self.uploader._service.permissions.return_value = mock_permissions

        with patch("uploader.MediaFileUpload"):
            result = self.uploader.upload_video("/tmp/scene.mp4", "scene.mp4")
        self.assertEqual(result, "")

    def test_make_public_called_after_create(self) -> None:
        """Verify _make_public is called with the id returned by _create_file."""
        self._mock_drive("FILE_ABC")
        with patch("uploader.MediaFileUpload"), \
             patch.object(self.uploader, "_make_public") as mock_public:
            self.uploader.upload_video("/tmp/scene.mp4", "scene.mp4")
        mock_public.assert_called_once_with("FILE_ABC")


# ---------------------------------------------------------------------------
# Tests: orchestrator upload_node integration
# ---------------------------------------------------------------------------

class TestOrchestratorUploadNode(unittest.TestCase):
    """Verify the upload_node wiring inside WorkflowOrchestrator."""

    def _base_state(self, output_path: str = "/tmp/scene.mp4") -> dict:
        return {
            "user_prompt": "test",
            "current_code": "code",
            "error_message": "",
            "retry_count": 0,
            "output_path": output_path,
            "status": "success",
            "drive_link": "",
        }

    def _build_orch(self, drive_uploader=None):
        from orchestrator import WorkflowOrchestrator
        from executor import SandboxExecutor
        from generator import ManimCodeGenerator
        from pathlib import Path

        with patch("orchestrator.ChatGoogleGenerativeAI"):
            orch = WorkflowOrchestrator(
                generator=MagicMock(spec=ManimCodeGenerator),
                auditors=[],
                executor=MagicMock(spec=SandboxExecutor),
                working_dir=Path("/tmp"),
                drive_uploader=drive_uploader,
            )
        return orch

    def test_upload_node_sets_drive_link_on_success(self) -> None:
        mock_uploader = MagicMock(spec=DriveUploader)
        mock_uploader.upload_video.return_value = (
            "https://drive.google.com/file/d/XYZ/view"
        )
        orch = self._build_orch(drive_uploader=mock_uploader)

        result = orch.upload_node(self._base_state("/tmp/scene.mp4"))

        self.assertEqual(
            result["drive_link"],
            "https://drive.google.com/file/d/XYZ/view",
        )
        mock_uploader.upload_video.assert_called_once_with(
            "/tmp/scene.mp4", "scene.mp4"
        )

    def test_upload_node_noop_when_no_uploader(self) -> None:
        orch = self._build_orch(drive_uploader=None)
        result = orch.upload_node(self._base_state())
        self.assertEqual(result, {})

    def test_upload_node_returns_empty_drive_link_on_failure(self) -> None:
        mock_uploader = MagicMock(spec=DriveUploader)
        mock_uploader.upload_video.return_value = ""  # uploader failed
        orch = self._build_orch(drive_uploader=mock_uploader)

        result = orch.upload_node(self._base_state())
        self.assertEqual(result["drive_link"], "")

    def test_route_after_execute_goes_to_upload_node_on_success(self) -> None:
        orch = self._build_orch()
        state = self._base_state()
        self.assertEqual(orch._route_after_execute(state), "upload_node")

    def test_full_graph_with_uploader_populates_drive_link(self) -> None:
        """End-to-end: graph finishes with drive_link in PipelineResult."""
        from auditor import SecurityAuditor
        from generator import SceneDescription, SceneComplexity

        CLEAN_CODE = (
            "from manim import Scene, Circle\n"
            "class S(Scene):\n"
            "    def construct(self): pass\n"
        )

        mock_uploader = MagicMock(spec=DriveUploader)
        mock_uploader.upload_video.return_value = (
            "https://drive.google.com/file/d/FINAL/view"
        )
        executor = MagicMock(spec=__import__("executor").SandboxExecutor)
        executor.run_manim.return_value = {
            "status": "success",
            "output_path": "/tmp/scene.mp4",
        }

        with patch("orchestrator.ChatGoogleGenerativeAI"):
            from orchestrator import WorkflowOrchestrator
            from pathlib import Path

            orch = WorkflowOrchestrator(
                generator=MagicMock(),
                auditors=[SecurityAuditor()],
                executor=executor,
                working_dir=Path("/tmp"),
                drive_uploader=mock_uploader,
            )

        orch._llm = MagicMock()
        orch._llm.invoke.return_value = MagicMock(
            content=f"```python\n{CLEAN_CODE}\n```"
        )

        result = orch.run(
            SceneDescription(
                title="T", narrative="Draw a circle", complexity=SceneComplexity.SIMPLE
            )
        )

        from orchestrator import PipelineStatus
        self.assertEqual(result.status, PipelineStatus.SUCCESS)
        self.assertEqual(result.drive_link, "https://drive.google.com/file/d/FINAL/view")


if __name__ == "__main__":
    unittest.main(verbosity=2)
