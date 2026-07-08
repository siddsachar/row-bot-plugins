# Asana Projects

Browse your Asana workspaces, projects, and tasks directly from Row-Bot, and
create tasks with approval.

## What It Does

**Read (safe, no approval):**
- List **workspaces** and **projects**.
- List and **search tasks**.
- View a single **task's detail** (notes, assignee, due date, link).
- **Summarize blockers** for a project: overdue / upcoming / no-due-date /
  unassigned counts, plus the overdue task list.

**Write (approval-gated — Row-Bot confirms before it runs):**
- **Create** a task inside a project.

## What It Does Not Do (Yet)

- No updating, completing, or deleting tasks.
- No comments, attachments, subtasks, custom fields, or section moves.
- No OAuth — authentication is a Personal Access Token only (OAuth is future
  work).
- Task search uses Asana **typeahead**, which matches on task names in one
  workspace; it is not a full-text search across every field.

## Approval Model

The read tool (`asana_projects`) runs without approval. The create tool
(`asana_create_task`) is declared **destructive**, so Row-Bot's approval gate
applies:

- In **approve** mode, Row-Bot pauses and asks the user to confirm before the
  task is created.
- In **block** mode, the create tool is hidden from the agent entirely.

The agent can never write to Asana without the user's explicit confirmation.

## Setup

You need an **Asana Personal Access Token (PAT)**.

1. In Asana, open **Settings → Apps → Developer apps → Personal access tokens**.
2. Create a token and copy it (you only see it once).
3. In Row-Bot Plugin Center, open the Asana Projects plugin and paste the token
   into **Asana Personal Access Token**.
4. Optional: run `list_workspaces`, copy your workspace GID, and paste it into
   **Default workspace GID** so `search_tasks` and `list_projects` work without
   passing a GID each time.
5. Run **Test**, then **Enable**.

The token authenticates as your Asana user and can access whatever workspaces,
projects, and tasks that user can. Use a token from an account with only the
access you want Row-Bot to have.

## Permissions

| Permission | Why |
| --- | --- |
| `network` | Calls the Asana REST API over HTTPS (`https://app.asana.com`). |
| `account` | Uses your Asana account's workspaces, projects, and tasks via your Personal Access Token. |

The MVP does not send messages or email, so `external_send` and `messaging` are
**not** requested.

## Settings And Secrets

| Field | Type | Required | Purpose |
| --- | --- | --- | --- |
| `default_count` | setting (number) | no | Results per list/search (1–30, default 10). |
| `default_workspace` | setting (text) | no | Workspace GID used by `search_tasks` / `list_projects`. |
| `access_token` | secret | yes | Asana Personal Access Token. |

Health check: `access_token_present` (required secret) — deterministic, no live
call.

## Tests / Fixture Behavior

Default tests are **offline and deterministic**. They stub `plugins.api`, load
`plugin_main.py`, and patch the network layer (`_api_request` and the
`_list_*` / `_search_*` / `_get_task` / `_create_task` helpers) with fake return
values. No test contacts Asana or the network. Coverage includes: manifest
shape, tool registration and destructive-name declarations, command parsing,
formatting, the blockers summary buckets, missing-token handling, HTTP error
messages (401/403/429), and create-task routing.

Run:

```powershell
uv run python -m pytest plugins/asana-projects/tests -q
```

## Manual / Live Checks (optional, not run by default)

Use a **throwaway Asana workspace / test project** and a test-account PAT:

1. `list_workspaces` → returns your workspaces with GIDs.
2. `list_projects <workspace_gid>` → returns projects.
3. `list_tasks <project_gid>` and `blockers <project_gid>` → return tasks / a
   summary.
4. `search_tasks <query>` → returns matching tasks.
5. `asana_create_task <project_gid> Test task` → Row-Bot shows an approval
   prompt; on confirm, the task appears in Asana.

Do not commit real tokens, GIDs, task names, or API responses from these checks.

## Known Limitations And Rate Limits

- Asana enforces per-token rate limits; the plugin surfaces `429` as a
  wait-and-retry message.
- `search_tasks` relies on typeahead (name match, single workspace).
- `list_tasks` requires a project GID; there is no cross-project task listing.
- `current_status` on projects is shown only when Asana returns it.
