"""Microsoft Teams channel adapter for Row-Bot."""

from __future__ import annotations

import asyncio
import json
import mimetypes
from pathlib import Path
from typing import Any

from plugins.api import (
    Channel,
    ChannelAttachment,
    ChannelCapabilities,
    ChannelOutboundCallbacks,
    PluginWebhookResponse,
)

import teams_activity
import teams_auth
import teams_cards
import teams_client
import teams_storage


class TeamsChannel(Channel):
    def __init__(self, api):
        self.api = api
        self._running = False
        self._webhook_path = ""
        self._webhook_url = ""
        self._seen_activity_ids: dict[str, float] = {}
        self._background_tasks: set[asyncio.Task] = set()
        self.auth_verifier = teams_auth.BotFrameworkJWTVerifier()
        self._token_provider = teams_auth.BotConnectorTokenProvider(
            app_id=lambda: self._config("bot_app_id", ""),
            client_secret=lambda: self._secret("bot_client_secret"),
            authority_tenant=lambda: self._config("authority_tenant", "botframework.com"),
        )
        self._client: teams_client.BotConnectorClient | None = None

    @property
    def name(self):
        return "teams"

    @property
    def display_name(self):
        return "Microsoft Teams"

    @property
    def icon(self):
        return "groups"

    @property
    def capabilities(self):
        return ChannelCapabilities(
            photo_in=True,
            voice_in=True,
            document_in=True,
            photo_out=True,
            document_out=True,
            buttons=True,
            streaming=True,
            typing=True,
            reactions=False,
            slash_commands=True,
        )

    @property
    def needs_tunnel(self):
        return True

    @property
    def setup_guide(self):
        path = self._webhook_path or self._safe_webhook_path()
        public_base_url = self._config("public_base_url", "").rstrip("/")
        endpoint = f"{public_base_url}{path}" if public_base_url else (self._webhook_url or path)
        return (
            "Configure the Azure Bot messaging endpoint to:\n\n"
            f"`{endpoint}`\n\n"
            "Install the Teams app for personal chat first, generate a Row-Bot "
            "Teams pairing code, then DM that code to the bot."
        )

    async def start(self):
        if not self.is_configured():
            self._running = False
            return False
        self._webhook_path = self.api.register_webhook_route(
            "messages",
            self._handle_webhook,
            methods=["POST"],
            max_body_bytes=1_048_576,
        )
        if self._bool_config("auto_start_tunnel", False):
            self._webhook_url = self.api.get_webhook_url("messages", start_tunnel=True)
        self._running = True
        return True

    async def stop(self):
        self._running = False
        for task in list(self._background_tasks):
            if not task.done():
                task.cancel()
        self._background_tasks.clear()

    def is_configured(self):
        return bool(
            self._config("bot_app_id", "").strip()
            and self._config("authority_tenant", "botframework.com").strip()
            and self._secret("bot_client_secret").strip()
        )

    def is_running(self):
        return self._running

    def get_default_target(self):
        configured = self._config("default_target", "").strip()
        if configured:
            return configured
        approved = set()
        try:
            approved = set(self.api.get_channel_approved_users("teams") or [])
        except Exception:
            approved = set()
        ref = teams_storage.first_personal_conversation_ref(self.api, approved)
        if ref:
            return str(ref["conversation_id"])
        raise RuntimeError(
            "Microsoft Teams default target is not configured. Set Default Conversation ID "
            "or pair with the bot in a personal Teams chat first."
        )

    def send_message(self, target, text):
        ref = self._resolve_target_ref(str(target))
        self._send_text_to_ref(ref, text)

    def send_photo(self, target, file_path, caption=None):
        self._send_file_to_ref(self._resolve_target_ref(str(target)), file_path, caption)

    def send_document(self, target, file_path, caption=None):
        self._send_file_to_ref(self._resolve_target_ref(str(target)), file_path, caption)

    def send_approval_request(self, target, interrupt_data, config):
        ref = self._resolve_target_ref(str(target))
        return self._send_approval_to_ref(ref, interrupt_data, config or {})

    def update_approval_message(self, message_ref, status, source=""):
        conversation_id, activity_id = _split_message_ref(str(message_ref or ""))
        if not conversation_id or not activity_id:
            return None
        ref = teams_storage.get_conversation_ref(self.api, conversation_id)
        if not ref:
            return None
        activity = {
            "type": "message",
            "attachments": [teams_cards.resolved_approval_attachment(status, source)],
        }
        return self._connector().update_activity(ref, activity_id, activity)

    async def _handle_webhook(self, request):
        if not self._running:
            return _text_response(503, "Microsoft Teams channel is not running")
        if str(request.method).upper() != "POST":
            return _text_response(405, "Method not allowed")
        try:
            raw = request.json()
        except Exception:
            return _text_response(400, "Invalid JSON body")
        activity = teams_activity.parse_activity(raw if isinstance(raw, dict) else {})

        try:
            self._verify_request(request, activity)
        except teams_auth.AuthError as exc:
            return _text_response(403, str(exc))

        if activity.channel_id != teams_activity.TEAMS_CHANNEL_ID:
            return _text_response(403, "Only Microsoft Teams activities are accepted")
        if not self._tenant_allowed(teams_activity.tenant_id(activity)):
            return _text_response(403, "Teams tenant is not allowed")
        if self._is_duplicate(activity.id):
            return _text_response(200, "duplicate")

        if activity.type == "message":
            return await self._handle_message_activity(activity)
        if activity.type == "invoke":
            return await self._handle_invoke_activity(activity)
        if activity.type in {"conversationUpdate", "installationUpdate"}:
            self._cache_conversation(activity)
            return _text_response(200, "ok")
        return _text_response(200, "ignored")

    async def _handle_message_activity(self, activity):
        ref = self._cache_conversation(activity)
        if teams_activity.is_approval_action(activity):
            await self._run_approval_action(activity, ref)
            return _text_response(200, "approval handled")
        if self._requires_mention(activity) and not teams_activity.is_bot_mentioned(activity):
            return _text_response(200, "ignored")

        text = teams_activity.strip_bot_mentions(activity.text, activity)
        if not await self._ensure_sender_authorized(activity, ref, text):
            return _text_response(200, "authorization required")

        attachments, warnings = self._attachments_from_activity(activity)
        if warnings:
            warning_text = "\n".join(warnings)
            text = f"{text}\n\n{warning_text}".strip()
        if not text and not attachments:
            return _text_response(200, "empty message")

        message = teams_activity.activity_to_inbound(activity, attachments)
        message.text = text
        callbacks = self._callbacks_for_ref(ref)
        try:
            self.api.record_channel_activity("teams")
        except Exception:
            pass
        await self.api.handle_channel_message(
            message,
            callbacks,
            channel=self,
            stream=self._bool_config("enable_streaming", True),
        )
        return _text_response(200, "handled")

    async def _handle_invoke_activity(self, activity):
        ref = self._cache_conversation(activity)
        if teams_activity.is_approval_action(activity):
            self._schedule(self._run_approval_action(activity, ref))
            return _json_response(200, {"status": "accepted"})
        if teams_activity.is_file_consent_action(activity):
            try:
                self._handle_file_consent(activity, ref)
            except teams_client.TeamsConnectorError as exc:
                return _json_response(500, {"status": "error", "message": str(exc)})
            return _json_response(200, {"status": "accepted"})
        return _json_response(200, {"status": "ignored"})

    async def _run_approval_action(self, activity, ref):
        payload = teams_activity.approval_payload(activity)
        thread_id = str(payload.get("thread_id") or "")
        approved = bool(payload.get("approved"))
        interrupt_ids = _string_list(payload.get("interrupt_ids"))
        callbacks = self._callbacks_for_ref(ref)
        message_id = activity.reply_to_id or activity.id
        message_ref = _message_ref(ref, message_id)
        if message_ref:
            self.update_approval_message(message_ref, "approved" if approved else "denied", "teams")
        await self.api.handle_channel_approval(
            channel_name="teams",
            thread_id=thread_id,
            approved=approved,
            callbacks=callbacks,
            interrupt_ids=interrupt_ids,
            source="teams",
        )

    def _handle_file_consent(self, activity, ref):
        payload = teams_activity.file_consent_payload(activity)
        action = str(payload.get("action") or payload.get("response") or "").lower()
        upload_info = payload.get("uploadInfo") if isinstance(payload.get("uploadInfo"), dict) else {}
        context = payload.get("context") if isinstance(payload.get("context"), dict) else payload
        file_id = str(context.get("file_id") or context.get("fileId") or "")
        pending = teams_storage.pop_pending_file_upload(self.api, file_id)
        if not pending:
            return None
        if action in {"decline", "declined", "reject", "rejected"}:
            return None
        upload_url = str(upload_info.get("uploadUrl") or payload.get("uploadUrl") or "")
        if not upload_url:
            raise teams_client.TeamsConnectorError("Teams file upload consent did not include an upload URL")
        self._connector().upload_file_to_consent_url(upload_url, pending["file_path"])
        if upload_info:
            self._connector().send_file_card(ref, upload_info)
        return None

    async def _ensure_sender_authorized(self, activity, ref, text):
        user_id = teams_activity.activity_sender_id(activity)
        display_name = teams_activity.activity_sender_display_name(activity)
        if self._sender_authorized(user_id):
            return True
        mode = self._config("auth_mode", "pairing").strip() or "pairing"
        if mode == "pairing":
            if teams_activity.conversation_type(activity) != "dm":
                self._send_text_to_ref(ref, "Please DM the Teams bot with your Row-Bot pairing code first.")
                return False
            if text:
                try:
                    paired = self.api.verify_channel_pairing_code(
                        "teams",
                        user_id,
                        text.strip(),
                        display_name=display_name,
                    )
                except Exception:
                    paired = False
                if paired:
                    self._send_text_to_ref(ref, "Microsoft Teams is paired with Row-Bot.")
                    return False
            self._send_text_to_ref(
                ref,
                "This Teams user is not paired yet. Generate a Teams pairing code in Row-Bot, "
                "then DM the code to this bot.",
            )
            return False
        self._send_text_to_ref(ref, "This Teams user is not allowed to use Row-Bot.")
        return False

    def _sender_authorized(self, user_id):
        mode = self._config("auth_mode", "pairing").strip() or "pairing"
        if mode == "single_user":
            return bool(user_id and user_id == self._config("single_user_id", "").strip())
        if mode == "allowlist":
            try:
                return user_id in set(self.api.get_channel_approved_users("teams") or [])
            except Exception:
                return False
        try:
            return bool(self.api.is_channel_user_approved("teams", user_id))
        except Exception:
            return False

    def _callbacks_for_ref(self, ref):
        async def send_text(text):
            return self._send_text_to_ref(ref, text)

        async def send_typing():
            return self._connector().send_typing(ref)

        async def start_stream(initial_text):
            if not self._bool_config("enable_streaming", True):
                return None
            activity_id = self._connector().send_activity(
                ref,
                {"type": "message", "text": initial_text or "Working..."},
            )
            return {
                "conversation_id": ref.get("conversation_id", ""),
                "activity_id": activity_id,
                "service_url": ref.get("service_url", ""),
            }

        async def update_stream(stream_ref, text):
            if not stream_ref:
                return None
            activity_id = str(stream_ref.get("activity_id") or "")
            if not activity_id:
                return None
            return self._connector().update_activity(
                ref,
                activity_id,
                {"type": "message", "text": text or ""},
            )

        async def finish_stream(stream_ref, final_text):
            return await update_stream(stream_ref, final_text)

        async def send_photo(file_path, caption=None):
            return self._send_file_to_ref(ref, file_path, caption)

        async def send_document(file_path, caption=None):
            return self._send_file_to_ref(ref, file_path, caption)

        async def send_approval_request(interrupt_data, config):
            return self._send_approval_to_ref(ref, interrupt_data, config or {})

        async def update_approval_message(message_ref, status, source=""):
            return self.update_approval_message(message_ref, status, source)

        return ChannelOutboundCallbacks(
            send_text=send_text,
            send_typing=send_typing,
            start_stream=start_stream,
            update_stream=update_stream,
            finish_stream=finish_stream,
            send_photo=send_photo,
            send_document=send_document,
            send_approval_request=send_approval_request,
            update_approval_message=update_approval_message,
        )

    def _attachments_from_activity(self, activity):
        attachments: list[ChannelAttachment] = []
        warnings: list[str] = []
        max_bytes = max(1, int(self._float_config("max_attachment_mb", 10) * 1024 * 1024))
        for raw in activity.attachments or []:
            content_type = str(raw.get("contentType") or "")
            content = raw.get("content") if isinstance(raw.get("content"), dict) else {}
            content_url = str(raw.get("contentUrl") or content.get("downloadUrl") or "")
            filename = teams_activity.safe_filename(
                str(raw.get("name") or content.get("name") or content.get("fileName") or "attachment")
            )
            if not content_url:
                warnings.append(f"Teams attachment '{filename}' is not directly downloadable by this channel plugin.")
                continue
            try:
                bearer = self._token_provider.get_token() if content_type != teams_activity.FILE_DOWNLOAD_INFO_TYPE else ""
                data = self._connector().download_attachment(
                    content_url,
                    bearer_token=bearer,
                    max_bytes=max_bytes,
                )
            except (teams_auth.AuthError, teams_client.TeamsConnectorError) as exc:
                warnings.append(f"Teams attachment '{filename}' could not be downloaded: {exc}")
                continue
            guessed_type = content_type
            if content_type == teams_activity.FILE_DOWNLOAD_INFO_TYPE:
                guessed_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            attachments.append(
                ChannelAttachment(
                    id=str(raw.get("id") or content.get("uniqueId") or ""),
                    filename=filename,
                    content_type=guessed_type,
                    size_bytes=len(data),
                    data=data,
                    kind=teams_activity.attachment_kind(guessed_type, filename),
                    metadata={"teams_content_type": content_type},
                )
            )
        return attachments, warnings

    def _send_text_to_ref(self, ref, text):
        return self._connector().send_activity(ref, {"type": "message", "text": str(text or "")})

    def _send_file_to_ref(self, ref, file_path, caption=None):
        if ref.get("conversation_type") != "dm":
            raise RuntimeError(
                "Teams channel/group file sends require Microsoft 365 document access. "
                "Use personal chat file consent or a future Microsoft 365 plugin."
            )
        activity_id, file_id = self._connector().send_file_consent(ref, str(file_path), caption)
        teams_storage.put_pending_file_upload(
            self.api,
            file_id,
            {
                "conversation_id": ref.get("conversation_id", ""),
                "file_path": str(file_path),
                "caption": caption or "",
            },
        )
        return activity_id

    def _send_approval_to_ref(self, ref, interrupt_data, config):
        activity = {
            "type": "message",
            "attachments": [teams_cards.approval_attachment(interrupt_data, config or {})],
        }
        activity_id = self._connector().send_activity(ref, activity)
        return _message_ref(ref, activity_id)

    def _resolve_target_ref(self, target):
        ref = teams_storage.get_conversation_ref(self.api, target)
        if ref:
            return ref
        if target == self._config("default_target", ""):
            ref = teams_storage.get_conversation_ref(self.api, target)
            if ref:
                return ref
        raise RuntimeError(
            "Teams conversation is unknown. Send a message to Row-Bot from Teams first "
            "or configure a known Default Conversation ID."
        )

    def _cache_conversation(self, activity):
        ref = teams_storage.upsert_conversation_ref(
            self.api,
            teams_activity.conversation_reference(activity),
        )
        teams_storage.upsert_known_user(
            self.api,
            teams_activity.activity_sender_id(activity),
            {
                "display_name": teams_activity.activity_sender_display_name(activity),
                "aad_object_id": teams_activity.aad_object_id(activity),
                "tenant_id": teams_activity.tenant_id(activity),
                "last_seen_at": ref.get("last_seen_at", ""),
            },
        )
        return ref

    def _verify_request(self, request, activity):
        authorization = _header(request.headers, "authorization")
        self.auth_verifier.verify_authorization_header(
            authorization,
            bot_app_id=self._config("bot_app_id", ""),
            activity=activity.raw,
        )

    def _tenant_allowed(self, tenant):
        allowed = {
            line.strip()
            for line in str(self._config("allowed_tenant_ids", "") or "").splitlines()
            if line.strip()
        }
        return not allowed or tenant in allowed

    def _requires_mention(self, activity):
        return teams_activity.conversation_type(activity) == "channel" and self._bool_config(
            "require_mention_in_channels",
            True,
        )

    def _is_duplicate(self, activity_id):
        if not activity_id:
            return False
        now = asyncio.get_running_loop().time()
        cutoff = now - 600
        self._seen_activity_ids = {
            key: seen_at for key, seen_at in self._seen_activity_ids.items() if seen_at >= cutoff
        }
        if activity_id in self._seen_activity_ids:
            return True
        self._seen_activity_ids[activity_id] = now
        return False

    def _schedule(self, coro):
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    def _connector(self):
        if self._client is None:
            self._client = teams_client.BotConnectorClient(self._token_provider.get_token)
        return self._client

    def _config(self, key, default=None):
        try:
            value = self.api.get_config(key, default)
            return str(value if value is not None else "")
        except Exception:
            return str(default or "")

    def _secret(self, key):
        try:
            value = self.api.get_secret(key)
        except Exception:
            value = ""
        return str(value or "")

    def _bool_config(self, key, default=False):
        value = self._config(key, default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _float_config(self, key, default=0.0):
        try:
            return float(self._config(key, default))
        except (TypeError, ValueError):
            return float(default)

    def _safe_webhook_path(self):
        try:
            return self.api.get_webhook_path("messages")
        except Exception:
            return "/plugin-webhooks/microsoft-teams-channel/messages"


def register(api):
    api.register_channel(TeamsChannel(api))


def _header(headers, name):
    wanted = str(name).lower()
    for key, value in dict(headers or {}).items():
        if str(key).lower() == wanted:
            return str(value)
    return ""


def _text_response(status_code, body):
    return PluginWebhookResponse(status_code=status_code, body=body, media_type="text/plain")


def _json_response(status_code, payload):
    return PluginWebhookResponse(
        status_code=status_code,
        body=json.dumps(payload),
        media_type="application/json",
    )


def _message_ref(ref, activity_id):
    conversation_id = str(ref.get("conversation_id") or "")
    if not conversation_id or not activity_id:
        return ""
    return f"{conversation_id}:{activity_id}"


def _split_message_ref(message_ref):
    if ":" not in message_ref:
        return "", ""
    return tuple(message_ref.split(":", 1))


def _string_list(value):
    if isinstance(value, list):
        return [str(item) for item in value]
    if value in (None, ""):
        return []
    return [str(value)]
