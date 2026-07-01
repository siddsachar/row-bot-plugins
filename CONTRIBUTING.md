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

Use the Row-Bot `main` checkout, which includes Plugin System v2.

```powershell
cd "$env:USERPROFILE\Code\row-bot"
git checkout main
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
3. Define the first MVP before coding. Prefer a read-only, search, summarize,
   or draft-only version first; add writes, sends, deletes, refunds, permission
   changes, or publishes only after approval behavior is explicit.
4. Keep the plugin disabled-by-default compatible: required setup must be
   declared, health checks must be deterministic where possible, and the plugin
   must not assume it is enabled at install time.
5. Add or update the plugin README with setup, provider accounts, OAuth scopes
   or API-token requirements, dry-run behavior, manual/live checks, and known
   limitations.
6. Validate the plugin:

   ```powershell
   uv run python ..\row-bot-plugins\scripts\validate_plugin.py ..\row-bot-plugins\plugins\<plugin-id>
   ```

7. Rebuild the index:

   ```powershell
   uv run python ..\row-bot-plugins\scripts\build_index.py ..\row-bot-plugins --source "https://github.com/siddsachar/row-bot-plugins"
   ```

8. Validate the repo:

   ```powershell
   uv run python ..\row-bot-plugins\scripts\validate_repo.py ..\row-bot-plugins
   ```

9. Test a local marketplace install with `ROW_BOT_PLUGIN_INDEX_URL` pointed at
   this repo's `index.json`.

## MVP Scope

New provider plugins should start with the smallest useful workflow that proves
the manifest, settings, secrets, auth, health checks, and runtime loading path.
Good first versions usually search, read, list, summarize, export, or draft.

Avoid shipping broad "do everything" tools. Split operations into clear
sub-tools when that makes permissions and approvals easier to review. If the
provider API can send messages, charge/refund money, delete records, change
permissions, publish content, or mutate business data, the MVP may still be
read-only while documenting those future operations.

## Plugin README Requirements

Each non-template plugin should include a README that covers:

- User-facing purpose and current MVP limitations.
- Required provider account, app setup, OAuth scopes, API tokens, webhook URLs,
  channel scopes, or tenant/admin steps.
- What each declared Row-Bot permission is used for.
- Required settings, secrets, auth entries, and health checks.
- Deterministic test or fixture behavior.
- Manual/live smoke checks that are useful but not required by default
  validation.
- Destructive or external-send operations and how Row-Bot approvals protect
  them.
- Provider API rate limits, data retention notes, and known limitations.

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
- A README for setup and manual/live checks, unless the plugin is a template
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

## Approval-Aware Operations

Any operation that sends, deletes, publishes, charges, refunds, changes
permissions, changes account state, modifies records, or posts to an external
audience must be approval-aware. Native tools that expose multiple LangChain
tools should override `destructive_tool_names` for those operations.

Background-safe destructive operations are exceptional. Only expose them when
the tool checks Row-Bot's runtime context, validates allowed recipients or
targets, and documents the behavior in the plugin README.

## Tests And Validation

Default validation must be offline and deterministic. Live provider probes,
real channel sends, real OAuth refreshes, and real network checks belong in
manual or opt-in e2e instructions, not in default scripts.

Use fake clients, local fixtures, static provider responses, and dry-run paths
for tests. Do not commit generated logs, real provider responses, customer data,
message bodies, access tokens, refresh tokens, or private local paths.

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
- README coverage for accounts, scopes, permissions, dry-run behavior, and
  known limitations

Use [docs/PLUGIN_REVIEW_CHECKLIST.md](docs/PLUGIN_REVIEW_CHECKLIST.md) for the
full checklist.
