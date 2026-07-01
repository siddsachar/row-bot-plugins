# Plugin Review Checklist

Use this before merging a plugin PR.

## Manifest

- [ ] `plugin.json` uses `schema_version: 2`.
- [ ] Plugin id is stable, lowercase, and hyphenated.
- [ ] Version is semver and bumped for behavior changes.
- [ ] Description is clear and user-facing.
- [ ] `provides` contains only supported surfaces.
- [ ] Permissions are accurate and minimal.
- [ ] Settings, secrets, and auth are declarative.
- [ ] Health checks cover required local setup.
- [ ] Provider scopes and account requirements match the MVP, not future
      features.

## Security And Privacy

- [ ] No secrets, tokens, private local paths, real user data, real messages, or
      generated logs are committed.
- [ ] Fixtures and examples do not contain copied provider responses, customer
      names, account IDs, tenant IDs, message bodies, or private URLs.
- [ ] No hidden telemetry or phone-home behavior.
- [ ] Default validation does not call live providers, live MCP servers, live
      channels, or real network services.
- [ ] Plugin code imports only `plugins.api`.
- [ ] Plugin code does not import UI frameworks or Row-Bot internals.
- [ ] External send, delete, publish, and mutate operations are approval-aware.
- [ ] Payment, refund, permission, invite, account-state, and public-post
      operations are treated as destructive or external-send actions.

## Runtime Behavior

- [ ] Install defaults disabled.
- [ ] Plugin Center renders setup clearly.
- [ ] Test fails clearly when required setup is missing.
- [ ] Test passes after required setup is provided.
- [ ] Enable is blocked until required setup and Test pass.
- [ ] Disable removes plugin-owned tools, MCP tools, skills, and channels.
- [ ] Update path preserves disabled-until-tested behavior.
- [ ] Logs are useful and do not expose secrets.
- [ ] Safe read/list/search operations are separated from higher-risk mutate or
      send operations.

## Marketplace

- [ ] `index.json` was regenerated.
- [ ] Checksum changed when plugin files changed.
- [ ] Repo validation passes.
- [ ] Local marketplace install was tested.
- [ ] Manual/live checks are documented but not required by default validation.

## Documentation

- [ ] Plugin README or docs explain setup.
- [ ] Required provider accounts, scopes, and permissions are named.
- [ ] Dry-run or test-mode behavior is documented.
- [ ] Manual/live checks name required sandbox or test accounts and expected
      result.
- [ ] Destructive or external-send behavior is documented in user language.
- [ ] Known limitations are documented.
