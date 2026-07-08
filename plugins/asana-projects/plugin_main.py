"""Browse Asana workspaces, projects, and tasks from Row-Bot.

Read tools (list / search / detail / blockers) are safe and run without
approval. The create tool writes a task to Asana and is declared destructive,
so Row-Bot's approval gate asks the user to confirm before it runs.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from typing import Any, Callable

from plugins.api import PluginTool

_API_BASE = "https://app.asana.com/api/1.0"
_REQUEST_TIMEOUT = 15
_USER_AGENT = "Row-Bot-Asana-Projects-Plugin/0.1"

_NO_TOKEN_MSG = (
    "Asana access token is not configured. Add an Asana Personal Access Token "
    "in Plugin Center before using this tool."
)

_NO_WORKSPACE_MSG = (
    "No workspace GID available. Set a Default workspace GID in Plugin Center, "
    "or pass one explicitly. Run 'list_workspaces' to find it."
)

# opt_fields requested per read, kept minimal and non-sensitive.
_PROJECT_FIELDS = "name,archived,current_status.text"
_TASK_LIST_FIELDS = "name,completed,due_on,assignee.name"
_TASK_DETAIL_FIELDS = (
    "name,notes,completed,completed_at,due_on,assignee.name,"
    "projects.name,permalink_url,num_subtasks"
)

_HELP_TEXT = (
    "Asana Projects (read). Commands:\n"
    "  list_workspaces [count]\n"
    "  list_projects [workspace_gid] [count]  - workspace_gid optional if a "
    "default workspace is set\n"
    "  list_tasks <project_gid> [count]\n"
    "  search_tasks <query> [count]           - searches the default workspace\n"
    "  task <task_gid>\n"
    "  blockers <project_gid>                 - summarize open tasks by due status\n"
    "A bare query without a command searches tasks in the default workspace."
)


# ── Small pure helpers ───────────────────────────────────────────────────────
def _parse_int(value: str, default: int) -> int:
    value = (value or "").strip()
    if value.isdigit():
        return max(1, min(int(value), 30))
    return default


def _split_trailing_count(text: str, default_count: int) -> tuple[str, int]:
    """Split a trailing integer count off a query string."""
    tokens = (text or "").rsplit(None, 1)
    if len(tokens) == 2 and tokens[1].isdigit():
        return tokens[0].strip(), _parse_int(tokens[1], default_count)
    return (text or "").strip(), default_count


def _is_gid(token: str) -> bool:
    """Asana GIDs are numeric strings."""
    return token.isdigit()


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _parse_due(due_on: Any) -> date | None:
    if not due_on or not isinstance(due_on, str):
        return None
    try:
        return date.fromisoformat(due_on[:10])
    except ValueError:
        return None


# ── Read: parsing ────────────────────────────────────────────────────────────
def _parse_query(query: str, default_count: int) -> tuple[str, dict[str, Any]]:
    query = (query or "").strip()
    if not query:
        return "help", {}

    parts = query.split(None, 1)
    action = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""

    if action == "list_workspaces":
        return "list_workspaces", {"count": _parse_int(rest, default_count) if rest else default_count}

    if action == "list_projects":
        text, count = _split_trailing_count(rest, default_count)
        first = text.split()[0] if text else ""
        workspace = first if _is_gid(first) else ""
        return "list_projects", {"workspace": workspace, "count": count}

    if action == "list_tasks":
        if not rest:
            return "error", {"message": "Please provide a project GID. Usage: list_tasks <project_gid>"}
        text, count = _split_trailing_count(rest, default_count)
        project = text.split()[0]
        if not _is_gid(project):
            return "error", {"message": f"Invalid project GID: {project}"}
        return "list_tasks", {"project": project, "count": count}

    if action == "search_tasks":
        if not rest:
            return "error", {"message": "Please provide a search query. Usage: search_tasks <query>"}
        text, count = _split_trailing_count(rest, default_count)
        return "search_tasks", {"query": text, "count": count}

    if action == "task":
        if not rest:
            return "error", {"message": "Please provide a task GID. Usage: task <task_gid>"}
        task_gid = rest.split()[0]
        if not _is_gid(task_gid):
            return "error", {"message": f"Invalid task GID: {task_gid}"}
        return "task", {"task": task_gid}

    if action == "blockers":
        if not rest:
            return "error", {"message": "Please provide a project GID. Usage: blockers <project_gid>"}
        project = rest.split()[0]
        if not _is_gid(project):
            return "error", {"message": f"Invalid project GID: {project}"}
        return "blockers", {"project": project}

    if action in ("help", "commands", "?"):
        return "help", {}

    # Bare query → search tasks in the default workspace.
    text, count = _split_trailing_count(query, default_count)
    return "search_tasks", {"query": text, "count": count}


# ── Read: formatting ─────────────────────────────────────────────────────────
def _format_workspace(ws: dict[str, Any], index: int | None = None) -> str:
    prefix = f"[{index}] " if index is not None else ""
    name = (ws.get("name") or "").strip() or "Unnamed workspace"
    return f"{prefix}**{name}**  (gid: {ws.get('gid', '')})"


def _format_project(project: dict[str, Any], index: int | None = None) -> str:
    prefix = f"[{index}] " if index is not None else ""
    name = (project.get("name") or "").strip() or "Untitled project"
    lines = [f"{prefix}**{name}**  (gid: {project.get('gid', '')})"]
    if project.get("archived"):
        lines.append("   (archived)")
    status = project.get("current_status") or {}
    if isinstance(status, dict) and status.get("text"):
        lines.append(f"   Status: {status['text']}")
    return "\n".join(lines)


def _format_task(task: dict[str, Any], index: int | None = None) -> str:
    prefix = f"[{index}] " if index is not None else ""
    name = (task.get("name") or "").strip() or "Untitled task"
    mark = "x" if task.get("completed") else " "
    lines = [f"{prefix}[{mark}] **{name}**  (gid: {task.get('gid', '')})"]
    assignee = task.get("assignee") or {}
    if isinstance(assignee, dict) and assignee.get("name"):
        lines.append(f"   Assignee: {assignee['name']}")
    if task.get("due_on"):
        lines.append(f"   Due: {task['due_on']}")
    return "\n".join(lines)


def _format_task_detail(task: dict[str, Any]) -> str:
    lines = [_format_task(task)]
    notes = (task.get("notes") or "").strip()
    if notes:
        if len(notes) > 800:
            notes = notes[:797].rstrip() + "..."
        lines.append(f"\nNotes:\n{notes}")
    projects = task.get("projects") or []
    names = [p.get("name") for p in projects if isinstance(p, dict) and p.get("name")]
    if names:
        lines.append("Projects: " + ", ".join(names))
    if task.get("num_subtasks"):
        lines.append(f"Subtasks: {task['num_subtasks']}")
    if task.get("permalink_url"):
        lines.append(f"Link: {task['permalink_url']}")
    return "\n".join(lines)


def _summarize_blockers(tasks: list[dict[str, Any]]) -> str:
    today = _today()
    overdue: list[dict] = []
    due_soon: list[dict] = []
    no_due: list[dict] = []
    unassigned = 0
    for task in tasks:
        if task.get("completed"):
            continue
        assignee = task.get("assignee") or {}
        if not (isinstance(assignee, dict) and assignee.get("name")):
            unassigned += 1
        due_date = _parse_due(task.get("due_on"))
        if due_date is None:
            no_due.append(task)
        elif due_date < today:
            overdue.append(task)
        else:
            due_soon.append(task)

    open_count = len(overdue) + len(due_soon) + len(no_due)
    lines = ["**Blockers summary**"]
    lines.append(f"   Open tasks: {open_count}")
    lines.append(f"   Overdue: {len(overdue)}")
    lines.append(f"   Upcoming (has due date): {len(due_soon)}")
    lines.append(f"   No due date: {len(no_due)}")
    lines.append(f"   Unassigned: {unassigned}")
    if overdue:
        lines.append("\nOverdue tasks:")
        lines.append("\n".join(_format_task(t, index=i) for i, t in enumerate(overdue, 1)))
    return "\n".join(lines)


# ── Network layer ────────────────────────────────────────────────────────────
def _api_request(
    method: str,
    path: str,
    token: str,
    *,
    body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    url = _API_BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": _USER_AGENT,
        "Accept": "application/json",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8")
    if not raw:
        return {}
    return json.loads(raw)


def _data_list(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    return [r for r in payload.get("data", []) if isinstance(r, dict)]


def _list_workspaces(count: int, token: str) -> list[dict[str, Any]]:
    payload = _api_request("GET", "/workspaces", token, params={"limit": count, "opt_fields": "name"})
    return _data_list(payload)


def _list_projects(workspace: str, count: int, token: str) -> list[dict[str, Any]]:
    params = {"workspace": workspace, "limit": count, "opt_fields": _PROJECT_FIELDS}
    return _data_list(_api_request("GET", "/projects", token, params=params))


def _list_tasks(project: str, count: int, token: str) -> list[dict[str, Any]]:
    params = {"project": project, "limit": count, "opt_fields": _TASK_LIST_FIELDS}
    return _data_list(_api_request("GET", "/tasks", token, params=params))


def _project_open_tasks(project: str, token: str) -> list[dict[str, Any]]:
    """Fetch incomplete tasks for a project (for the blockers summary)."""
    params = {
        "project": project,
        "completed_since": "now",
        "limit": 100,
        "opt_fields": _TASK_LIST_FIELDS,
    }
    return _data_list(_api_request("GET", "/tasks", token, params=params))


def _search_tasks(workspace: str, query: str, count: int, token: str) -> list[dict[str, Any]]:
    """Task typeahead search (available on all Asana tiers)."""
    params = {
        "resource_type": "task",
        "query": query,
        "count": count,
        "opt_fields": "name,completed,due_on,assignee.name",
    }
    payload = _api_request("GET", f"/workspaces/{workspace}/typeahead", token, params=params)
    return _data_list(payload)


def _get_task(task_gid: str, token: str) -> dict[str, Any] | None:
    payload = _api_request("GET", f"/tasks/{task_gid}", token, params={"opt_fields": _TASK_DETAIL_FIELDS})
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


def _create_task(project: str, name: str, token: str) -> dict[str, Any] | None:
    body = {"data": {"name": name, "projects": [project]}}
    payload = _api_request("POST", "/tasks", token, body=body)
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


# ── Read: runners ────────────────────────────────────────────────────────────
def _run_list_workspaces(count: int, token: str) -> str:
    workspaces = _list_workspaces(count, token)
    if not workspaces:
        return "No workspaces found for this token."
    body = "\n".join(_format_workspace(w, index=i) for i, w in enumerate(workspaces, 1))
    return f"Workspaces ({len(workspaces)}):\n\n{body}"


def _run_list_projects(workspace: str, count: int, token: str) -> str:
    projects = _list_projects(workspace, count, token)
    if not projects:
        return f"No projects found in workspace {workspace}."
    body = "\n\n".join(_format_project(p, index=i) for i, p in enumerate(projects, 1))
    return f"Projects in workspace {workspace} ({len(projects)}):\n\n{body}"


def _run_list_tasks(project: str, count: int, token: str) -> str:
    tasks = _list_tasks(project, count, token)
    if not tasks:
        return f"No tasks found in project {project}."
    body = "\n\n".join(_format_task(t, index=i) for i, t in enumerate(tasks, 1))
    return f"Tasks in project {project} ({len(tasks)}):\n\n{body}"


def _run_search_tasks(workspace: str, query: str, count: int, token: str) -> str:
    if not query:
        return "Please provide a search query."
    tasks = _search_tasks(workspace, query, count, token)
    if not tasks:
        return f"No tasks found for: {query}"
    body = "\n\n".join(_format_task(t, index=i) for i, t in enumerate(tasks, 1))
    return f"Found {len(tasks)} task(s) for '{query}':\n\n{body}"


def _run_task_detail(task_gid: str, token: str) -> str:
    task = _get_task(task_gid, token)
    if not task or not task.get("gid"):
        return f"Could not find task with GID {task_gid}."
    return _format_task_detail(task)


def _run_blockers(project: str, token: str) -> str:
    tasks = _project_open_tasks(project, token)
    if not tasks:
        return f"No open tasks in project {project}. Nothing is blocking."
    return _summarize_blockers(tasks)


# ── Write: parsing / runner ──────────────────────────────────────────────────
def _parse_create(query: str) -> tuple[str | None, str]:
    """Parse '<project_gid> <task name...>' into (project_gid, name)."""
    parts = (query or "").strip().split(None, 1)
    if len(parts) < 2:
        return None, ""
    project = parts[0]
    if not _is_gid(project):
        return None, ""
    return project, parts[1].strip()


def _run_create_task(project: str | None, name: str, token: str) -> str:
    if not project:
        return (
            "Usage: <project_gid> <task name>. The first token must be a numeric "
            "project GID, followed by the task name."
        )
    if not name:
        return "Please provide a task name. Usage: <project_gid> <task name>"
    task = _create_task(project, name, token)
    if not task or not task.get("gid"):
        return "Asana did not return a new task GID."
    return f"Created task '{name}' in project {project} (gid: {task['gid']})."


# ── Error mapping ────────────────────────────────────────────────────────────
def _format_http_error(exc: urllib.error.HTTPError) -> str:
    code = getattr(exc, "code", None)
    if code == 401:
        return "Asana rejected the token (401 Unauthorized). Check the Personal Access Token."
    if code == 402:
        return "This Asana feature requires a paid plan (402 Payment Required)."
    if code == 403:
        return (
            "Asana denied access (403 Forbidden). The token may not have access to that "
            "workspace or project."
        )
    if code == 404:
        return "Resource not found in Asana (404). Check the GID."
    if code == 429:
        return "Asana rate limit reached (429). Please wait a moment and try again."
    return f"Asana API error (HTTP {code})."


# ── Tools ────────────────────────────────────────────────────────────────────
class _AsanaTool(PluginTool):
    """Shared token handling and error wrapping for all Asana tools."""

    def _run_guarded(self, fn: Callable[[str], str]) -> str:
        token = self.plugin_api.get_secret("access_token")
        if not token:
            return _NO_TOKEN_MSG
        try:
            return fn(token)
        except urllib.error.HTTPError as exc:
            return _format_http_error(exc)
        except urllib.error.URLError as exc:
            return f"Network error accessing Asana: {exc.reason}"
        except Exception as exc:
            return f"Error accessing Asana: {exc}"

    def _default_count(self) -> int:
        raw = self.plugin_api.get_config("default_count", 10)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = 10
        return max(1, min(value, 30))

    def _default_workspace(self) -> str:
        return str(self.plugin_api.get_config("default_workspace", "") or "").strip()


class AsanaProjectsTool(_AsanaTool):
    @property
    def name(self) -> str:
        return "asana_projects"

    @property
    def display_name(self) -> str:
        return "Asana Projects"

    @property
    def description(self) -> str:
        return (
            "Read Asana workspaces, projects, and tasks (read-only, no approval needed). "
            "Commands: list_workspaces [count], list_projects [workspace_gid] [count], "
            "list_tasks <project_gid> [count], search_tasks <query> [count], task <task_gid>, "
            "blockers <project_gid>. A bare query searches tasks in the default workspace."
        )

    def execute(self, query: str) -> str:
        action, params = _parse_query(query, self._default_count())
        if action == "help":
            return _HELP_TEXT
        if action == "error":
            return params["message"]

        def _do(token: str) -> str:
            if action == "list_workspaces":
                return _run_list_workspaces(params["count"], token)
            if action == "list_projects":
                workspace = params["workspace"] or self._default_workspace()
                if not workspace:
                    return _NO_WORKSPACE_MSG
                return _run_list_projects(workspace, params["count"], token)
            if action == "list_tasks":
                return _run_list_tasks(params["project"], params["count"], token)
            if action == "search_tasks":
                workspace = self._default_workspace()
                if not workspace:
                    return _NO_WORKSPACE_MSG
                return _run_search_tasks(workspace, params["query"], params["count"], token)
            if action == "task":
                return _run_task_detail(params["task"], token)
            if action == "blockers":
                return _run_blockers(params["project"], token)
            return f"Unknown command: {action}"

        return self._run_guarded(_do)


class AsanaCreateTaskTool(_AsanaTool):
    @property
    def name(self) -> str:
        return "asana_create_task"

    @property
    def display_name(self) -> str:
        return "Asana Create Task"

    @property
    def description(self) -> str:
        return (
            "Create a task in an Asana project. Requires user approval before it runs. "
            "Usage: <project_gid> <task name>. "
            "Example: 12000045 Draft Q3 onboarding checklist."
        )

    @property
    def destructive_tool_names(self) -> set[str]:
        return {"asana_create_task"}

    def execute(self, query: str) -> str:
        project, name = _parse_create(query)
        return self._run_guarded(lambda token: _run_create_task(project, name, token))


def register(api):
    api.register_tool(AsanaProjectsTool(api))
    api.register_tool(AsanaCreateTaskTool(api))
