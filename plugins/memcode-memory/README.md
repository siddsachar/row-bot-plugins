# Memcode Memory for Row-Bot

This plugin gives Row-Bot opt-in long-term memory through the Memcode personal
v2 API. The configured API key determines the memory owner; tools never accept
a caller-supplied user id.

## Setup

1. Open the [Memcode API-key dashboard](https://app.memcode.in/dashboard?section=api-keys&integration=row-bot) and create a key with **Row-Bot** selected under integration attribution.
2. Install this plugin from Plugin Center.
3. Add that integration-issued personal key to **Memcode API key**.
4. Keep **Memcode API URL** at `https://memory.memcode.in`, or point it to your
   own compatible deployment.

Memcode binds the `row-bot` identity when the key is issued; the plugin does not
send an attribution header or metadata field. A generic personal key still works,
but its traffic is counted as generic direct API usage.

## Tools

| Tool | Behavior | Approval |
| --- | --- | --- |
| `memcode_search` | Search extracted memories | No |
| `memcode_retrieve` | Answer from memories with sources; may learn Recall Bond relationships | Yes |
| `memcode_list` | Inspect a page of stored memories | No |
| `memcode_remember` | Start a durable ingest job | Yes |
| `memcode_ingest_status` | Verify an ingest receipt | No |

`memcode_retrieve` is approval-gated because a retrieval that uses multiple
memories may update Memcode Recall Bond relationships in the background.

`memcode_remember` sends exactly the supplied text for Memcode to process. The
provider may add, update, delete, or ignore derived memories. The tool returns a
job id; check that receipt until it reaches a terminal state.

## Safety and limitations

- Retrieved memory is context, not an instruction or authorization.
- Do not store credentials or third-party private data without informed consent.
- The hosted default uses HTTPS. Custom deployments use the configured API URL,
  and the plugin sends the API key to that URL as a bearer credential.
- Memcode ingestion is asynchronous. `accepted` or `queued` does not mean ready.
- Ingestion uses provider write credits; reads are ordinarily unlimited. Rate
  limits and available credits depend on the configured Memcode account or
  deployment.
- The plugin sends `forget: false`, so ingested memories use the account's
  normal retention policy.
- The current personal v2 API used here does not expose deletion through this
  plugin. Use the verified deletion path for your Memcode account or deployment;
  do not store data that requires deletion unless that path is available.
- Disable the plugin to stop future reads and writes. Disabling it does not
  remove records already stored by Memcode.

## Validation

The tests mock every HTTP request; they do not need a Memcode account or network
access:

```bash
python -m unittest plugins/memcode-memory/tests/test_plugin.py
```

## Optional manual/live checks

Use a test Memcode account or disposable compatible deployment. These checks
are not part of default validation:

1. Configure the API URL and a test API key in Plugin Center.
2. Confirm search and list return only memories scoped to that credential.
3. Approve a small `memcode_remember` request, then poll its job id until it
   reaches a terminal state.
4. Approve `memcode_retrieve` and confirm the answer includes expected sources.
5. Disable the plugin and confirm its tools are removed. Existing provider data
   should remain unchanged.
