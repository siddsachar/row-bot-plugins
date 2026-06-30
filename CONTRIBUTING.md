# Contributing Row-Bot Plugins

Row-Bot plugins are local-first extensions. The review bar is intentionally
strict because plugins can touch user data, accounts, files, messages, and
external services.

## Development Setup

Keep Row-Bot and this marketplace repo next to each other:

```text
Code/
  row-bot/
  row-bot-plugins/
```

Use the Row-Bot checkout that contains Plugin System v2. While the feature is
landing, that is `feat/plugin-system-v2`; after merge, use `main`.

```powershell
cd "$env:USERPROFILE\Code\row-bot"
git checkout feat/plugin-system-v2
uv sync --locked --all-extras --group test
$env:ROW_BOT_SOURCE = "$env:USERPROFILE\Code\row-bot"
```

Validate this repo:

```powershell
uv run python ..\row-bot-plugins\scripts\validate_repo.py ..\row-bot-plugins
```

## Contribution Workflow

1. Start from a template in `templates/`.
2. Build in `plugins/<plugin-id>/`.
3. Keep the plugin disabled-by-default compatible: required setup must be
   declared, health checks must be deterministic where possible, and the plugin
   must not assume it is enabled at install time.
4. Validate the plugin:

   ```powershell
   uv run python ..\row-bot-plugins\scripts\validate_plugin.py ..\row-bot-plugins\plugins\<plugin-id>
   ```

5. Rebuild the index:

   ```powershell
   uv run python ..\row-bot-plugins\scripts\build_index.py ..\row-bot-plugins --source "https://github.com/siddsachar/row-bot-plugins"
   ```

6. Validate the repo:

   ```powershell
   uv run python ..\row-bot-plugins\scripts\validate_repo.py ..\row-bot-plugins
   ```

7. Test a local marketplace install with `ROW_BOT_PLUGIN_INDEX_URL` pointed at
   this repo's `index.json`.

## Plugin Requirements

Every plugin must include:

- `plugin.json` with `schema_version: 2`
- Semver `version`
- Clear user-facing `name` and `description`
- Accurate `provides` declarations
- Accurate `permissions`
- Declarative `settings`, `secrets`, and `auth` entries when setup is needed
- Health checks for required setup
- Deterministic validation path
- No secrets or private data

Native tool and channel plugins with Python code must expose:

```python
def register(api):
    ...
```

Plugins may import only the public plugin API:

```python
from plugins.api import PluginTool
from plugins.api import Channel
```

Do not import Row-Bot internals or UI frameworks.

## Tests And Validation

Default validation must be offline and deterministic. Live provider probes,
real channel sends, real OAuth refreshes, and real network checks belong in
manual or opt-in e2e instructions, not in default scripts.

Before opening a PR, run:

```powershell
uv run python ..\row-bot-plugins\scripts\validate_repo.py ..\row-bot-plugins
```

For Row-Bot core changes required by a plugin, run the relevant Row-Bot test
matrix from the Row-Bot checkout. Start with:

```powershell
uv run python scripts/run_test_matrix.py changed --base origin/main
```

Use `scripts/run_test_matrix.py pr` for shared runtime, security, installer, or
release-sensitive changes.

## Review Expectations

Reviewers check:

- Privacy and local-first behavior
- No hidden phone-home behavior
- No default live provider/channel/network dependency
- Correct permissions and setup declarations
- Disabled-by-default install flow
- Plugin Center health/test/enable flow
- Approval gates for destructive or external-send actions
- Index checksum freshness
- Clear docs for manual/live setup

Use [docs/PLUGIN_REVIEW_CHECKLIST.md](docs/PLUGIN_REVIEW_CHECKLIST.md) for the
full checklist.
