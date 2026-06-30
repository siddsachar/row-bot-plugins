"""Small Bot Framework Connector REST client for Microsoft Teams."""

from __future__ import annotations

import json
import mimetypes
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable


class TeamsConnectorError(Exception):
    """Connector failure with sanitized details suitable for users/tests."""


class BotConnectorClient:
    def __init__(
        self,
        token_provider: Callable[[], str],
        *,
        urlopen: Callable[..., Any] = urllib.request.urlopen,
        timeout: int = 10,
    ) -> None:
        self._token_provider = token_provider
        self._urlopen = urlopen
        self._timeout = timeout

    def send_activity(self, conversation_ref: dict[str, Any], activity: dict[str, Any]) -> str:
        url = self._conversation_url(conversation_ref) + "/activities"
        data = self._request_json("POST", url, activity, bearer_token=self._token_provider())
        return str(data.get("id") or data.get("activityId") or "")

    def update_activity(
        self,
        conversation_ref: dict[str, Any],
        activity_id: str,
        activity: dict[str, Any],
    ) -> str:
        url = self._conversation_url(conversation_ref) + "/activities/" + _quote(activity_id)
        data = self._request_json("PUT", url, activity, bearer_token=self._token_provider())
        return str(data.get("id") or data.get("activityId") or activity_id)

    def delete_activity(self, conversation_ref: dict[str, Any], activity_id: str) -> None:
        url = self._conversation_url(conversation_ref) + "/activities/" + _quote(activity_id)
        self._request_json("DELETE", url, None, bearer_token=self._token_provider())

    def send_typing(self, conversation_ref: dict[str, Any]) -> None:
        self.send_activity(conversation_ref, {"type": "typing"})

    def download_attachment(
        self,
        download_url: str,
        *,
        bearer_token: str = "",
        max_bytes: int = 10 * 1024 * 1024,
    ) -> bytes:
        headers = {"User-Agent": "Row-Bot-Teams-Channel/0.1"}
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"
        req = urllib.request.Request(download_url, headers=headers)
        try:
            with self._urlopen(req, timeout=self._timeout) as resp:
                data = resp.read(max_bytes + 1)
        except urllib.error.HTTPError as exc:
            raise TeamsConnectorError(f"Attachment download failed with HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise TeamsConnectorError(f"Attachment download failed: {exc.reason}") from exc
        if len(data) > max_bytes:
            raise TeamsConnectorError("Attachment exceeds configured size limit")
        return data

    def send_file_consent(
        self,
        conversation_ref: dict[str, Any],
        file_path: str,
        caption: str | None = None,
        *,
        context_id: str = "",
    ) -> tuple[str, str]:
        path = Path(file_path)
        if not path.is_file():
            raise TeamsConnectorError("File does not exist or is not readable")
        context_id = context_id or uuid.uuid4().hex
        description = caption or path.name
        activity = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.teams.card.file.consent",
                    "name": path.name,
                    "content": {
                        "description": description,
                        "sizeInBytes": path.stat().st_size,
                        "acceptContext": {"row_bot_action": "file_upload", "file_id": context_id},
                        "declineContext": {"row_bot_action": "file_upload", "file_id": context_id},
                    },
                }
            ],
        }
        return self.send_activity(conversation_ref, activity), context_id

    def upload_file_to_consent_url(self, upload_url: str, file_path: str) -> None:
        path = Path(file_path)
        if not path.is_file():
            raise TeamsConnectorError("File does not exist or is not readable")
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        headers = {
            "Content-Type": content_type,
            "Content-Length": str(path.stat().st_size),
            "User-Agent": "Row-Bot-Teams-Channel/0.1",
        }
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise TeamsConnectorError("File could not be read for Teams upload") from exc
        req = urllib.request.Request(upload_url, data=data, method="PUT", headers=headers)
        try:
            with self._urlopen(req, timeout=self._timeout) as resp:
                resp.read()
        except urllib.error.HTTPError as exc:
            raise TeamsConnectorError(f"File upload failed with HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise TeamsConnectorError(f"File upload failed: {exc.reason}") from exc

    def send_file_card(self, conversation_ref: dict[str, Any], upload_info: dict[str, Any]) -> str:
        activity = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.teams.card.file.info",
                    "contentUrl": upload_info.get("contentUrl") or upload_info.get("downloadUrl") or "",
                    "name": upload_info.get("name") or upload_info.get("fileName") or "file",
                    "content": upload_info,
                }
            ],
        }
        return self.send_activity(conversation_ref, activity)

    def _request_json(
        self,
        method: str,
        url: str,
        payload: dict[str, Any] | None,
        *,
        bearer_token: str,
    ) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "User-Agent": "Row-Bot-Teams-Channel/0.1",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with self._urlopen(req, timeout=self._timeout) as resp:
                body = resp.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:200]
            raise TeamsConnectorError(f"Bot Connector HTTP {exc.code}: {_sanitize_error(body)}") from exc
        except urllib.error.URLError as exc:
            raise TeamsConnectorError(f"Bot Connector request failed: {exc.reason}") from exc
        if not body:
            return {}
        try:
            decoded = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}

    @staticmethod
    def _conversation_url(conversation_ref: dict[str, Any]) -> str:
        service_url = str(conversation_ref.get("service_url") or conversation_ref.get("serviceUrl") or "").rstrip("/")
        conversation_id = str(conversation_ref.get("conversation_id") or conversation_ref.get("conversationId") or "")
        if not service_url or not conversation_id:
            raise TeamsConnectorError("Teams conversation reference is missing service URL or conversation ID")
        return f"{service_url}/v3/conversations/{_quote(conversation_id)}"


def _quote(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


def _sanitize_error(value: str) -> str:
    cleaned = str(value or "")
    cleaned = cleaned.replace("Bearer ", "Bearer <redacted> ")
    return cleaned
