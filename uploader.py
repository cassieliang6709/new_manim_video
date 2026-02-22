"""
uploader.py

Two ways to upload to Google Drive:
- DriveUploader: 服务账号（需共享盘或共享文件夹，个人 Gmail 会 403）
- DriveUploaderOAuth: 个人 Gmail 用「用户登录一次 + refresh token」，上传到你的「我的云端硬盘」

Dependencies:
    pip install google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

_logger = logging.getLogger(__name__)

_DRIVE_SCOPES: list[str] = ["https://www.googleapis.com/auth/drive"]


class DriveUploader:
    """Uploads files to Google Drive using a service account credential.

    Usage example::

        uploader = DriveUploader(
            credentials_path="credentials.json",
            folder_id="1ABCxyz...",
        )
        link = uploader.upload_video("/tmp/output/MyScene.mp4", "MyScene.mp4")
        print(link)   # https://drive.google.com/file/d/<id>/view

    Args:
        credentials_path: Path to the service account JSON key file
            (e.g. ``"credentials.json"``).
        folder_id: ID of the target Drive folder.  Visible at the end of the
            folder URL:
            ``https://drive.google.com/drive/folders/<FOLDER_ID>``
    """

    def __init__(self, credentials_path: str, folder_id: str) -> None:
        self.credentials_path: str = credentials_path
        self.folder_id: str = folder_id
        self._service: Resource = self._build_service()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def upload_video(self, file_path: str, file_name: str) -> str:
        """Upload *file_path* to the configured Drive folder.

        The upload sequence is:
        1. Create the file inside the target folder using a resumable upload.
        2. Apply a public ``anyoneWithLink`` → ``reader`` permission so the
           returned link can be shared without further configuration.
        3. Return the canonical ``webViewLink``.

        All exceptions are caught and logged; on failure an empty string is
        returned so the caller can decide how to handle the missing link.

        Args:
            file_path: Absolute host-side path to the ``.mp4`` file to upload.
            file_name: Display name for the file inside Google Drive.

        Returns:
            ``webViewLink`` string on success
            (``"https://drive.google.com/file/d/<id>/view"``), or an empty
            string if any step of the upload fails.
        """
        try:
            _logger.info(
                "Uploading '%s' → Drive folder '%s'", file_name, self.folder_id
            )
            file_id: str = self._create_file(file_path, file_name)
            self._make_public(file_id)
            web_view_link = f"https://drive.google.com/file/d/{file_id}/view"
            _logger.info("Upload complete: %s", web_view_link)
            return web_view_link

        except HttpError as exc:
            _logger.error(
                "Drive API error uploading '%s' (HTTP %s): %s",
                file_name,
                exc.resp.status,
                exc,
            )
            return ""

        except FileNotFoundError as exc:
            _logger.error("File not found for upload: %s", exc)
            return ""

        except Exception as exc:  # noqa: BLE001 — intentional broad catch
            _logger.error(
                "Unexpected error uploading '%s': %s: %s",
                file_name,
                type(exc).__name__,
                exc,
            )
            return ""

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_service(self) -> Resource:
        """Authenticate with the service account and return a Drive v3 resource.

        Raises:
            FileNotFoundError: If *credentials_path* does not point to a file.
            google.auth.exceptions.MalformedError: If the JSON key is invalid.
            googleapiclient.errors.HttpError: If the discovery document cannot
                be fetched.

        Returns:
            An authenticated ``googleapiclient`` Drive v3 service resource.
        """
        credentials = service_account.Credentials.from_service_account_file(
            self.credentials_path,
            scopes=_DRIVE_SCOPES,
        )
        service: Resource = build(
            "drive",
            "v3",
            credentials=credentials,
            # Suppress the "file_cache is unavailable" warning in serverless
            # environments that lack a writable filesystem cache.
            cache_discovery=False,
        )
        _logger.debug(
            "Drive service initialised for '%s'", self.credentials_path
        )
        return service

    def _create_file(self, file_path: str, file_name: str) -> str:
        """Upload file bytes to Drive and return the resulting file ID.

        Uses a resumable upload so large video files are handled reliably
        even over slow or interrupted connections.

        Args:
            file_path: Host-side path to the file to upload.
            file_name: Desired name inside Drive.

        Returns:
            The new Drive file ID (e.g. ``"1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs"``).

        Raises:
            googleapiclient.errors.HttpError: On any API-level upload failure.
        """
        file_metadata: dict[str, Any] = {
            "name": file_name,
            "parents": [self.folder_id],
        }
        media = MediaFileUpload(
            file_path,
            mimetype="video/mp4",
            resumable=True,
        )
        response: dict[str, Any] = (
            self._service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id",
                supportsAllDrives=True,
            )
            .execute()
        )
        file_id: str = response["id"]
        _logger.debug("File created in Drive with id=%s", file_id)
        return file_id

    def _make_public(self, file_id: str) -> None:
        """Grant 'anyone with the link can view' access to *file_id*.

        Creates a single permission of type ``anyone`` with role ``reader``
        so the ``webViewLink`` can be opened without a Google account.

        Args:
            file_id: Drive file ID returned by :meth:`_create_file`.

        Raises:
            googleapiclient.errors.HttpError: If the permission request fails
                (e.g. insufficient OAuth scope or quota exceeded).
        """
        self._service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
            supportsAllDrives=True,
        ).execute()
        _logger.debug("Public read permission applied to file_id=%s", file_id)


# ---------------------------------------------------------------------------
# OAuth 上传（个人 Gmail：用你的账号、你的空间，无需共享盘）
# ---------------------------------------------------------------------------

def _oauth_service_from_token(token_path: str) -> Resource:
    """从 token.json（含 refresh_token）构建 Drive 服务。"""
    path = Path(token_path)
    if not path.exists():
        raise FileNotFoundError(f"OAuth token 不存在: {token_path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    refresh_token = data.get("refresh_token")
    client_id = data.get("client_id")
    client_secret = data.get("client_secret")
    if not all([refresh_token, client_id, client_secret]):
        raise ValueError("token.json 需包含 refresh_token, client_id, client_secret")
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=_DRIVE_SCOPES,
    )
    creds.refresh(Request())
    return build("drive", "v3", credentials=creds, cache_discovery=False)


class DriveUploaderOAuth:
    """用 OAuth 登录后的 refresh token 上传到你的 Drive（个人 Gmail 可用）。"""

    def __init__(self, token_path: str, folder_id: str) -> None:
        self.folder_id = folder_id
        self._service: Resource = _oauth_service_from_token(token_path)

    def upload_video(self, file_path: str, file_name: str) -> str:
        try:
            _logger.info("Uploading '%s' → Drive folder '%s' (OAuth)", file_name, self.folder_id)
            file_id = self._create_file(file_path, file_name)
            self._make_public(file_id)
            link = f"https://drive.google.com/file/d/{file_id}/view"
            _logger.info("Upload complete: %s", link)
            return link
        except HttpError as exc:
            _logger.error("Drive API error (HTTP %s): %s", exc.resp.status, exc)
            return ""
        except Exception as exc:
            _logger.error("Upload error: %s", exc)
            return ""

    def _create_file(self, file_path: str, file_name: str) -> str:
        file_metadata: dict[str, Any] = {
            "name": file_name,
            "parents": [self.folder_id],
        }
        media = MediaFileUpload(file_path, mimetype="video/mp4", resumable=True)
        response: dict[str, Any] = (
            self._service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id",
                supportsAllDrives=True,
            )
            .execute()
        )
        return response["id"]

    def _make_public(self, file_id: str) -> None:
        self._service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
            supportsAllDrives=True,
        ).execute()
