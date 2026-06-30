"""Microsoft Teams activity parsing helpers for the Row-Bot channel plugin."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from plugins.api import ChannelAttachment, ChannelInboundMessage

TEAMS_CHANNEL_ID = "msteams"
FILE_DOWNLOAD_INFO_TYPE = "application/vnd.microsoft.teams.file.download.info"
FILE_CONSENT_INVOKE_NAMES = {"fileConsent/invoke", "fileConsent"}


@dataclass
class TeamsActivity:
    raw: dict[str, Any]
    type: str = ""
    id: str = ""
    channel_id: str = ""
    service_url: str = ""
    text: str = ""
    value: Any = None
    name: str = ""
    conversation: dict[str, Any] | None = None
    from_user: dict[str, Any] | None = None
    recipient: dict[str, Any] | None = None
    channel_data: dict[str, Any] | None = None
    attachments: list[dict[str, Any]] | None = None
    entities: list[dict[str, Any]] | None = None
    reply_to_id: str = ""


def parse_activity(raw: dict[str, Any]) -> TeamsActivity:
    """Convert a raw Bot Framework activity dict into a defensive wrapper."""
    if not isinstance(raw, dict):
        raw = {}
    return TeamsActivity(
        raw=raw,
        type=str(raw.get("type") or ""),
        id=str(raw.get("id") or ""),
        channel_id=str(raw.get("channelId") or ""),
        service_url=str(raw.get("serviceUrl") or ""),
        text=str(raw.get("text") or ""),
        value=raw.get("value"),
        name=str(raw.get("name") or ""),
        conversation=_dict(raw.get("conversation")),
        from_user=_dict(raw.get("from")),
        recipient=_dict(raw.get("recipient")),
        channel_data=_dict(raw.get("channelData")),
        attachments=_dict_list(raw.get("attachments")),
        entities=_dict_list(raw.get("entities")),
        reply_to_id=str(raw.get("replyToId") or ""),
    )


def activity_to_inbound(
    activity: TeamsActivity,
    attachments: list[ChannelAttachment] | None = None,
) -> ChannelInboundMessage:
    """Build Row-Bot's public inbound message envelope from a Teams activity."""
    conversation_id = activity_conversation_key(activity)
    conv_type = conversation_type(activity)
    metadata = {
        "tenant_id": tenant_id(activity),
        "aad_object_id": aad_object_id(activity),
        "service_url": activity.service_url,
        "team_id": team_id(activity),
        "teams_channel_id": teams_channel_id(activity),
        "conversation_type": conv_type,
    }
    return ChannelInboundMessage(
        channel_name="teams",
        external_conversation_id=conversation_id,
        sender_id=activity_sender_id(activity),
        text=strip_bot_mentions(activity.text, activity),
        sender_display_name=activity_sender_display_name(activity),
        platform_message_id=activity.id,
        platform_thread_id=activity.reply_to_id,
        conversation_type=conv_type,
        is_direct=conv_type == "dm",
        is_mention=is_bot_mentioned(activity),
        attachments=list(attachments or []),
        metadata={key: value for key, value in metadata.items() if value},
    )


def strip_bot_mentions(text: str, activity: TeamsActivity) -> str:
    """Remove the bot mention Teams injects into channel text."""
    cleaned = text or ""
    bot_id = str((activity.recipient or {}).get("id") or "")
    for entity in activity.entities or []:
        if str(entity.get("type") or "").lower() != "mention":
            continue
        mentioned = _dict(entity.get("mentioned"))
        mentioned_id = str(mentioned.get("id") or "")
        mention_text = str(entity.get("text") or "")
        if bot_id and mentioned_id == bot_id and mention_text:
            cleaned = cleaned.replace(mention_text, "")
    if is_bot_mentioned(activity):
        cleaned = re.sub(r"<at>[^<]+</at>", "", cleaned, count=1, flags=re.IGNORECASE)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def conversation_type(activity: TeamsActivity) -> str:
    """Return Row-Bot's normalized conversation scope: dm, group, or channel."""
    raw_type = str((activity.conversation or {}).get("conversationType") or "").lower()
    if raw_type in {"personal", "dm", "direct"}:
        return "dm"
    if raw_type in {"channel", "team"}:
        return "channel"
    if raw_type in {"groupchat", "group", "group_chat"}:
        return "group"
    if team_id(activity) or teams_channel_id(activity):
        return "channel"
    return "group" if activity_conversation_key(activity) else ""


