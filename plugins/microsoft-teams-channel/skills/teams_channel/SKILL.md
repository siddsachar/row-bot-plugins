---
name: teams_channel
display_name: Microsoft Teams Channel
icon: groups
description: Guides Row-Bot on using Microsoft Teams channel delivery for messages, approvals, and personal-chat files.
tags:
  - teams
  - channel
  - messaging
version: "1.0"
author: Row-Bot
---

# Microsoft Teams Channel

Use the Teams channel when the user wants Row-Bot to communicate through
Microsoft Teams.

## Channel Behavior

- Teams supports text messages, slash-style commands, typing indicators,
  streaming-style message updates, and Adaptive Card approvals.
- Personal chats support the most complete behavior, including pairing and
  personal-chat files.
- Team channels and group chats work for text, but file operations may require
  Microsoft 365 document access that this channel plugin does not request.

## Delivery Guidance

- Prefer concise Teams-friendly replies with clear next steps.
- For approvals, rely on the channel's Adaptive Card buttons instead of asking
  for plain-text yes or no.
- For generated documents or images, use personal chat delivery when available.
- If a team or group file operation needs SharePoint, OneDrive, or Graph access,
  tell the user that a Microsoft 365 document tool is needed.
