"""Opt-in personal long-term memory for Row-Bot, backed by Memcode."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from plugins.api import PluginTool

_DEFAULT_BASE_URL = "https://memory.memcode.in"
_REQUEST_TIMEOUT = 20
_USER_AGENT = "Row-Bot-Memcode-Memory-Plugin/0.1"
_NO_TOKEN_MSG = (
    "Memcode API key is not configured. Add a personal Memcode API key in "
    "Plugin Center before using this tool."
)


def _bounded_count(value: Any, default: int = 5) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, 25))


def _query_and_count(value: str, default: int) -> tuple[str, int]:
    text = (value or "").strip()
    parts = text.rsplit(None, 1)
    if len(parts) == 2 and parts[1].lower().startswith("count="):
        raw_count = parts[1].split("=", 1)[1]
        if raw_count.isdigit():
            return parts[0].strip(), _bounded_count(raw_count, default)
    return text, default


def _base_url(value: Any) -> str:
    candidate = str(value or _DEFAULT_BASE_URL).strip().rstrip("/")
    parsed = urllib.parse.urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Memcode API URL must be an http or https URL")
    return candidate


def _api_request(
    method: str,
    base_url: str,
    path: str,
    token: str,
    *,
    body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{_base_url(base_url)}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Memcode returned a non-object response")
    if payload.get("status") == "error":
        raise ValueError(str(payload.get("error") or "Memcode request failed"))
    data_payload = payload.get("data", payload)
    return data_payload if isinstance(data_payload, dict) else {"value": data_payload}


def _source_lines(items: list[Any], limit: int) -> list[str]:
    lines: list[str] = []
    for index, raw in enumerate(items[:limit], 1):
        if not isinstance(raw, dict):
            continue
        content = " ".join(str(raw.get("content") or "").split())
        if len(content) > 500:
            content = content[:497] + "..."
        domain = str(raw.get("domain") or "memory")
        score = raw.get("score")
        score_text = f", score {score:.3f}" if isinstance(score, (int, float)) else ""
        lines.append(f"[{index}] {domain}{score_text}: {content or '(no text)' }")
    return lines


def _http_error_message(exc: urllib.error.HTTPError) -> str:
    if exc.code in {401, 403}:
        return "Memcode rejected the credential. Check the API key configured in Plugin Center."
    if exc.code == 404:
        return "The requested Memcode resource was not found."
    if exc.code == 429:
        return "Memcode rate limit reached. Wait a moment and try again."
    if exc.code >= 500:
        return f"Memcode is temporarily unavailable (HTTP {exc.code})."
    return f"Memcode request failed (HTTP {exc.code})."


class _MemcodeTool(PluginTool):
    def _default_count(self) -> int:
        return _bounded_count(self.plugin_api.get_config("default_count", 5))

    def _run(self, operation: Callable[[str, str], str]) -> str:
        token = self.plugin_api.get_secret("api_key")
        if not token:
            return _NO_TOKEN_MSG
        base_url = self.plugin_api.get_config("base_url", _DEFAULT_BASE_URL)
        try:
            return operation(str(token), str(base_url))
        except urllib.error.HTTPError as exc:
            return _http_error_message(exc)
        except urllib.error.URLError as exc:
            return f"Network error accessing Memcode: {exc.reason}"
        except (TypeError, ValueError) as exc:
            return f"Memcode response error: {exc}"
        except Exception as exc:
            return f"Error accessing Memcode: {exc}"


class MemcodeSearchTool(_MemcodeTool):
    @property
    def name(self) -> str:
        return "memcode_search"

    @property
    def display_name(self) -> str:
        return "Search Memcode"

    @property
    def description(self) -> str:
        return "Search the authenticated user's memories. Usage: <query> [count=N]. Read-only."

    def execute(self, query: str) -> str:
        text, count = _query_and_count(query, self._default_count())
        if not text:
            return "Please provide a memory search query."

        def operation(token: str, base_url: str) -> str:
            data = _api_request(
                "POST",
                base_url,
                "/v2/memory/search",
                token,
                body={
                    "query": text,
                    "mode": "memories",
                    "top_k": count,
                    "include_original_chunks": False,
                    "search_mode": "default",
                    "minimum_score": 0.0,
                },
            )
            items = data.get("memory_results", data.get("results", []))
            lines = _source_lines(items if isinstance(items, list) else [], count)
            return "No matching memories found." if not lines else "Memcode results:\n" + "\n".join(lines)

        return self._run(operation)


class MemcodeRetrieveTool(_MemcodeTool):
    @property
    def name(self) -> str:
        return "memcode_retrieve"

    @property
    def display_name(self) -> str:
        return "Ask Memcode"

    @property
    def description(self) -> str:
        return (
            "Answer from the authenticated user's memories. Usage: <question> [count=N]. "
            "May update Memcode Recall Bond relationships and requires approval."
        )

    @property
    def destructive_tool_names(self) -> set[str]:
        return {"memcode_retrieve"}

    def execute(self, query: str) -> str:
        text, count = _query_and_count(query, self._default_count())
        if not text:
            return "Please provide a question for Memcode."

        def operation(token: str, base_url: str) -> str:
            data = _api_request(
                "POST", base_url, "/v2/memory/retrieve", token, body={"query": text, "top_k": count}
            )
            answer = " ".join(str(data.get("answer") or "").split())
            sources = data.get("sources", [])
            lines = _source_lines(sources if isinstance(sources, list) else [], count)
            output = answer or "Memcode did not return an answer."
            if lines:
                output += "\n\nSources:\n" + "\n".join(lines)
            return output

        return self._run(operation)


class MemcodeListTool(_MemcodeTool):
    @property
    def name(self) -> str:
        return "memcode_list"

    @property
    def display_name(self) -> str:
        return "List Memcode Memories"

    @property
    def description(self) -> str:
        return "List the authenticated user's recent memories. Usage: [count] [offset]. Read-only."

    def execute(self, query: str) -> str:
        parts = (query or "").split()
        count = _bounded_count(parts[0] if parts else self._default_count(), self._default_count())
        try:
            offset = max(0, int(parts[1])) if len(parts) > 1 else 0
        except ValueError:
            return "Offset must be a non-negative integer."

        def operation(token: str, base_url: str) -> str:
            data = _api_request(
                "GET", base_url, "/v2/memory", token, params={"limit": count, "offset": offset}
            )
            items = data.get("items", [])
            lines = _source_lines(items if isinstance(items, list) else [], count)
            if not lines:
                return "No memories found on this page."
            total = data.get("total_memories")
            heading = f"Memcode memories (offset {offset}"
            heading += f", total {total})" if isinstance(total, int) else ")"
            return heading + ":\n" + "\n".join(lines)

        return self._run(operation)


class MemcodeRememberTool(_MemcodeTool):
    @property
    def name(self) -> str:
        return "memcode_remember"

    @property
    def display_name(self) -> str:
        return "Remember with Memcode"

    @property
    def description(self) -> str:
        return (
            "Send exactly the supplied text to Memcode for memory processing. Memcode may "
            "add, update, delete, or ignore derived memories. This write requires approval."
        )

    @property
    def destructive_tool_names(self) -> set[str]:
        return {"memcode_remember"}

    def execute(self, query: str) -> str:
        text = (query or "").strip()
        if not text:
            return "Please provide the exact text to remember."
        if len(text) > 10_000:
            return "Memory text must be 10,000 characters or fewer."

        def operation(token: str, base_url: str) -> str:
            data = _api_request(
                "POST",
                base_url,
                "/v2/memory/ingest",
                token,
                body={"user_query": text, "effort_level": "low", "forget": False},
            )
            job_id = str(data.get("job_id") or "")
            status = str(data.get("status") or "queued")
            return (
                f"Memcode ingest accepted with status '{status}' and job id {job_id}. "
                "Use memcode_ingest_status to verify completion."
                if job_id
                else "Memcode accepted the ingest but did not return a job id."
            )

        return self._run(operation)


class MemcodeIngestStatusTool(_MemcodeTool):
    @property
    def name(self) -> str:
        return "memcode_ingest_status"

    @property
    def display_name(self) -> str:
        return "Check Memcode Ingest"

    @property
    def description(self) -> str:
        return "Check a Memcode ingest receipt. Usage: <job id>. Read-only."

    def execute(self, query: str) -> str:
        job_id = (query or "").strip()
        if not job_id:
            return "Please provide the Memcode ingest job id."

        def operation(token: str, base_url: str) -> str:
            encoded = urllib.parse.quote(job_id, safe="")
            data = _api_request(
                "GET", base_url, f"/v2/memory/ingest/{encoded}/status", token
            )
            status = str(data.get("status") or "unknown")
            progress = data.get("progress")
            suffix = f" Progress: {json.dumps(progress, sort_keys=True)}" if progress else ""
            error = data.get("error")
            if error:
                suffix += f" Error: {str(error)[:300]}"
            return f"Memcode job {job_id}: {status}.{suffix}".strip()

        return self._run(operation)


def register(api):
    api.register_tool(MemcodeSearchTool(api))
    api.register_tool(MemcodeRetrieveTool(api))
    api.register_tool(MemcodeListTool(api))
    api.register_tool(MemcodeRememberTool(api))
    api.register_tool(MemcodeIngestStatusTool(api))
