# cellareye-sales-pulse
CellarEye Sales Pulse — weekly pipeline brief generated from Asana data. Static HTML dashboard delivered to Slack via Zapier.
# CellarEye Sales Pulse

Weekly pipeline brief generated from live Asana data. Static HTML dashboard intended for delivery to the CellarEye team via Slack.

## What this repo contains

```
cellareye-sales-pulse/
├── prompt/
│   └── sales_pulse_prompt.md     # Instructions for Claude when generating the brief
├── templates/
│   └── sales_pulse.html           # The dashboard template with placeholder tokens
├── output/
│   └── sales_pulse_YYYY-MM-DD.html # Snapshot of each rendered brief
├── docs/
│   └── data_definitions.md        # What every metric means and how it's calculated
└── README.md                       # This file
```

## How the system works

```
Apple Shortcut on iPhone or Mac
    ↓
Sends prompt to Claude (with link to this repo)
    ↓
Claude reads prompt/sales_pulse_prompt.md
    ↓
Claude pulls live data from Asana via MCP
    ↓
Claude reads templates/sales_pulse.html
    ↓
Claude calculates metrics, fills in placeholders
    ↓
Claude returns the rendered HTML
    ↓
You (Mark) review, then Share → Slack → #sales-pulse channel
```

## Why this architecture

- **You control timing.** No cron firing while you're traveling or asleep.
- **You quality-check before the team sees it.** Catches bad data before broadcast.
- **Template and prompt are version-controlled.** Changes to either are reviewable diffs, not invisible drift.
- **No infrastructure to maintain.** No GitHub Actions, no Cowork, no Zapier. Apple Shortcut + Claude does the whole thing.
- **Mirrors the existing daily brief pattern** that already works for LGV.

## What changes when

| File | How often it changes | Who changes it |
|---|---|---|
| `templates/sales_pulse.html` | Rarely (when redesigning the dashboard) | Mark + Claude in conversation |
| `prompt/sales_pulse_prompt.md` | Occasionally (when adjusting metrics or rules) | Mark + Claude in conversation |
| `output/sales_pulse_*.html` | Weekly (each render) | Generated automatically |
| `docs/data_definitions.md` | When data taxonomy evolves | Mark + Danielle as data hygiene improves |

## Cadence

- **Weekly Friday afternoon:** Run the brief, share to Slack
- **Monthly:** Review dashboard structure for needed tweaks
- **Quarterly:** Review whether dashboard is still serving its purpose, or whether something different is needed

## Data quality philosophy

The dashboard surfaces missing data rather than hiding it. If only 17 of 32 Open deals have Onboarding values assigned, the dashboard says "17 of 32 · 53% complete" in red text. **You can't clean up data you can't see.** The intent is to make data hygiene visible enough that it gets done.

Over time, as Mark and Danielle clean up the underlying Asana data (adding ARR estimates, capturing Loss Reasons, fixing stale Closed Lost classifications), the dashboard will naturally improve in fidelity.

## Versions

- **v0.5** (2026-05-06): Initial three-row Open/Won/Lost structure, manual render via Claude conversation
- **v1.0** (planned): Apple Shortcut + Claude integration replacing manual conversation
- **v2.0** (planned): Add Loss Reason and Stall Reason custom fields, add Last Activity Date manual field for cleaner threshold logic

## Setup notes for Apple Shortcut (planned)

When building the Shortcut:

1. Action: "Get Contents of URL" → fetch this repo's prompt at `https://raw.githubusercontent.com/marklainsworth/cellareye-sales-pulse/main/prompt/sales_pulse_prompt.md`
2. Action: Send to Claude (via Claude.ai app or API)
3. Action: Receive response (HTML file)
4. Action: Open Share Sheet → user selects Slack → #sales-pulse channel

Same pattern as the existing LGV daily brief Shortcut.

## Related infrastructure

- **Asana project:** [CellarEye Sales Pipeline](https://app.asana.com/1/1214587766552282/project/1214587430477572)
- **Slack channel:** `#sales-pulse` (CellarEye workspace)
- **HubSpot:** System of record for customer data
- **LGV Daily Brief automation:** `marklainsworth/lgv-ops` repo (reference architecture)

## Maintained by

Mark Ainsworth, CEO CellarEye Inc.
mark@cellareye.com
