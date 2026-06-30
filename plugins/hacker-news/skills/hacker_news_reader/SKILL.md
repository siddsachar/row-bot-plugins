---
name: hacker_news_reader
display_name: Hacker News Reader
icon: newspaper
description: Guides the agent on when and how to use the Hacker News tool for tech news, startup discussions, and developer trends.
tags:
  - news
  - tech
version: "1.0"
author: Row-Bot
---

# Hacker News Reader

You have access to the `hacker_news` tool for browsing and searching Hacker
News.

## When To Use

- The user asks about tech news, startup news, developer trends, or what is
  trending in tech.
- The user mentions Hacker News, HN, or Y Combinator.
- The user wants to know what the tech community is discussing.
- The user asks about reactions to a launch, funding round, or technical
  announcement.
- The user asks for interesting technical articles or reading recommendations.

## Commands

| Command | Example | Purpose |
| --- | --- | --- |
| `top_stories [N]` | `top_stories 5` | Fetch front page stories. |
| `new_stories [N]` | `new_stories 10` | Fetch latest submissions. |
| `search <query> [N]` | `search rust programming 5` | Search the archive. |
| `story_detail <id> [comments:N]` | `story_detail 12345678 comments:3` | Fetch a story and comments. |

A bare query without a command is treated as search.

## Presentation Tips

- Summarize the top few stories rather than dumping every raw result.
- Include discussion links when useful.
- Add context when you know background about a story.
- Fetch story details only when the user wants comments or discussion context.
- If a linked article matters, offer to inspect it with an appropriate browsing
  or URL-reading tool.
