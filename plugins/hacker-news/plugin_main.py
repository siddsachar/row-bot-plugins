"""Browse and search Hacker News from Row-Bot."""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from plugins.api import PluginTool

_HN_BASE = "https://hacker-news.firebaseio.com/v0"
_ALGOLIA_BASE = "https://hn.algolia.com/api/v1"
_REQUEST_TIMEOUT = 10
_USER_AGENT = "Row-Bot-Hacker-News-Plugin/1.0"


def _fetch_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _relative_time(unix_ts: int | None) -> str:
    if not unix_ts:
        return ""
    now = datetime.now(timezone.utc)
    dt = datetime.fromtimestamp(int(unix_ts), tz=timezone.utc)
    seconds = int((now - dt).total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 30:
        return f"{days}d ago"
    return f"{days // 30}mo ago"


def _strip_html(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", "", text or "")
    cleaned = html.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _fetch_item(item_id: int) -> dict[str, Any] | None:
    try:
        data = _fetch_json(f"{_HN_BASE}/item/{int(item_id)}.json")
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _format_story(item: dict[str, Any], index: int | None = None) -> str:
    title = item.get("title") or "Untitled"
    url = item.get("url") or ""
    score = item.get("score") or 0
    by = item.get("by") or "unknown"
    time_str = _relative_time(item.get("time"))
    descendants = item.get("descendants") or 0
    item_id = item.get("id") or ""
    hn_link = f"https://news.ycombinator.com/item?id={item_id}"

    prefix = f"[{index}] " if index is not None else ""
    lines = [f"{prefix}**{title}**"]
    if url:
        lines.append(f"   Link: {url}")
    lines.append(f"   {score} points - {by} - {time_str} - {descendants} comments")
    lines.append(f"   Discussion: {hn_link}")
    return "\n".join(lines)


def _fetch_stories(endpoint: str, count: int) -> str:
    story_ids = _fetch_json(f"{_HN_BASE}/{endpoint}.json")
    if not isinstance(story_ids, list):
        return "No stories found."

    stories: list[dict[str, Any]] = []
    for sid in story_ids[:count]:
        item = _fetch_item(int(sid))
        if item and item.get("type") == "story":
            stories.append(item)

    if not stories:
        return "No stories found."
    return "\n\n".join(_format_story(story, index=i) for i, story in enumerate(stories, 1))


def _search_hn(query: str, count: int) -> str:
    query = (query or "").strip()
    if not query:
        return "Please provide a search query. Usage: search <query>"

    params = urllib.parse.urlencode({
        "query": query,
        "tags": "story",
        "hitsPerPage": count,
    })
    data = _fetch_json(f"{_ALGOLIA_BASE}/search?{params}")
    hits = data.get("hits", []) if isinstance(data, dict) else []
    if not hits:
        return f"No Hacker News results found for: {query}"

    parts = []
    for i, hit in enumerate(hits, 1):
        title = hit.get("title") or "Untitled"
        link = hit.get("url") or ""
        points = hit.get("points") or 0
        author = hit.get("author") or "unknown"
        num_comments = hit.get("num_comments") or 0
        time_str = _relative_time(hit.get("created_at_i"))
        object_id = hit.get("objectID") or ""
        hn_link = f"https://news.ycombinator.com/item?id={object_id}"

        lines = [f"[{i}] **{title}**"]
        if link:
            lines.append(f"   Link: {link}")
        lines.append(f"   {points} points - {author} - {time_str} - {num_comments} comments")
        lines.append(f"   Discussion: {hn_link}")
        parts.append("\n".join(lines))

    return "\n\n".join(parts)


def _story_detail(story_id: int, comment_count: int = 5) -> str:
    item = _fetch_item(story_id)
    if not item:
        return f"Could not find story with ID {story_id}."
    if item.get("type") != "story":
        return f"Item {story_id} is a {item.get('type', 'unknown')}, not a story."

    result = _format_story(item)
    text = _strip_html(str(item.get("text") or ""))
    if text:
        result += f"\n\nPost text:\n{text}"

    comment_ids = list(item.get("kids") or [])[:comment_count]
    if comment_ids:
        result += f"\n\nTop {len(comment_ids)} comments:\n"
        for cid in comment_ids:
            comment = _fetch_item(int(cid))
            if not comment or not comment.get("text"):
                continue
            body = _strip_html(str(comment.get("text") or ""))
            if len(body) > 500:
                body = body[:497].rstrip() + "..."
            by = comment.get("by") or "unknown"
            time_str = _relative_time(comment.get("time"))
            result += f"\n---\n**{by}** - {time_str}\n{body}\n"
    return result


def _parse_int(value: str, default: int) -> int:
    value = (value or "").strip()
    if value.isdigit():
        return max(1, min(int(value), 30))
    return default


def _parse_query(query: str, default_count: int) -> tuple[str, dict[str, Any]]:
    query = (query or "").strip()
    if not query:
        return "top_stories", {"count": default_count}

    parts = query.split(None, 1)
    action = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""

    if action == "top_stories":
        return "top_stories", {"count": _parse_int(rest, default_count)}
    if action == "new_stories":
        return "new_stories", {"count": _parse_int(rest, default_count)}
    if action == "search":
        if not rest:
            return "error", {"message": "Please provide a search query. Usage: search <query>"}
        tokens = rest.rsplit(None, 1)
        if len(tokens) == 2 and tokens[1].isdigit():
            return "search", {"query": tokens[0], "count": _parse_int(tokens[1], default_count)}
        return "search", {"query": rest, "count": default_count}
    if action == "story_detail":
        if not rest:
            return "error", {"message": "Please provide a story ID. Usage: story_detail <id>"}
        tokens = rest.split()
        try:
            story_id = int(tokens[0])
        except (TypeError, ValueError):
            return "error", {"message": f"Invalid story ID: {tokens[0]}"}
        if story_id <= 0:
            return "error", {"message": f"Invalid story ID: {tokens[0]}"}
        comment_count = 5
        for token in tokens[1:]:
            if token.startswith("comments:"):
                comment_count = _parse_int(token.split(":", 1)[1], 5)
        return "story_detail", {"story_id": story_id, "comment_count": comment_count}

    return "search", {"query": query, "count": default_count}


class HackerNewsTool(PluginTool):
    @property
    def name(self) -> str:
        return "hacker_news"

    @property
    def display_name(self) -> str:
        return "Hacker News"

    @property
    def description(self) -> str:
        return (
            "Browse and search Hacker News. Commands: top_stories [count], "
            "new_stories [count], search <query> [count], story_detail <id> "
            "[comments:N]. A bare query is treated as search."
        )

    def execute(self, query: str) -> str:
        default_count = self.plugin_api.get_config("default_count", 10)
        try:
            default_count = int(default_count)
        except (TypeError, ValueError):
            default_count = 10
        default_count = max(1, min(default_count, 30))

        try:
            action, params = _parse_query(query, default_count)
            if action == "top_stories":
                return _fetch_stories("topstories", params["count"])
            if action == "new_stories":
                return _fetch_stories("newstories", params["count"])
            if action == "search":
                return _search_hn(params["query"], params["count"])
            if action == "story_detail":
                return _story_detail(params["story_id"], params.get("comment_count", 5))
            if action == "error":
                return params["message"]
            return f"Unknown action: {action}"
        except urllib.error.URLError as exc:
            return f"Network error accessing Hacker News: {exc}"
        except Exception as exc:
            return f"Error fetching from Hacker News: {exc}"


def register(api):
    api.register_tool(HackerNewsTool(api))
