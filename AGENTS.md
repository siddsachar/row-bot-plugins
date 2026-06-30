# AGENTS.md

Instructions for AI coding agents working in `row-bot-plugins`.

## Mission

This repo is the plugin marketplace catalog for Row-Bot Plugin System v2.
Contributors add installable plugin directories under `plugins/`, keep
`index.json` generated, and preserve a safe local-first user experience.

## Hard Rules

- Do not commit secrets, tokens, API keys, private local paths, real user data,
  real messages, generated logs, or provider responses.
- Do not add hidden network calls, telemetry, analytics, or phone-home behavior.
- Do not make default validation depend on live providers, live channels, live
  MCP servers, real network availability, or a local Ollama model.
- Do not add arbitrary plugin UI. Row-Bot Plugin Center owns all plugin UI.
- Do not add unsupported plugin surfaces. Supported surfaces are native tools,
  plugin-packaged MCP-backed tools, bundled skills, and channels.
- Do not import Row-Bot internals from plugin code. Use only `plugins.api`.
- Do not install plugin dependencies into Row-Bot's main environment.
- Do not edit `index.json` by hand except to inspect it. Regenerate it with
  `scripts/build_index.py`.

## Expected Workflow

1. Read `README.md`, `CONTRIBUTING.md`, and the docs under `docs/`.
2. Start from the closest template in `templates/`.
3. Keep plugin ids lowercase with hyphens.
4. Declare all settings, secrets, auth, permissions, and health checks in
   `plugin.json`.
5. Use deterministic fakes for default validation.
6. Run plugin validation and repo validation.
7. Rebuild `index.json`.
8. Test local marketplace install through Row-Bot when changing plugin behavior.

## Useful Commands

From the Row-Bot checkout:

```powershell
$env:ROW_BOT_SOURCE = (Get-Location)
uv run python ..\row-bot-plugins\scripts\validate_plugin.py ..\row-bot-plugins\plugins\<plugin-id>
uv run python ..\row-bot-plugins\scripts\build_index.py ..\row-bot-plugins --source "https://github.com/siddsachar/row-bot-plugins"
uv run python ..\row-bot-plugins\scripts\validate_repo.py ..\row-bot-plugins
```

For local marketplace testing:

```powershell
$env:ROW_BOT_PLUGIN_INDEX_URL = "$env:USERPROFILE\Code\row-bot-plugins\index.json"
uv run python launcher.py
```

## Handoff Notes

When finishing work, report:

- Plugin ids changed
- Files changed
- Validation commands and results
- Whether `index.json` was regenerated
- Manual/live checks still needed
- Any permissions, OAuth scopes, channel scopes, or external-send behavior
  requiring reviewer attention
