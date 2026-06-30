"""Subscribe to and read RSS/Atom feeds from Row-Bot."""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from plugins.api import PluginTool

_REQUEST_TIMEOUT = 10
_USER_AGENT = "Row-Bot-RSS-Reader-Plugin/1.0"


class FeedResult:
    def __init__(
        self,
        *,
        feed: dict[str, Any] | None = None,
        entries: list[dict[str, Any]] | None = None,
        bozo: bool = False,
        bozo_exception: str = "",
    ) -> None:
        self.feed = feed or {}
        self.entries = entries or []
        self.bozo = bozo
        self.bozo_exception = bozo_exception


def _get_feeds(api) -> list[dict[str, str]]:
    raw = api.get_config("feeds", "[]")
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, dict)]
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [dict(item) for item in parsed if isinstance(item, dict)]


def _save_feeds(api, feeds: list[dict[str, str]]) -> None:
    api.set_config("feeds", json.dumps(feeds))


def _find_feed(feeds: list[dict[str, str]], identifier: str) -> dict[str, str] | None:
    needle = (identifier or "").strip().lower()
    for feed in feeds:
        if str(feed.get("url", "")).lower() == needle:
            return feed
        if str(feed.get("name", "")).lower() == needle:
            return feed
    return None


def _fetch_url(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
        return resp.read()


def _parse_feed(url: str) -> FeedResult:
    raw = _fetch_url(url)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        return FeedResult(bozo=True, bozo_exception=str(exc))

    root_name = _local_name(root.tag).lower()
    if root_name in {"rss", "rdf"}:
        return _parse_rss(root)
    if root_name == "feed":
        return _parse_atom(root)
    return FeedResult(bozo=True, bozo_exception=f"Unsupported feed root: {root_name}")


def _parse_rss(root: ET.Element) -> FeedResult:
    channel = _first_child(root, "channel")
    if channel is None:
        channel = root
    feed_title = _child_text(channel, "title")
    item_nodes = _children(channel, "item")
    if not item_nodes:
        item_nodes = _children(root, "item")

    entries = []
    for item in item_nodes:
        date_text = _child_text(item, "pubdate", "updated", "published", "date")
        entries.append({
            "title": _child_text(item, "title") or "Untitled",
            "link": _child_text(item, "link") or _child_text(item, "guid"),
            "summary": _child_text(item, "description", "summary", "content", "encoded"),
            "published": _parse_datetime(date_text),
        })
    return FeedResult(feed={"title": feed_title}, entries=entries)


def _parse_atom(root: ET.Element) -> FeedResult:
    feed_title = _child_text(root, "title")
    entries = []
    for entry in _children(root, "entry"):
        date_text = _child_text(entry, "updated", "published")
        entries.append({
            "title": _child_text(entry, "title") or "Untitled",
            "link": _atom_link(entry),
            "summary": _child_text(entry, "summary", "content"),
            "published": _parse_datetime(date_text),
        })
    return FeedResult(feed={"title": feed_title}, entries=entries)


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _children(node: ET.Element, name: str) -> list[ET.Element]:
    wanted = name.lower()
    return [child for child in list(node) if _local_name(child.tag).lower() == wanted]


def _first_child(node: ET.Element, name: str) -> ET.Element | None:
    matches = _children(node, name)
    return matches[0] if matches else None


def _child_text(node: ET.Element, *names: str) -> str:
    wanted = {name.lower() for name in names}
    for child in list(node):
        if _local_name(child.tag).lower() in wanted:
            text = "".join(child.itertext())
            return _clean_text(text)
    return ""


def _atom_link(entry: ET.Element) -> str:
    fallback = ""
    for child in list(entry):
        if _local_name(child.tag).lower() != "link":
            continue
        href = child.attrib.get("href", "").strip()
        rel = child.attrib.get("rel", "alternate").strip().lower()
        text = _clean_text("".join(child.itertext()))
        candidate = href or text
        if not fallback:
            fallback = candidate
        if candidate and rel in {"", "alternate"}:
            return candidate
    return fallback


def _parse_datetime(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError, OverflowError):
        pass
    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _entry_date(entry: dict[str, Any]) -> datetime:
    published = entry.get("published")
    if isinstance(published, datetime):
        return published
    if isinstance(published, str):
        parsed = _parse_datetime(published)
        if parsed:
            return parsed
    return datetime.now(timezone.utc)


def _relative_time(dt: datetime) -> str:
    now = datetime.now(timezone.utc)
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


def _clean_text(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", "", text or "")
    cleaned = html.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _truncate(text: str, length: int = 200) -> str:
    text = _clean_text(text)
    if len(text) <= length:
        return text
    return text[: length - 3].rstrip() + "..."


def _format_entry(entry: dict[str, Any], index: int, feed_name: str = "") -> str:
    title = entry.get("title") or "Untitled"
    link = entry.get("link") or ""
    summary = _truncate(str(entry.get("summary") or ""))
    time_str = _relative_time(_entry_date(entry))
    source = f" - Source: {feed_name}" if feed_name else ""

    lines = [f"[{index}] **{title}**"]
    if link:
        lines.append(f"   Link: {link}")
    if summary:
        lines.append(f"   {summary}")
    lines.append(f"   {time_str}{source}")
    return "\n".join(lines)


def _add_feed(api, url: str, name: str) -> str:
    url = (url or "").strip()
    name = (name or "").strip()
    if not url:
        return "Error: Please provide a feed URL. Usage: add_feed <url> [name]"
    if not re.match(r"https?://", url, re.IGNORECASE):
        return f"Error: Invalid URL. Feed URLs must start with http:// or https://. Got: {url}"

    feeds = _get_feeds(api)
    if _find_feed(feeds, url):
        return f"Already subscribed to: {url}"

    try:
        result = _parse_feed(url)
    except Exception as exc:
        return f"Error fetching feed: {exc}"

    if result.bozo and not result.entries:
        return f"Error: Could not parse feed at {url} - {result.bozo_exception or 'unknown error'}"

    feed_title = str(result.feed.get("title") or "")
    display_name = name or feed_title or url.rstrip("/").rsplit("/", 1)[-1] or url
    feeds.append({"url": url, "name": display_name})
    _save_feeds(api, feeds)

    return (
        f"Subscribed to **{display_name}**\n"
        f"   Link: {url}\n"
        f"   {len(result.entries)} entries available"
    )


def _remove_feed(api, identifier: str) -> str:
    identifier = (identifier or "").strip()
    if not identifier:
        return "Error: Please specify a feed URL or name. Usage: remove_feed <url|name>"

    feeds = _get_feeds(api)
    match = _find_feed(feeds, identifier)
    if not match:
        return f"No feed found matching: {identifier}"

    remaining = [feed for feed in feeds if feed.get("url") != match.get("url")]
    _save_feeds(api, remaining)
    return f"Unsubscribed from **{match.get('name', '')}** ({match.get('url', '')})"


def _list_feeds(api) -> str:
    feeds = _get_feeds(api)
    if not feeds:
        return "No feeds subscribed yet.\nUse `add_feed <url> [name]` to subscribe to a feed."

    label = "feed" if len(feeds) == 1 else "feeds"
    parts = [f"**{len(feeds)} subscribed {label}:**\n"]
    for i, feed in enumerate(feeds, 1):
        parts.append(f"[{i}] **{feed.get('name', '')}**\n   Link: {feed.get('url', '')}")
    return "\n\n".join(parts)


def _fetch_feed(api, identifier: str, count: int) -> str:
    identifier = (identifier or "").strip()
    if not identifier:
        return "Error: Please specify a feed URL or name. Usage: fetch <url|name> [count]"

    feeds = _get_feeds(api)
    match = _find_feed(feeds, identifier)
    url = str(match.get("url")) if match else identifier
    feed_name = str(match.get("name")) if match else ""

    if not re.match(r"https?://", url, re.IGNORECASE):
        return f"No feed found matching: {identifier}"

    try:
        result = _parse_feed(url)
    except Exception as exc:
        return f"Error fetching feed: {exc}"

    if result.bozo and not result.entries:
        return f"Error: Could not parse feed at {url} - {result.bozo_exception or 'unknown error'}"
    if not result.entries:
        return f"No entries found in feed: {url}"

    if not feed_name:
        feed_name = str(result.feed.get("title") or url)

    entries = sorted(result.entries, key=_entry_date, reverse=True)[:count]
    parts = [f"**{feed_name}** - {len(entries)} latest entries:\n"]
    for i, entry in enumerate(entries, 1):
        parts.append(_format_entry(entry, i))
    return "\n\n".join(parts)


def _fetch_all(api, count: int) -> str:
    feeds = _get_feeds(api)
    if not feeds:
        return "No feeds subscribed yet.\nUse `add_feed <url> [name]` to subscribe to a feed."

    all_entries: list[tuple[dict[str, Any], str]] = []
    errors: list[str] = []
    for feed in feeds:
        name = str(feed.get("name") or feed.get("url") or "Unnamed feed")
        url = str(feed.get("url") or "")
        try:
            result = _parse_feed(url)
            if result.bozo and not result.entries:
                errors.append(f"{name}: {result.bozo_exception or 'could not parse feed'}")
                continue
            for entry in result.entries:
                all_entries.append((entry, name))
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    if not all_entries and errors:
        return "Could not fetch any feeds:\n" + "\n".join(errors)
    if not all_entries:
        return "No entries found across any subscribed feed."

    all_entries.sort(key=lambda pair: _entry_date(pair[0]), reverse=True)
    top = all_entries[:count]
    parts = [f"**Latest across {len(feeds)} feeds** - {len(top)} entries:\n"]
    for i, (entry, feed_name) in enumerate(top, 1):
        parts.append(_format_entry(entry, i, feed_name=feed_name))
    if errors:
        parts.append("\n---\n" + "\n".join(errors))
    return "\n\n".join(parts)


def _parse_int(value: str, default: int) -> int:
    value = (value or "").strip()
    if value.isdigit():
        return max(1, min(int(value), 30))
    return default


def _parse_query(query: str, default_count: int) -> tuple[str, dict[str, Any]]:
    query = (query or "").strip()
    if not query:
        return "list_feeds", {}

    parts = query.split(None, 1)
    action = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""

    if action == "add_feed":
        tokens = rest.split(None, 1)
        url = tokens[0] if tokens else ""
        name = tokens[1] if len(tokens) > 1 else ""
        return "add_feed", {"url": url, "name": name}
    if action == "remove_feed":
        return "remove_feed", {"identifier": rest}
    if action in {"list_feeds", "list"}:
        return "list_feeds", {}
    if action == "fetch":
        if not rest:
            return "error", {"message": "Please specify a feed. Usage: fetch <url|name> [count]"}
        tokens = rest.rsplit(None, 1)
        if len(tokens) == 2 and tokens[1].isdigit():
            return "fetch", {"identifier": tokens[0], "count": _parse_int(tokens[1], default_count)}
        return "fetch", {"identifier": rest, "count": default_count}
    if action == "fetch_all":
        return "fetch_all", {"count": _parse_int(rest, default_count)}
    if re.match(r"https?://", query, re.IGNORECASE):
        return "fetch", {"identifier": query, "count": default_count}
    return "error", {
        "message": (
            f"Unknown command: {action}\n"
            "Available commands: add_feed, remove_feed, list_feeds, fetch, fetch_all"
        )
    }


class RSSReaderTool(PluginTool):
    @property
    def name(self) -> str:
        return "rss_reader"

    @property
    def display_name(self) -> str:
        return "RSS Reader"

    @property
    def description(self) -> str:
        return (
            "Manage RSS/Atom feed subscriptions and fetch latest entries. "
            "Commands: add_feed <url> [name], remove_feed <url|name>, "
            "list_feeds, fetch <url|name> [count], fetch_all [count]."
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
            if action == "add_feed":
                return _add_feed(self.plugin_api, params["url"], params["name"])
            if action == "remove_feed":
                return _remove_feed(self.plugin_api, params["identifier"])
            if action == "list_feeds":
                return _list_feeds(self.plugin_api)
            if action == "fetch":
                return _fetch_feed(self.plugin_api, params["identifier"], params["count"])
            if action == "fetch_all":
                return _fetch_all(self.plugin_api, params["count"])
            if action == "error":
                return params["message"]
            return f"Unknown action: {action}"
        except urllib.error.URLError as exc:
            return f"Network error fetching feed: {exc}"
        except Exception as exc:
            return f"Error: {exc}"


def register(api):
    api.register_tool(RSSReaderTool(api))
