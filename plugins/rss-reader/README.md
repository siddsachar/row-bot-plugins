# RSS Reader

Subscribe to and read RSS and Atom feeds directly from Row-Bot.

## Features

- Subscribe to feeds by URL.
- List and remove subscriptions.
- Fetch recent entries from one feed.
- Fetch recent entries across all subscribed feeds, merged by date.
- Parse common RSS and Atom feeds without external Python dependencies.

## Configuration

No API key is required.

| Setting | Default | Description |
| --- | --- | --- |
| `default_count` | `10` | Number of entries returned per request, clamped to 1-30. |

Feed subscriptions are stored in this plugin's Row-Bot configuration as a local
list of feed URL/name pairs.

## Commands

The `rss_reader` tool accepts a single query string:

| Command | Example | Description |
| --- | --- | --- |
| `add_feed <url> [name]` | `add_feed https://example.com/rss My Blog` | Subscribe to a feed. |
| `remove_feed <name|url>` | `remove_feed My Blog` | Unsubscribe from a feed. |
| `list_feeds` | `list_feeds` | Show all subscriptions. |
| `fetch <name|url> [N]` | `fetch My Blog 5` | Fetch entries from one feed. |
| `fetch_all [N]` | `fetch_all 10` | Fetch entries across all subscriptions. |

A bare URL is treated as `fetch <url>`.

## Network Behavior

The plugin performs live network requests only when the user runs a command that
adds or fetches a feed. It does not fetch feeds during install, validation, or
plugin registration.

## Parser Notes

This Row-Bot v2 port uses a lightweight stdlib RSS/Atom parser instead of the
old Thoth plugin's `feedparser` dependency. It covers common RSS and Atom fields
used by most feeds. Unusual feed extensions may produce less detailed summaries.

## License

Apache-2.0. See [LICENSE](LICENSE).
