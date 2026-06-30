# Plugin Author Guide

This guide explains how to build a Row-Bot Plugin System v2 plugin in this
marketplace repository.

## Choose The Right Surface

Use a native tool when the integration benefits from Row-Bot settings, secrets,
auth, approvals, account context, workflows, documents, or channel semantics.

Use a plugin-packaged MCP server when the integration is mostly a portable tool
server and can run cleanly as a separate process.

Use a channel plugin when the integration sends or receives messages through an
external platform.

Use bundled skills for prompt and workflow guidance that should appear only when
the owning plugin is enabled.

Do not add custom UI, provider runtimes, memory providers, workflow triggers, or
general hooks.

## Create A Plugin

Copy a template:

```powershell
Copy-Item -Recurse templates\native-tool plugins\office365
```

Then update:

- Directory name
- `plugin.json` id, name, description, tags, author, version
- `provides`
- `permissions`
- Settings, secrets, auth, and health checks
- Python code or MCP server metadata

Plugin ids use lowercase letters, numbers, and hyphens:

```text
office365
google-workspace
matrix-channel
```

Tool names should be lowercase with underscores:

```text
search_outlook_mail
create_calendar_event
send_matrix_message
```

## Native Tool Plugin

`plugin.json` declares a native tool:

```json
{
  "provides": {
    "native_tools": [
      {"id": "search_mail", "entrypoint": "plugin_main.py"}
    ],
    "mcp_servers": [],
    "channels": [],
    "skills": []
  }
}
```

`plugin_main.py` registers tools:

```python
from plugins.api import PluginTool


class SearchMailTool(PluginTool):
    @property
    def name(self) -> str:
        return "search_mail"

    @property
    def display_name(self) -> str:
        return "Search Mail"

    @property
    def description(self) -> str:
        return "Search mail messages."

    def execute(self, query: str) -> str:
        return "No live search is configured yet."


def register(api):
    api.register_tool(SearchMailTool(api))
```

If a tool can send, delete, modify, or publish data, declare destructive tool
names so Row-Bot approval gates can protect users:

```python
@property
def destructive_tool_names(self) -> set[str]:
    return {"send_mail", "delete_event"}
```

## MCP-Backed Plugin

Declare MCP servers under `provides.mcp_servers`:

```json
{
  "provides": {
    "native_tools": [],
    "mcp_servers": [
      {
        "id": "crm_mcp",
        "transport": "stdio",
        "command": "python",
        "args": ["-m", "crm_mcp_server"],
        "env": {
          "CRM_BASE_URL": "setting:base_url",
          "CRM_API_KEY": "secret:api_key"
        }
      }
    ],
    "channels": [],
    "skills": []
  }
}
```

Settings and secrets referenced with `setting:<key>` and `secret:<key>` are
resolved by Row-Bot only when the plugin is enabled. They should not be written
into the plugin directory.

## Channel Plugin

Declare the channel:

```json
{
  "provides": {
    "native_tools": [],
    "mcp_servers": [],
    "channels": [{"id": "matrix"}],
    "skills": []
  },
  "permissions": ["messaging", "external_send"]
}
```

Register a channel adapter:

```python
from plugins.api import Channel


class MatrixChannel(Channel):
    name = "matrix"
    display_name = "Matrix"

    def is_configured(self) -> bool:
        return bool(self.config.get("homeserver"))

    def is_running(self) -> bool:
        return False

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def send_message(self, target: str, text: str) -> None:
        raise RuntimeError("Live send is not implemented in the template.")


def register(api):
    api.register_channel(MatrixChannel())
```

Plugin channels must not render custom settings UI. Declare setup fields in
`plugin.json`; Row-Bot renders them in Plugin Center.

## Bundled Skills

Put skills under:

```text
plugins/<plugin-id>/skills/<skill-id>/SKILL.md
```

Declare them:

```json
{
  "provides": {
    "skills": [
      {"id": "office365_usage", "path": "skills/office365_usage/SKILL.md"}
    ]
  }
}
```

Skills load only when the owning plugin is enabled. Disabling or uninstalling
the plugin removes those skills from Row-Bot.

## Settings, Secrets, And Auth

Declare settings and secrets in `plugin.json`. Do not store real secret values
in plugin files.

```json
{
  "settings": {
    "base_url": {
      "type": "url",
      "label": "Base URL",
      "required": true
    }
  },
  "secrets": {
    "api_key": {
      "type": "secret",
      "label": "API Key",
      "required": true
    }
  },
  "auth": {
    "account": {
      "type": "api_key",
      "secret": "api_key"
    }
  }
}
```

Plugin code reads values through the public API:

```python
base_url = api.get_config("base_url")
api_key = api.get_secret("api_key")
```

## Health Checks

Use deterministic checks for local setup:

```json
{
  "health_checks": [
    {"id": "base_url_present", "type": "required_settings", "settings": ["base_url"]},
    {"id": "api_key_present", "type": "required_secrets", "secrets": ["api_key"]}
  ]
}
```

Live checks such as OAuth refreshes, API probes, or dry-run sends may be
documented as manual checks, but they must not run in default validation.

## Local Marketplace Test

From the Row-Bot checkout:

```powershell
$PluginRepo = "$env:USERPROFILE\Code\row-bot-plugins"
$env:ROW_BOT_SOURCE = (Get-Location)
uv run python "$PluginRepo\scripts\validate_repo.py" "$PluginRepo"
uv run python "$PluginRepo\scripts\build_index.py" "$PluginRepo" --source "$PluginRepo"
$env:ROW_BOT_PLUGIN_INDEX_URL = "$PluginRepo\index.json"
uv run python launcher.py
```

Install the plugin through Plugin Marketplace. Confirm:

- The plugin installs disabled.
- Plugin Center shows metadata, permissions, setup, auth, tools/channels/skills,
  health, logs, and updates.
- Test fails clearly when required setup is missing.
- Test passes after required setup is configured.
- Enable is blocked until local setup passes and Test succeeds.
- Disable removes native tools, MCP tools, skills, and channels.

Before committing, regenerate the public index source:

```powershell
uv run python "$PluginRepo\scripts\build_index.py" "$PluginRepo" --source "https://github.com/siddsachar/row-bot-plugins"
```
