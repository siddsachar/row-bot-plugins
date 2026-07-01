# Validation And Catalog

This repository has two validation layers:

- Row-Bot manifest/security validation for individual plugins.
- Marketplace validation for the full repo and generated `index.json`.

## Bootstrap Row-Bot

The scripts import Row-Bot's plugin validator. Run them from a Row-Bot
environment, or set `ROW_BOT_SOURCE` to a Row-Bot checkout.

Recommended local layout:

```text
Code/
  row-bot/
  row-bot-plugins/
```

Recommended command pattern:

```powershell
cd "$env:USERPROFILE\Code\row-bot"
$env:ROW_BOT_SOURCE = (Get-Location)
uv run python ..\row-bot-plugins\scripts\validate_repo.py ..\row-bot-plugins
```

## Validate One Plugin

```powershell
uv run python ..\row-bot-plugins\scripts\validate_plugin.py ..\row-bot-plugins\plugins\hello-tool
```

This checks:

- `plugin.json` manifest v2 shape
- Supported extension surfaces only
- Supported permissions, settings, and auth types
- Basic plugin code import/security rules

It does not prove that a live provider account, OAuth app, webhook endpoint, or
external channel works. Cover those with README manual/live checks and local
marketplace smoke testing.

## Validate The Whole Repo

```powershell
uv run python ..\row-bot-plugins\scripts\validate_repo.py ..\row-bot-plugins
```

This checks:

- All directories under `plugins/`
- All directories under `templates/`
- `index.json` matches generated plugin metadata and checksums
- No obvious private local paths or secret-like tokens in tracked text files
- Required docs and scripts are present

The repo scan is a safety net, not permission to commit sensitive data. Review
plugin README files, tests, fixtures, and examples manually for real messages,
customer data, provider responses, tokens, account IDs, tenant IDs, local paths,
and logs before opening a PR.

Use JSON output when another tool needs to consume results:

```powershell
uv run python ..\row-bot-plugins\scripts\validate_repo.py ..\row-bot-plugins --json
```

## Build The Index

For local install testing, point `source` at your local plugin repo:

```powershell
uv run python ..\row-bot-plugins\scripts\build_index.py ..\row-bot-plugins --source "$env:USERPROFILE\Code\row-bot-plugins"
```

For a PR or push, use the public repository source:

```powershell
uv run python ..\row-bot-plugins\scripts\build_index.py ..\row-bot-plugins --source "https://github.com/siddsachar/row-bot-plugins"
```

The generated catalog includes:

- Plugin id
- Name
- Version
- Description
- Author
- Tags
- Relative plugin path
- Optional archive URL
- `sha256:` checksum
- Provides summary
- Permissions
- Minimum Row-Bot version

Do not hand-edit checksums.

## Local Marketplace Smoke

From Row-Bot:

```powershell
$PluginRepo = "$env:USERPROFILE\Code\row-bot-plugins"
$env:ROW_BOT_PLUGIN_INDEX_URL = "$PluginRepo\index.json"
uv run python launcher.py
```

Open Settings -> Plugins -> Plugin Marketplace. Install the plugin and verify:

- It installs disabled.
- Plugin Center renders metadata and setup.
- Missing setup fails clearly.
- Test and Enable behave correctly after setup is configured.
- Disable removes plugin-owned tools, MCP tools, skills, and channels.
- Permissions, auth, settings, secrets, health checks, logs, and docs are clear.
- External-send or destructive operations request approval before they send,
  delete, publish, charge, refund, change permissions, or mutate provider data.

For plugins with optional live checks, run them only with test accounts,
throwaway workspaces, sandbox stores, or provider test modes. Record the command
or manual steps and result in the PR template.

## GitHub Actions

The validation workflow checks this repo with Row-Bot `main`. Leave the
repository variable `ROW_BOT_REF` unset or set it to `main`. If Row-Bot is
private, add a `ROW_BOT_SOURCE_TOKEN` secret that can read
`siddsachar/row-bot`.
