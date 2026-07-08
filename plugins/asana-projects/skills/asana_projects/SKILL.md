---
name: asana_projects
display_name: Asana Projects
icon: checklist
description: Guides the agent on when and how to use the Asana tools to browse workspaces, projects, and tasks, summarize blockers, and create tasks with approval.
tags:
  - asana
  - projects
  - tasks
  - project-management
version: "0.1"
author: Venky1209
---

# Asana Projects

You have access to two Asana tools. **Reading** is safe and instant.
**Creating** a task changes the user's live Asana, so that tool is
approval-gated — Row-Bot will ask the user to confirm before it runs.

Tools:

- `asana_projects` — read: list workspaces/projects/tasks, search tasks, view a
  task, and summarize blockers (no approval needed).
- `asana_create_task` — create a task in a project (approval-gated).

## When To Use

- The user asks what projects or tasks exist, or the status of work in Asana.
- The user asks "what's blocking us", "what's overdue", or for a project health
  summary.
- The user references Asana, "our board", "the project", or a task by name.
- The user asks to add or create a task — use `asana_create_task` and expect an
  approval prompt.

Do not use these tools for email or calendar — Row-Bot has separate Gmail and
Calendar tools for that.

## Read commands (`asana_projects`)

| Command | Example | Purpose |
| --- | --- | --- |
| `list_workspaces [N]` | `list_workspaces` | Find workspace GIDs. |
| `list_projects [workspace_gid] [N]` | `list_projects 12000001` | List projects in a workspace. |
| `list_tasks <project_gid> [N]` | `list_tasks 12000045 20` | List tasks in a project. |
| `search_tasks <query> [N]` | `search_tasks onboarding` | Search tasks in the default workspace. |
| `task <task_gid>` | `task 12000900` | Full detail for one task. |
| `blockers <project_gid>` | `blockers 12000045` | Summarize open tasks by due status. |

`workspace_gid` is optional for `list_projects` and `search_tasks` when a
Default workspace GID is configured in Plugin Center. A bare query without a
command searches tasks.

## Create tool (approval-gated)

| Tool | Input | Example |
| --- | --- | --- |
| `asana_create_task` | `<project_gid> <task name>` | `12000045 Draft Q3 onboarding checklist` |

## Write safety

- GIDs are numeric. Never guess a GID — look it up first with a list or search
  command.
- Before creating a task, confirm the target project and task name with the user
  in plain language, then call the tool — Row-Bot will still show its own
  approval prompt.

## Presentation Tips

- Start with `list_workspaces`, then drill into `list_projects` and
  `list_tasks`; users rarely know GIDs by heart.
- For "what's blocking" questions, lead with the `blockers` summary (overdue /
  upcoming / no due date / unassigned counts), then list the overdue tasks.
- Summarize the most relevant few tasks instead of dumping every field.
- Never expose the access token; if the tool reports missing setup or an auth
  error, tell the user to check the token in Plugin Center.
