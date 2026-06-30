from __future__ import annotations

import asyncio
import importlib.util
import json
import pathlib
import sys
import tempfile
import types
import unittest
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

PLUGIN_DIR = pathlib.Path(__file__).resolve().parents[1]


def _install_plugin_api_stub():
    plugins_module = types.ModuleType("plugins")
    api_module = types.ModuleType("plugins.api")

    @dataclass
    class ChannelCapabilities:
        photo_in: bool = False
        voice_in: bool = False
        document_in: bool = False
        photo_out: bool = False
        document_out: bool = False
        buttons: bool = False
        streaming: bool = False
        typing: bool = False
        reactions: bool = False
        slash_commands: bool = False

    class Channel:
        pass

    @dataclass
    class ChannelAttachment:
        id: str = ""
        filename: str = "attachment"
        content_type: str = ""
        size_bytes: int = 0
        data: bytes | None = None
        local_path: str = ""
        url: str = ""
        kind: str = "file"
        caption: str = ""
        metadata: dict[str, Any] = field(default_factory=dict)

    @dataclass
    class ChannelInboundMessage:
        channel_name: str
        external_conversation_id: str
        sender_id: str
        text: str = ""
        sender_display_name: str = ""
        platform_message_id: str = ""
        platform_thread_id: str = ""
        conversation_type: str = ""
        is_direct: bool = False
        is_mention: bool = False
        attachments: list[ChannelAttachment] = field(default_factory=list)
        metadata: dict[str, Any] = field(default_factory=dict)

    @dataclass
    class ChannelOutboundCallbacks:
        send_text: Any
        send_typing: Any = None
        start_stream: Any = None
        update_stream: Any = None
        finish_stream: Any = None
        send_photo: Any = None
        send_document: Any = None
        send_approval_request: Any = None
        update_approval_message: Any = None

    @dataclass
    class ChannelRunResult:
        thread_id: str
        answer: str = ""
        handled: bool = False

    @dataclass
    class ChannelAttachmentResult:
        prompt_text: str = ""
        error: str = ""

    @dataclass
    class PluginWebhookRequest:
        method: str
        path: str
        query: dict[str, str]
        headers: dict[str, str]
        body: bytes
        client_host: str = ""

        def json(self):
            return json.loads(self.body.decode("utf-8") if self.body else "{}")

    @dataclass
    class PluginWebhookResponse:
        status_code: int = 200
        body: str | bytes = ""
        media_type: str = "text/plain"
        headers: dict[str, str] = field(default_factory=dict)

    api_module.Channel = Channel
    api_module.ChannelCapabilities = ChannelCapabilities
    api_module.ChannelAttachment = ChannelAttachment
    api_module.ChannelInboundMessage = ChannelInboundMessage
    api_module.ChannelOutboundCallbacks = ChannelOutboundCallbacks
    api_module.ChannelRunResult = ChannelRunResult
    api_module.ChannelAttachmentResult = ChannelAttachmentResult
    api_module.PluginWebhookRequest = PluginWebhookRequest
    api_module.PluginWebhookResponse = PluginWebhookResponse
    plugins_module.api = api_module
    sys.modules["plugins"] = plugins_module
    sys.modules["plugins.api"] = api_module


