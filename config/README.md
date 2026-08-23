# Credentials

Every `*.env` in this directory is gitignored. Place them by hand on the Air,
via terminal. Never paste a token into a chat session: it lands in the
transcript and has to be rotated.

| File | Holds | Where it comes from |
|---|---|---|
| `asana.env` | `ASANA_TOKEN` | Asana > Settings > Apps > Developer > Personal access token |
| `slack.env` | `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`, `SLACK_USER_ID` | see `slack.env.example` |

## Two Slack apps, deliberately

The Pulse has its own Slack app, **Sales Pulse Bot** (App ID `A0BS83JVCLU`),
separate from the daily brief's `lgv_daily_brief` app. Both live in the LGV
workspace and both are fine there.

They are kept separate on purpose. Adding a scope to a Slack app requires
reinstalling it, and reinstalling issues a new bot token that invalidates the
old one. If the two systems shared an app, every scope change to the Pulse
would silently break the 5am daily brief until its token was updated too.

So: **the daily brief's app and token are never touched by work in this repo.**
`lgv-ops/config/slack.env` is not ours to edit. If the Pulse needs a new Slack
capability, add the scope to Sales Pulse Bot and reinstall that app only.

### Scopes on Sales Pulse Bot

| Scope | Why |
|---|---|
| `chat:write` | post the gate prompt, the board summary, and the finished link |
| `channels:history` | read your replies in the `#sales-pulse` thread |

That is the complete list. `channels:read` and `users:read` are deliberately
not requested: the channel ID and user ID are pinned in `slack.env` instead, so
the bot cannot enumerate the workspace.

The bot must be a member of `#sales-pulse`. Slack will not serve channel
history to a bot that is not in the channel, scope or no scope.
