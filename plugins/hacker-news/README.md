# Hacker News Reader

Browse and search Hacker News directly from Row-Bot.

## Features

- Front page stories from the Hacker News Firebase API
- New submissions
- Full-text archive search through Algolia's Hacker News API
- Story details with top comments

## Configuration

No API key is required.

| Setting | Default | Description |
| --- | --- | --- |
| `default_count` | `10` | Number of stories returned per request, clamped to 1-30. |

## Commands

The `hacker_news` tool accepts a single query string:

| Command | Example | Description |
| --- | --- | --- |
| `top_stories [N]` | `top_stories 5` | Fetch front page stories. |
| `new_stories [N]` | `new_stories 10` | Fetch newest submissions. |
| `search <query> [N]` | `search rust 5` | Search the Hacker News archive. |
| `story_detail <id> [comments:N]` | `story_detail 12345 comments:3` | Fetch a story and top comments. |

A bare query without a command is treated as `search <query>`.

## Network Behavior

The plugin performs live network requests only when the user runs the tool. It
does not contact Hacker News or Algolia during install, validation, or plugin
registration.

## APIs Used

- Hacker News Firebase API
- Algolia Hacker News Search API

## License

Apache-2.0. See [LICENSE](LICENSE).