def _load_module(name: str):
    _install_plugin_api_stub()
    if str(PLUGIN_DIR) not in sys.path:
        sys.path.insert(0, str(PLUGIN_DIR))
    spec = importlib.util.spec_from_file_location(name, PLUGIN_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _activity(**overrides):
    activity = {
        "type": "message",
        "id": "activity-1",
        "channelId": "msteams",
        "serviceUrl": "https://smba.example.test/amer/",
        "conversation": {"id": "conversation-1", "conversationType": "personal"},
        "from": {"id": "user-1", "name": "Alice Example", "aadObjectId": "aad-1"},
        "recipient": {"id": "bot-1", "name": "Row-Bot"},
        "channelData": {"tenant": {"id": "tenant-1"}},
        "text": "hello",
    }
    activity.update(overrides)
    return activity


class FakeVerifier:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def verify_authorization_header(self, authorization, *, bot_app_id, activity):
        self.calls.append((authorization, bot_app_id, activity))
        if self.fail or not authorization:
            auth = sys.modules["teams_auth"]
            raise auth.AuthError("bad token")
        return {"aud": bot_app_id, "serviceurl": activity.get("serviceUrl")}


class FakeClient:
    def __init__(self):
        self.sent = []
        self.updated = []
        self.downloads = {}
        self.uploads = []
        self.file_consents = []

    def send_activity(self, ref, activity):
        self.sent.append((dict(ref), activity))
        return f"activity-{len(self.sent)}"

    def update_activity(self, ref, activity_id, activity):
        self.updated.append((dict(ref), activity_id, activity))
        return activity_id

    def send_typing(self, ref):
        self.sent.append((dict(ref), {"type": "typing"}))

    def download_attachment(self, url, *, bearer_token="", max_bytes=0):
        data = self.downloads.get(url, b"file")
        if max_bytes and len(data) > max_bytes:
            client = _load_module("teams_client")
            raise client.TeamsConnectorError("Attachment exceeds configured size limit")
        return data

    def send_file_consent(self, ref, file_path, caption=None):
        self.file_consents.append((dict(ref), file_path, caption))
        return "file-consent-activity", "file-id-1"

    def upload_file_to_consent_url(self, upload_url, file_path):
        self.uploads.append((upload_url, file_path))

    def send_file_card(self, ref, upload_info):
        self.sent.append((dict(ref), {"file_card": upload_info}))
        return "file-card-activity"


class FakeAPI:
    def __init__(self, config=None, secrets=None):
        self.config = dict(config or {})
        self.secrets = dict(secrets or {})
        self.channels = []
        self.messages = []
        self.approvals = []
        self.webhooks = {}
        self.approved_users = set()
        self.pairing_result = False

    def get_config(self, key, default=None):
        return self.config.get(key, default)

    def set_config(self, key, value):
        self.config[key] = value

    def get_secret(self, key):
        return self.secrets.get(key)

    def register_channel(self, channel):
        self.channels.append(channel)

    def register_webhook_route(self, name, handler, *, methods=None, max_body_bytes=0):
        self.webhooks[name] = (handler, methods, max_body_bytes)
        return f"/plugin-webhooks/microsoft-teams-channel/{name}"

    def get_webhook_path(self, name):
        return f"/plugin-webhooks/microsoft-teams-channel/{name}"

    def get_webhook_url(self, name, *, start_tunnel=False):
        return f"https://public.example.test/plugin-webhooks/microsoft-teams-channel/{name}"

    async def handle_channel_message(self, message, callbacks, **kwargs):
        self.messages.append((message, callbacks, kwargs))
        await callbacks.send_text("agent reply")
        return types.SimpleNamespace(thread_id="teams_conversation-1", handled=True)

    async def handle_channel_approval(self, **kwargs):
        self.approvals.append(kwargs)
        return types.SimpleNamespace(thread_id=kwargs["thread_id"], handled=True)

    def record_channel_activity(self, channel_name):
        self.config["last_activity"] = channel_name

    def verify_channel_pairing_code(self, channel_name, user_id, code, *, display_name=""):
        self.config["pairing_attempt"] = (channel_name, user_id, code, display_name)
        if self.pairing_result:
            self.approved_users.add(user_id)
        return self.pairing_result

    def is_channel_user_approved(self, channel_name, user_id):
        return user_id in self.approved_users

    def get_channel_approved_users(self, channel_name):
        return sorted(self.approved_users)


def _configured_api(**overrides):
    config = {
        "bot_app_id": "app-id-1",
        "authority_tenant": "botframework.com",
        "auth_mode": "pairing",
        "require_mention_in_channels": True,
        "enable_streaming": True,
        "max_attachment_mb": 10,
    }
    config.update(overrides)
    return FakeAPI(config=config, secrets={"bot_client_secret": "secret"})


def _request(activity, auth="Bearer token"):
    api_module = sys.modules["plugins.api"]
    return api_module.PluginWebhookRequest(
        method="POST",
        path="/plugin-webhooks/microsoft-teams-channel/messages",
        query={},
        headers={"Authorization": auth},
        body=json.dumps(activity).encode("utf-8"),
    )


class TestManifest(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))

    def test_manifest_shape(self):
        self.assertEqual(self.manifest["schema_version"], 2)
        self.assertEqual(self.manifest["id"], "microsoft-teams-channel")
        self.assertEqual(self.manifest["provides"]["channels"], [{"id": "teams"}])
        for permission in ["network", "messaging", "external_send", "account", "files"]:
            self.assertIn(permission, self.manifest["permissions"])

    def test_required_setup_declared(self):
        self.assertIn("bot_app_id", self.manifest["settings"])
        self.assertIn("bot_client_secret", self.manifest["secrets"])
        health_types = {item["type"] for item in self.manifest["health_checks"]}
        self.assertIn("required_settings", health_types)
        self.assertIn("required_secrets", health_types)
        self.assertIn("channel_configured", health_types)


