# Credentials

Every `*.env` in this directory is gitignored. Place them by hand on the Air,
via terminal. Never paste a token into a chat session: it lands in the
transcript and has to be rotated.

| File | Holds | Where it comes from |
|---|---|---|
| `asana.env` | `ASANA_TOKEN` | Asana > Settings > Apps > Developer > Personal access token |
| `slack.env` | `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`, `SLACK_USER_ID` | see `slack.env.example` |

## Slack, one thing to be careful about

The Pulse reuses the existing `lgv_daily_brief` app rather than creating a new
one. Adding the `channels:history` scope requires reinstalling the app, and
**reinstalling issues a new bot token and invalidates the old one**.

The daily brief authenticates with that token. So after reinstalling:

1. Copy the new `xoxb-` token into BOTH
   `lgv-ops/config/slack.env` and `cellareye-sales-pulse/config/slack.env`.
2. Run the daily brief's dry run and confirm it still posts, before walking away.

Miss step 1 and the 5am brief fails silently the next morning.
