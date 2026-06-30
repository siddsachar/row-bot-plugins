"""Display-safe plugin config storage helpers for Teams channel state."""

from __future__ import annotations

import json
from typing import Any

CONVERSATION_REFS_KEY = "conversation_refs"
PENDING_FILE_UPLOADS_KEY = "pending_file_uploads"
KNOWN_USERS_KEY = "known_users"


def get_conversation_refs(api) -> dict[str, dict[str, Any]]:
    data = _load_json(api, CONVERSATION_REFS_KEY, {})
    return _dict_dict(data)


def get_conversation_ref(api, conversation_id: str) -> dict[str, Any] | None:
    refs = get_conversation_refs(api)
    ref = refs.get(str(conversation_id))
    return dict(ref) if isinstance(ref, dict) else None


def upsert_conversation_ref(api, ref: dict[str, Any], *, limit: int = 200) -> dict[str, Any]:
    conversation_id = str(ref.get("conversation_id") or "")
    if not conversation_id:
        return {}
    refs = get_conversation_refs(api)
    stored = _display_safe_ref(ref)
    refs[conversation_id] = stored
    while len(refs) > limit:
        oldest = min(refs, key=lambda key: str(refs[key].get("last_seen_at") or ""))
        refs.pop(oldest, None)
    _save_json(api, CONVERSATION_REFS_KEY, refs)
    return stored


def first_personal_conversation_ref(api, approved_user_ids: set[str] | None = None) -> dict[str, Any] | None:
    refs = get_conversation_refs(api)
    approved = approved_user_ids or set()
    candidates = []
    for ref in refs.values():
        if ref.get("conversation_type") != "dm":
            continue
        if approved and str(ref.get("user_id") or "") not in approved:
            continue
        candidates.append(ref)
    if not candidates:
        return None
    candidates.sort(key=lambda item: str(item.get("last_seen_at") or ""), reverse=True)
    return dict(candidates[0])


def upsert_known_user(api, user_id: str, metadata: dict[str, Any], *, limit: int = 500) -> None:
    user_id = str(user_id or "")
    if not user_id:
        return
    users = _dict_dict(_load_json(api, KNOWN_USERS_KEY, {}))
    users[user_id] = {
        "user_id": user_id,
        "display_name": str(metadata.get("display_name") or ""),
        "aad_object_id": str(metadata.get("aad_object_id") or ""),
        "tenant_id": str(metadata.get("tenant_id") or ""),
        "last_seen_at": str(metadata.get("last_seen_at") or ""),
    }
    while len(users) > limit:
        oldest = min(users, key=lambda key: str(users[key].get("last_seen_at") or ""))
        users.pop(oldest, None)
    _save_json(api, KNOWN_USERS_KEY, users)


def put_pending_file_upload(api, file_id: str, record: dict[str, Any]) -> None:
    file_id = str(file_id or "")
    if not file_id:
        return
    pending = _dict_dict(_load_json(api, PENDING_FILE_UPLOADS_KEY, {}))
    pending[file_id] = {
        "file_id": file_id,
        "conversation_id": str(record.get("conversation_id") or ""),
        "file_path": str(record.get("file_path") or ""),
        "caption": str(record.get("caption") or ""),
    }
    _save_json(api, PENDING_FILE_UPLOADS_KEY, pending)


def pop_pending_file_upload(api, file_id: str) -> dict[str, Any] | None:
    file_id = str(file_id or "")
    pending = _dict_dict(_load_json(api, PENDING_FILE_UPLOADS_KEY, {}))
    record = pending.pop(file_id, None)
    _save_json(api, PENDING_FILE_UPLOADS_KEY, pending)
    return dict(record) if isinstance(record, dict) else None


def _load_json(api, key: str, fallback: Any) -> Any:
    raw = api.get_config(key, fallback)
    if isinstance(raw, (dict, list)):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def _save_json(api, key: str, value: Any) -> None:
    api.set_config(key, json.dumps(value, sort_keys=True))


def _dict_dict(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    return {str(key): dict(item) for key, item in value.items() if isinstance(item, dict)}


def _display_safe_ref(ref: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "conversation_id",
        "service_url",
        "conversation_type",
        "tenant_id",
        "bot_id",
        "user_id",
        "aad_object_id",
        "team_id",
        "channel_id",
        "display_name",
        "last_seen_at",
    }
    return {key: str(ref.get(key) or "") for key in sorted(allowed)}