class TestRegistration(unittest.TestCase):
    def setUp(self):
        self.plugin_main = _load_module("plugin_main")

    def test_register_registers_channel(self):
        api = _configured_api()
        self.plugin_main.register(api)
        self.assertEqual(len(api.channels), 1)
        channel = api.channels[0]
        self.assertEqual(channel.name, "teams")
        self.assertEqual(channel.display_name, "Microsoft Teams")
        self.assertTrue(channel.capabilities.buttons)
        self.assertTrue(channel.capabilities.streaming)

    def test_is_configured(self):
        self.assertFalse(self.plugin_main.TeamsChannel(FakeAPI()).is_configured())
        self.assertTrue(self.plugin_main.TeamsChannel(_configured_api()).is_configured())

    def test_start_stop_registers_webhook(self):
        api = _configured_api()
        channel = self.plugin_main.TeamsChannel(api)
        result = asyncio.run(channel.start())
        self.assertTrue(result)
        self.assertTrue(channel.is_running())
        self.assertIn("messages", api.webhooks)
        self.assertEqual(api.webhooks["messages"][1], ["POST"])
        asyncio.run(channel.stop())
        self.assertFalse(channel.is_running())


class TestActivityParsing(unittest.TestCase):
    def setUp(self):
        self.activity_mod = _load_module("teams_activity")

    def test_personal_message_to_inbound(self):
        activity = self.activity_mod.parse_activity(_activity())
        inbound = self.activity_mod.activity_to_inbound(activity)
        self.assertEqual(inbound.channel_name, "teams")
        self.assertEqual(inbound.sender_id, "user-1")
        self.assertEqual(inbound.conversation_type, "dm")
        self.assertTrue(inbound.is_direct)
        self.assertEqual(inbound.metadata["tenant_id"], "tenant-1")
        self.assertEqual(inbound.metadata["aad_object_id"], "aad-1")

    def test_channel_mention_stripped(self):
        raw = _activity(
            conversation={"id": "channel-conv", "conversationType": "channel"},
            text="<at>Row-Bot</at> hello channel",
            entities=[{"type": "mention", "text": "<at>Row-Bot</at>", "mentioned": {"id": "bot-1"}}],
        )
        activity = self.activity_mod.parse_activity(raw)
        self.assertTrue(self.activity_mod.is_bot_mentioned(activity))
        self.assertEqual(self.activity_mod.strip_bot_mentions(activity.text, activity), "hello channel")
        self.assertEqual(self.activity_mod.conversation_type(activity), "channel")

    def test_approval_and_file_consent_detection(self):
        approval = self.activity_mod.parse_activity(_activity(value={"row_bot_action": "approval"}))
        self.assertTrue(self.activity_mod.is_approval_action(approval))
        consent = self.activity_mod.parse_activity(_activity(type="invoke", name="fileConsent/invoke"))
        self.assertTrue(self.activity_mod.is_file_consent_action(consent))