def tenant_id(activity: TeamsActivity) -> str:
    channel_data = activity.channel_data or {}
    tenant = _dict(channel_data.get("tenant"))
    return str(
        tenant.get("id")
        or channel_data.get("tenantId")
        or channel_data.get("tid")
        or ""
    )


def aad_object_id(activity: TeamsActivity) -> str:
    from_user = activity.from_user or {}
    return str(from_user.get("aadObjectId") or from_user.get("aad_object_id") or "")


def team_id(activity: TeamsActivity) -> str:
    data = activity.channel_data or {}
    team = _dict(data.get("team"))
    return str(team.get("id") or data.get("teamId") or "")


def teams_channel_id(activity: TeamsActivity) -> str:
    data = activity.channel_data or {}
    channel = _dict(data.get("channel"))
    return str(channel.get("id") or data.get("channelId") or "")


def is_bot_mentioned(activity: TeamsActivity) -> bool:
    bot_id = str((activity.recipient or {}).get("id") or "")
    for entity in activity.entities or []:
        if str(entity.get("type") or "").lower() != "mention":
            continue
        mentioned_id = str(_dict(entity.get("mentioned")).get("id") or "")
        if bot_id and mentioned_id == bot_id:
            return True
    return bool(re.search(r"<at>[^<]+</at>", activity.text or "", re.IGNORECASE))


def activity_sender_id(activity: TeamsActivity) -> str:
    return str((activity.from_user or {}).get("id") or "")


def activity_sender_display_name(activity: TeamsActivity) -> str:
    return str((activity.from_user or {}).get("name") or "")


def activity_conversation_key(activity: TeamsActivity) -> str:
    return str((activity.conversation or {}).get("id") or "")


def is_approval_action(activity: TeamsActivity) -> bool:
    value = approval_payload(activity)
    return str(value.get("row_bot_action") or "") == "approval"


def approval_payload(activity: TeamsActivity) -> dict[str, Any]:
    return _dict(activity.value)


def is_file_consent_action(activity: TeamsActivity) -> bool:
    value = _dict(activity.value)
    return activity.name in FILE_CONSENT_INVOKE_NAMES or str(value.get("row_bot_action") or "") == "file_upload"


def file_consent_payload(activity: TeamsActivity) -> dict[str, Any]:
    return _dict(activity.value)


def conversation_reference(activity: TeamsActivity) -> dict[str, Any]:
    """Return the display-safe conversation metadata persisted by the plugin."""
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "conversation_id": activity_conversation_key(activity),
        "service_url": activity.service_url,
        "conversation_type": conversation_type(activity),
        "tenant_id": tenant_id(activity),
        "bot_id": str((activity.recipient or {}).get("id") or ""),
        "user_id": activity_sender_id(activity),
        "aad_object_id": aad_object_id(activity),
        "team_id": team_id(activity),
        "channel_id": teams_channel_id(activity),
        "display_name": activity_sender_display_name(activity),
        "last_seen_at": now,
    }


def attachment_kind(content_type: str, filename: str = "") -> str:
    lower_type = (content_type or "").lower()
    lower_name = (filename or "").lower()
    if lower_type.startswith("image/") or lower_name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
        return "image"
    if lower_type.startswith("audio/") or lower_name.endswith((".mp3", ".wav", ".m4a", ".ogg")):
        return "audio"
    return "file"


def safe_filename(value: str, fallback: str = "attachment") -> str:
    name = re.sub(r"[\\/:*?\"<>|]+", "_", value or "").strip(" .")
    return name or fallback


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]
