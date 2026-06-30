# Row-Bot Plugins

This repository is the first-party marketplace catalog for Row-Bot Plugin
System v2. A plugin can add only these supported surfaces:

- Native Row-Bot tools
- Plugin-packaged MCP-backed tools
- Bundled plugin skills
- Channels

Row-Bot renders one native Plugin Center for every plugin. Plugins declare
metadata, permissions, settings, secrets, auth, health checks, tools, channels,
skills, logs, and updates in `plugin.json`; they do not ship arbitrary custom
UI.

## Quick Start

Use adjacent checkouts while Plugin System v2 is under active development:

```powershell
$Workspace = "$env:USERPROFILE\Code"
git clone https://github.com/siddsachar/row-bot.git "$Workspace\row-bot"
git clone https://github.com/siddsachar/row-bot-plugins.git "$Workspace\row-bot-plugins"
cd "$Workspace\row-bot"
git checkout main
uv sync --locked --all-extras --group test
```

Validate this marketplace repo from the Row-Bot checkout:

```powershell
$env:ROW_BOT_SOURCE = "$Workspace\row-bot"
uv run python "$Workspace\row-bot-plugins\scripts\validate_repo.py" "$Workspace\row-bot-plugins"
```

Build or refresh the catalog index:

```powershell
uv run python "$Workspace\row-bot-plugins\scripts\build_index.py" "$Workspace\row-bot-plugins" --source "https://github.com/siddsachar/row-bot-plugins"
```

Install from a local catalog while developing:

```powershell
$env:ROW_BOT_PLUGIN_INDEX_URL = "$Workspace\row-bot-plugins\index.json"
uv run python launcher.py
```

Then open Settings -> Plugins -> Plugin Marketplace, install the plugin, review
permissions, configure required settings/secrets/auth, run Test, and enable it.
Installs must stay disabled until configured, tested, and explicitly enabled.

## Repository Layout

```text
row-bot-plugins/
  index.json                    # Marketplace catalog generated from plugins/
  plugins/                      # Installable plugins
  templates/                    # Starter plugin skeletons
  scripts/
    validate_plugin.py          # Validate one plugin directory
    validate_repo.py            # Validate plugins, templates, and index.json
    build_index.py              # Generate index.json
  docs/
    PLUGIN_AUTHOR_GUIDE.md
    MANIFEST_V2_REFERENCE.md
    VALIDATION_AND_CATALOG.md
    PLUGIN_REVIEW_CHECKLIST.md
```

## Add A Plugin

1. Copy the closest template from `templates/` into `plugins/<plugin-id>/`.
2. Rename ids, labels, descriptions, and tool/channel names.
3. Declare every setting, secret, auth flow, permission, and health check in
   `plugin.json`.
4. Implement only supported surfaces.
5. Validate the plugin and the whole repo.
6. Rebuild `index.json`.
7. Test local install from the marketplace catalog.
8. Open a PR with the checklist in `.github/pull_request_template.md`.

Detailed instructions live in [docs/PLUGIN_AUTHOR_GUIDE.md](docs/PLUGIN_AUTHOR_GUIDE.md).

## Contributor Rules

- Do not commit API keys, OAuth tokens, private local paths, real customer data,
  real messages, or generated logs.
- Do not make default validation require live providers, live channels, live MCP
  servers, real network availability, or a local Ollama model.
- Do not add unsupported extension surfaces such as provider plugins, custom
  NiceGUI panels, memory providers, workflow triggers, or general hooks.
- Do not install plugin dependencies into Row-Bot's main environment.
- Prefer deterministic fakes, dry-run modes, and local fixtures.
- Update `index.json` in the same PR as plugin changes.

See [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md) before
changing plugin code.