class TestStorage(unittest.TestCase):
    def setUp(self):
        self.storage = _load_module("teams_storage")

    def test_conversation_refs_persist_and_cap(self):
        api = FakeAPI()
        for index in range(3):
            self.storage.upsert_conversation_ref(
                api,
                {
                    "conversation_id": f"c-{index}",
                    "service_url": "https://service",
                    "conversation_type": "dm",
                    "user_id": f"u-{index}",
                    "last_seen_at": f"2026-06-30T00:00:0{index}Z",
                },
                limit=2,
            )
        refs = self.storage.get_conversation_refs(api)
        self.assertEqual(set(refs), {"c-1", "c-2"})
        self.assertNotIn("text", json.dumps(refs))

    def test_invalid_json_is_safe(self):
        api = FakeAPI(config={"conversation_refs": "{bad"})
        self.assertEqual(self.storage.get_conversation_refs(api), {})


class TestAuth(unittest.TestCase):
    def setUp(self):
        self.auth = _load_module("teams_auth")

    def test_outbound_token_request_and_cache(self):
        calls = []
        now = [1000.0]

        def fake_post(url, form):
            calls.append((url, form))
            return {"access_token": "token-1", "expires_in": 3600}

        provider = self.auth.BotConnectorTokenProvider(
            app_id="app-id",
            client_secret="secret",
            authority_tenant="botframework.com",
            post_form_func=fake_post,
            now_func=lambda: now[0],
        )
        self.assertEqual(provider.get_token(), "token-1")
        self.assertEqual(provider.get_token(), "token-1")
        self.assertEqual(len(calls), 1)
        self.assertIn("botframework.com", calls[0][0])
        self.assertEqual(calls[0][1]["scope"], "https://api.botframework.com/.default")
        now[0] += 3400
        provider.get_token()
        self.assertEqual(len(calls), 2)

    def test_jwt_verifier_rejects_missing_auth(self):
        verifier = self.auth.BotFrameworkJWTVerifier(fetch_json_func=lambda url: {})
        with self.assertRaises(self.auth.AuthError):
            verifier.verify_authorization_header("", bot_app_id="app", activity={})

    def test_jwt_verifier_validates_claims_with_monkeypatched_jwt(self):
        fake_jwt = types.SimpleNamespace()
        fake_jwt.get_unverified_header = lambda token: {"alg": "RS256", "kid": "kid-1"}
        fake_jwt.algorithms = types.SimpleNamespace(
            RSAAlgorithm=types.SimpleNamespace(from_jwk=lambda value: "public-key")
        )
        fake_jwt.decode = MagicMock(return_value={
            "aud": "app-id",
            "iss": "https://api.botframework.com",
            "serviceurl": "https://service",
        })
        fetches = []

        def fake_fetch(url):
            fetches.append(url)
            if "openidconfiguration" in url:
                return {"jwks_uri": "https://keys.example.test"}
            return {"keys": [{"kid": "kid-1", "kty": "RSA", "endorsements": ["msteams"]}]}

        with patch.object(self.auth, "jwt", fake_jwt):
            verifier = self.auth.BotFrameworkJWTVerifier(fetch_json_func=fake_fetch, now_func=lambda: 1000)
            claims = verifier.verify_authorization_header(
                "Bearer signed",
                bot_app_id="app-id",
                activity={"serviceUrl": "https://service"},
            )
        self.assertEqual(claims["aud"], "app-id")
        self.assertEqual(len(fetches), 2)
        fake_jwt.decode.assert_called_once()


class TestConnectorClient(unittest.TestCase):
    def setUp(self):
        self.client_mod = _load_module("teams_client")

    def test_send_update_typing_urls(self):
        requests = []

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, *args):
                return b'{"id": "activity-1"}'

        def fake_urlopen(req, timeout=0):
            requests.append(req)
            return Resp()

        client = self.client_mod.BotConnectorClient(lambda: "token", urlopen=fake_urlopen)
        ref = {"service_url": "https://service.example.test", "conversation_id": "conv 1"}
        self.assertEqual(client.send_activity(ref, {"type": "message", "text": "hi"}), "activity-1")
        client.update_activity(ref, "activity-1", {"type": "message", "text": "edit"})
        client.send_typing(ref)
        self.assertEqual(requests[0].get_method(), "POST")
        self.assertIn("/v3/conversations/conv%201/activities", requests[0].full_url)
        self.assertEqual(requests[1].get_method(), "PUT")
        self.assertIn("/activities/activity-1", requests[1].full_url)

    def test_download_attachment_limit(self):
        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, size=-1):
                return b"abcdef"

        client = self.client_mod.BotConnectorClient(lambda: "token", urlopen=lambda req, timeout=0: Resp())
        with self.assertRaises(self.client_mod.TeamsConnectorError):
            client.download_attachment("https://download.example.test/file", max_bytes=3)


