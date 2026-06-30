# Manifest v2 Reference

Every plugin directory contains `plugin.json`.

## Required Fields

```json
{
  "schema_version": 2,
  "id": "example-plugin",
  "name": "Example Plugin",
  "version": "0.1.0",
  "min_row_bot_version": "0.0.0",
  "description": "Short user-facing description.",
  "provides": {
    "native_tools": [],
    "mcp_servers": [],
    "channels": [],
    "skills": []
  }
}
```

Rules:

- `schema_version` must be `2`.
- `id` must be lowercase alphanumeric with hyphens, 2 to 64 characters.
- `version` and `min_row_bot_version` must be `x.y.z` semver.
- `provides` may contain only `native_tools`, `mcp_servers`, `channels`, and
  `skills`.

## Optional Metadata

```json
{
  "author": {"name": "Row-Bot", "github": "siddsachar"},
  "long_description": "Longer marketplace text.",
  "icon": "extension",
  "license": "MIT",
  "tags": ["mail", "calendar"],
  "homepage": "https://example.test",
  "repository": "https://github.com/example/plugin"
}
```

Use public URLs only. Do not use private local paths.

## Provides

Native tools:

```json
{
  "native_tools": [
    {"id": "search_mail", "entrypoint": "plugin_main.py"}
  ]
}
```

MCP servers:

```json
{
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
  ]
}
```

Channels:

```json
{
  "channels": [
    {"id": "matrix"}
  ]
}
```

Skills:

```json
{
  "skills": [
    {"id": "office365_usage", "path": "skills/office365_usage/SKILL.md"}
  ]
}
```

## Permissions

Supported permissions:

- `network`
- `files`
- `account`
- `external_send`
- `messaging`
- `memory_documents`
- `shell_processes`

Declare the smallest accurate set. Permissions are user-facing; write labels
and descriptions so reviewers can explain what the plugin needs.

## Settings And Secrets

Supported field types:

- `text`
- `password`
- `secret`
- `checkbox`
- `select`
- `multi-select`
- `number`
- `url`
- `local_path`
- `textarea`

Example:

```json
{
  "settings": {
    "base_url": {
      "type": "url",
      "label": "Base URL",
      "description": "Service URL for your account.",
      "required": true
    },
    "dry_run": {
      "type": "checkbox",
      "label": "Dry Run",
      "default": true
    }
  },
  "secrets": {
    "api_key": {
      "type": "secret",
      "label": "API Key",
      "required": true
    }
  }
}
```

Secret values live in Row-Bot's secret store. Do not place real values in
`plugin.json`, docs, tests, or examples.

## Auth

Supported auth types:

- `api_key`
- `bearer_token`
- `oauth2_pkce`
- `device_code`
- `open_url_paste_code`

Example:

```json
{
  "auth": {
    "account": {
      "type": "api_key",
      "secret": "api_key"
    }
  }
}
```

OAuth and device-code flows should declare provider URLs and scopes, but default
tests must not call live providers.

## Health Checks

Recommended deterministic checks:

```json
{
  "health_checks": [
    {
      "id": "settings_present",
      "type": "required_settings",
      "settings": ["base_url"]
    },
    {
      "id": "secrets_present",
      "type": "required_secrets",
      "secrets": ["api_key"]
    },
    {
      "id": "mcp_starts",
      "type": "mcp_server_starts"
    },
    {
      "id": "channel_configured",
      "type": "channel_configured"
    }
  ]
}
```

Manual/live checks may be declared for user visibility, but they must remain
non-blocking for deterministic validation unless Row-Bot explicitly supports a
local fake.
