"""Adaptive Card builders for Microsoft Teams approvals."""

from __future__ import annotations

from typing import Any

ADAPTIVE_CARD_CONTENT_TYPE = "application/vnd.microsoft.card.adaptive"


def approval_attachment(interrupt_data: Any, config: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "contentType": ADAPTIVE_CARD_CONTENT_TYPE,
        "content": approval_card(interrupt_data, config or {}),
    }


def approval_card(interrupt_data: Any, config: dict[str, Any]) -> dict[str, Any]:
    payload = _approval_payload(interrupt_data, config)
    summary = _summary_text(interrupt_data, config)
    base_data = {
        "row_bot_action": "approval",
        "thread_id": payload["thread_id"],
        "interrupt_ids": payload["interrupt_ids"],
        "resume_token": payload["resume_token"],
    }
    return {
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            {
                "type": "TextBlock",
                "text": "Approval Required",
                "weight": "Bolder",
                "size": "Medium",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": summary,
                "wrap": True,
            },
        ],
        "actions": [
            {
                "type": "Action.Submit",
                "title": "Approve",
                "data": dict(base_data, approved=True),
            },
            {
                "type": "Action.Submit",
                "title": "Deny",
                "data": dict(base_data, approved=False),
            },
        ],
    }


def resolved_approval_attachment(status: str, source: str = "") -> dict[str, Any]:
    return {
        "contentType": ADAPTIVE_CARD_CONTENT_TYPE,
        "content": resolved_approval_card(status, source),
    }


def resolved_approval_card(status: str, source: str = "") -> dict[str, Any]:
    normalized = "approved" if str(status).lower() == "approved" else "denied"
    suffix = f" from {source}" if source else ""
    return {
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            {
                "type": "TextBlock",
                "text": f"Approval {normalized.title()}",
                "weight": "Bolder",
                "size": "Medium",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": f"This request was {normalized}{suffix}.",
                "wrap": True,
            },
        ],
    }


def _approval_payload(interrupt_data: Any, config: dict[str, Any]) -> dict[str, Any]:
    if isinstance(interrupt_data, dict):
        thread_id = str(interrupt_data.get("thread_id") or config.get("thread_id") or "")
        interrupt_ids = _list(interrupt_data.get("interrupt_ids") or config.get("interrupt_ids"))
        resume_token = str(interrupt_data.get("resume_token") or config.get("resume_token") or "")
    else:
        thread_id = str(config.get("thread_id") or "")
        interrupt_ids = _list(config.get("interrupt_ids"))
        resume_token = str(config.get("resume_token") or "")
    return {
        "thread_id": thread_id,
        "interrupt_ids": interrupt_ids,
        "resume_token": resume_token,
    }


def _summary_text(interrupt_data: Any, config: dict[str, Any]) -> str:
    for value in (
        config.get("summary") if isinstance(config, dict) else "",
        config.get("message") if isinstance(config, dict) else "",
        interrupt_data.get("summary") if isinstance(interrupt_data, dict) else "",
        interrupt_data.get("message") if isinstance(interrupt_data, dict) else "",
        interrupt_data.get("tool_name") if isinstance(interrupt_data, dict) else "",
    ):
        if value:
            return str(value)
    if interrupt_data:
        return str(interrupt_data)[:900]
    return "Row-Bot needs your approval to continue."


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value in (None, ""):
        return []
    return [str(value)]