class TestWebhook(unittest.TestCase):
    def setUp(self):
        self.plugin_main = _load_module("plugin_main")

    def _started_channel(self, api=None):
        api = api or _configured_api()
        channel = self.plugin_main.TeamsChannel(api)
        channel.auth_verifier = FakeVerifier()
        channel._client = FakeClient()
        asyncio.run(channel.start())
        return api, channel

    def test_missing_auth_returns_403(self):
        api, channel = self._started_channel()
        response = asyncio.run(channel._handle_webhook(_request(_activity(), auth="")))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(api.messages, [])

    def test_normal_authorized_message_calls_row_bot(self):
        api = _configured_api()
        api.approved_users.add("user-1")
        api, channel = self._started_channel(api)
        response = asyncio.run(channel._handle_webhook(_request(_activity(text="hello bot"))))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(api.messages), 1)
        message = api.messages[0][0]
        self.assertEqual(message.text, "hello bot")
        self.assertEqual(channel._client.sent[-1][1]["text"], "agent reply")

    def test_channel_non_mention_is_ignored(self):
        api = _configured_api()
        api.approved_users.add("user-1")
        api, channel = self._started_channel(api)
        response = asyncio.run(channel._handle_webhook(_request(_activity(
            conversation={"id": "chan", "conversationType": "channel"},
            text="quiet",
        ))))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(api.messages, [])

    def test_pairing_message_verifies_code_without_agent_call(self):
        api = _configured_api()
        api.pairing_result = True
        api, channel = self._started_channel(api)
        response = asyncio.run(channel._handle_webhook(_request(_activity(text="123456"))))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(api.messages, [])
        self.assertEqual(api.config["pairing_attempt"][2], "123456")
        self.assertIn("paired", channel._client.sent[-1][1]["text"].lower())

    def test_duplicate_activity_is_ignored(self):
        api = _configured_api()
        api.approved_users.add("user-1")
        api, channel = self._started_channel(api)
        req = _request(_activity(id="dup-1"))
        asyncio.run(channel._handle_webhook(req))
        response = asyncio.run(channel._handle_webhook(req))
        self.assertEqual(response.body, "duplicate")
        self.assertEqual(len(api.messages), 1)

    def test_inbound_file_download_becomes_attachment(self):
        api = _configured_api()
        api.approved_users.add("user-1")
        api, channel = self._started_channel(api)
        channel._client.downloads["https://download.example.test/file"] = b"hello file"
        raw = _activity(
            text="please read",
            attachments=[
                {
                    "contentType": "application/vnd.microsoft.teams.file.download.info",
                    "name": "notes.txt",
                    "content": {"downloadUrl": "https://download.example.test/file", "uniqueId": "file-1"},
                }
            ],
        )
        response = asyncio.run(channel._handle_webhook(_request(raw)))
        self.assertEqual(response.status_code, 200)
        attachment = api.messages[0][0].attachments[0]
        self.assertEqual(attachment.filename, "notes.txt")
        self.assertEqual(attachment.data, b"hello file")

    def test_invoke_approval_schedules_resume(self):
        api = _configured_api()
        api.approved_users.add("user-1")
        api, channel = self._started_channel(api)

        async def run():
            response = await channel._handle_webhook(_request(_activity(
                type="invoke",
                id="invoke-1",
                replyToId="approval-activity",
                value={
                    "row_bot_action": "approval",
                    "approved": True,
                    "thread_id": "thread-1",
                    "interrupt_ids": ["int-1"],
                },
            )))
            await asyncio.sleep(0)
            return response

        response = asyncio.run(run())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(api.approvals[0]["thread_id"], "thread-1")
        self.assertTrue(api.approvals[0]["approved"])
        self.assertEqual(channel._client.updated[0][1], "approval-activity")

    def test_file_consent_accept_uploads_pending_file(self):
        api = _configured_api()
        api.approved_users.add("user-1")
        api, channel = self._started_channel(api)
        storage = _load_module("teams_storage")
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"file")
            tmp_path = pathlib.Path(tmp.name)
        try:
            storage.put_pending_file_upload(api, "file-id-1", {
                "conversation_id": "conversation-1",
                "file_path": str(tmp_path),
                "caption": "caption",
            })
            response = asyncio.run(channel._handle_webhook(_request(_activity(
                type="invoke",
                id="file-consent-1",
                name="fileConsent/invoke",
                value={
                    "action": "accept",
                    "context": {"file_id": "file-id-1"},
                    "uploadInfo": {
                        "uploadUrl": "https://upload.example.test/file",
                        "contentUrl": "https://download.example.test/file",
                        "name": "report.txt",
                    },
                },
            ))))
        finally:
            tmp_path.unlink(missing_ok=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(channel._client.uploads[0][0], "https://upload.example.test/file")
        self.assertEqual(channel._client.sent[-1][1]["file_card"]["name"], "report.txt")


class TestCallbacksAndOutbound(unittest.TestCase):
    def setUp(self):
        self.plugin_main = _load_module("plugin_main")
        self.storage = _load_module("teams_storage")

    def test_stream_callbacks_send_and_update(self):
        api = _configured_api()
        channel = self.plugin_main.TeamsChannel(api)
        channel._client = FakeClient()
        ref = {
            "conversation_id": "conversation-1",
            "service_url": "https://service",
            "conversation_type": "dm",
            "user_id": "user-1",
        }
        callbacks = channel._callbacks_for_ref(ref)

        async def run():
            stream_ref = await callbacks.start_stream("starting")
            await callbacks.update_stream(stream_ref, "middle")
            await callbacks.finish_stream(stream_ref, "done")

        asyncio.run(run())
        self.assertEqual(channel._client.sent[0][1]["text"], "starting")
        self.assertEqual(channel._client.updated[-1][2]["text"], "done")

    def test_send_message_uses_stored_ref(self):
        api = _configured_api()
        self.storage.upsert_conversation_ref(api, {
            "conversation_id": "conversation-1",
            "service_url": "https://service",
            "conversation_type": "dm",
            "user_id": "user-1",
        })
        channel = self.plugin_main.TeamsChannel(api)
        channel._client = FakeClient()
        channel.send_message("conversation-1", "hello")
        self.assertEqual(channel._client.sent[0][1]["text"], "hello")

    def test_send_document_uses_personal_file_consent(self):
        api = _configured_api()
        channel = self.plugin_main.TeamsChannel(api)
        channel._client = FakeClient()
        ref = {
            "conversation_id": "conversation-1",
            "service_url": "https://service",
            "conversation_type": "dm",
            "user_id": "user-1",
        }
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"file")
            tmp_path = pathlib.Path(tmp.name)
        try:
            channel._send_file_to_ref(ref, str(tmp_path), "caption")
        finally:
            tmp_path.unlink(missing_ok=True)
        self.assertEqual(channel._client.file_consents[0][2], "caption")
        self.assertIn("pending_file_uploads", api.config)

    def test_group_file_send_reports_limitation(self):
        api = _configured_api()
        channel = self.plugin_main.TeamsChannel(api)
        channel._client = FakeClient()
        ref = {
            "conversation_id": "conversation-1",
            "service_url": "https://service",
            "conversation_type": "channel",
            "user_id": "user-1",
        }
        with self.assertRaises(RuntimeError):
            channel._send_file_to_ref(ref, "missing.txt", None)


class TestSkill(unittest.TestCase):
    def test_skill_file_exists_with_frontmatter(self):
        text = (PLUGIN_DIR / "skills" / "teams_channel" / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---"))
        self.assertIn("name: teams_channel", text)
        self.assertIn("display_name:", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
