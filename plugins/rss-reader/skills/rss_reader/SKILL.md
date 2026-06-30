---
name: rss_reader
display_name: RSS Feed Reader
icon: rss_feed
description: Guides the agent on when and how to use the RSS Reader tool for feed subscriptions and reading.
tags:
  - rss
  - feeds
  - news
  - reading
version: "1.0"
author: Row-Bot
---

# RSS Feed Reader

You have access to the `rss_reader` tool for managing RSS and Atom feed
subscriptions.

## When To Use

- The user asks to subscribe to, follow, or track a blog, news source, or
  podcast.
- The user wants to read or check their feeds.
- The user asks what is new across their subscriptions.
- The user mentions an RSS or Atom feed URL.

## Commands

| Command | Purpose |
| --- | --- |
| `add_feed <url> [name]` | Subscribe to a feed and optionally give it a friendly name. |
| `remove_feed <url|name>` | Unsubscribe by URL or display name. |
| `list_feeds` | Show all subscribed feeds. |
| `fetch <url|name> [count]` | Get latest entries from one feed. |
| `fetch_all [count]` | Get latest entries across all subscriptions. |

## Presentation Tips

- After `add_feed`, confirm the subscription and mention how many entries were
  available.
- For fetch results, summarize the top few entries with titles and short
  descriptions rather than dumping every raw item.
- Include article links so the user can read the full source.
- When some feeds fail, still show successful results and mention failures
  briefly.
- If the user has no feeds yet, suggest feeds relevant to their interests.

Feed fetching depends on live network availability when the tool is run.
