# Microsoft Teams Channel

Connect Row-Bot to Microsoft Teams through the Bot Framework messaging
endpoint. The plugin receives Teams activities through Row-Bot's namespaced
plugin webhook and sends Row-Bot responses back to the same Teams conversation.

## Features

- Text inbound and outbound messages.
- Pairing, single-user, or Row-Bot allowlist authorization.
- Streaming-style updates by sending an activity and editing it while Row-Bot
  works.
- Approval prompts with Adaptive Card approve and deny buttons.
- Personal-chat file download handling for supported Teams attachments.
- Personal-chat file consent flow for outbound files.
- Deterministic local validation with no default Microsoft, Azure, Teams, or
  network dependency.

## Current Limitations

- Channel and group chat file sends need Microsoft 365 Graph, SharePoint, or
  OneDrive access and are intentionally deferred to a Microsoft 365
  productivity plugin.
- Live webhook authentication requires Bot Framework RS256 JWT validation. The
  current implementation uses PyJWT with crypto support when Row-Bot provides
  it, and fails closed if the dependency is unavailable.
- Teams allows one messaging endpoint per bot registration. Use the Row-Bot
  endpoint for the bot dedicated to this plugin.
- Proactive sends require Row-Bot to have seen and stored a conversation
  reference from Teams first, and the Teams app must be installed in the target
  conversation.

## Prerequisites

- An Azure Bot or Microsoft 365 app bot registration.
- Microsoft App ID for the bot.
- Bot client secret.
- Public HTTPS URL for Row-Bot's webhook, using either Row-Bot's tunnel support
  or your own reverse proxy.

## Row-Bot Setup

1. Install Microsoft Teams Channel from the Row-Bot plugin marketplace.
2. Configure:
   - Microsoft App ID.
   - Token Authority Tenant, usually `botframework.com`.
   - Bot Client Secret.
   - Optional Allowed Teams Tenant IDs.
   - Authorization mode, default `pairing`.
   - Optional Public Base URL if you manage your own tunnel.
3. Run Test in Plugin Center.
4. Enable the plugin.
5. Start the Microsoft Teams channel in Row-Bot.

The plugin registers this local webhook route:

```text
/plugin-webhooks/microsoft-teams-channel/messages
```

If `public_base_url` is configured, set the Azure Bot messaging endpoint to:

```text
{public_base_url}/plugin-webhooks/microsoft-teams-channel/messages
```

## Azure And Teams Setup

1. Create or open your Azure Bot / Microsoft 365 app bot registration.
2. Set the messaging endpoint to the public Row-Bot webhook URL above.
3. Add or enable the Teams channel for the bot.
4. Build a Teams app package that includes the bot.
5. Include bot scopes needed for your use:
   - `personal` for direct messages, pairing, approvals, and personal files.
   - `team` for team channel conversations.
   - `groupChat` for group chats.
6. Set `supportsFiles` to `true` in the Teams app manifest if you want
   personal-chat file support.
7. Upload/install the Teams app in your tenant.

No Microsoft Graph OAuth scopes are requested by this channel plugin. It uses
Bot Framework bot credentials for Teams messaging. Channel/group file access is
deferred because it needs Microsoft 365 document permissions.

## Pairing Flow

1. In Row-Bot, generate a pairing code for the Teams channel.
2. Open a personal chat with the Teams bot.
3. Send the pairing code as a DM to the bot.
4. Row-Bot confirms that Teams is paired.

For troubleshooting, the plugin uses the Teams `from.id` value as the primary
authorization ID. It stores the Microsoft Entra `aadObjectId` only as metadata
to help admins identify the user.

## Manual Live Smoke Tests

Run these only after local tests and validation pass:

1. Install the plugin from a local marketplace index and confirm it is disabled.
2. Configure App ID, authority tenant, secret, tenant allowlist, and public URL.
3. Run Test, enable the plugin, and start the Teams channel.
4. Configure the Azure Bot messaging endpoint.
5. Install the Teams app in personal scope.
6. DM the Row-Bot pairing code to the bot.
7. Send normal text and a slash-style command such as `/status`.
8. Trigger a Row-Bot approval and approve or deny with the Adaptive Card.
9. Confirm streaming placeholder updates during a longer response.
10. Send an image or document in personal chat.
11. Use Row-Bot's generated `send_teams_message` tool.
12. Stop the channel and confirm inbound Teams messages no longer run Row-Bot.

## Privacy And Permissions

The plugin declares `network`, `messaging`, `external_send`, `account`, and
`files` because it receives Teams messages, sends external replies, validates
bot credentials, and may process user-provided attachments. It does not store
access tokens, full incoming activities, message transcripts, provider
responses, or raw attachment bytes. It stores display-safe conversation
references so replies and proactive sends can work after a Teams message is
received.

## Troubleshooting

- `401` or `403` webhook responses usually mean the Bot Framework bearer token
  is missing, invalid, for the wrong app ID, or signed by a key not endorsed for
  Teams.
- Missing public URL or tunnel setup prevents Azure from reaching Row-Bot.
- Proactive sends can fail with `403` if the app is not installed in the target
  conversation.
- Team/channel file operations that require SharePoint or OneDrive access are
  outside this channel plugin's scope.
