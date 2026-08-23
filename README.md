# CellarEye Sales Pulse

Weekly pipeline brief generated from live Asana data, rendered to static HTML and published to GitHub.

Pipeline version: see [`VERSION`](VERSION). That file is the single source of truth for the version stamp shown in the brief header and footer.

## Repo layout

```
cellareye-sales-pulse/
├── VERSION                        # single pipeline version line
├── SALES_PULSE_BUILD_SPEC.md      # build spec for the automated pipeline
├── templates/
│   ├── sales_pulse.html           # master template, fully placeholder-driven
│   └── logo.png
├── pipeline/                      # (being built)
│   ├── config.py                  # GIDs, taxonomy, thresholds
│   ├── pull_asana.py              # fetches both projects -> data/*.json
│   ├── render.py                  # pure renderer, no network
│   ├── checks.py                  # integrity checks
│   └── run.py                     # orchestrator (two prompts, then automatic)
├── data/
│   ├── deal_data_current.json     # last pull: {open, stalled, won, lost}
│   └── lead_data_current.json     # last pull: flat list of leads
├── briefs/
│   ├── YYYY-MM-DD.html            # weekly dated archive
│   └── latest.html                # stable Slack-pinned URL
├── docs/data_definitions.md       # metric source of truth
├── prompt/sales_pulse_prompt.md   # superseded chat-based renderer, kept for reference
└── .github/workflows/update-latest.yml
```

## How the system works

```
Friday 3:00pm PT, scheduled job fires the prompt
    ↓
1. "Are we ready?"          Mark reviews the Asana board. Not ready -> stand down cleanly.
    ↓ yes
2. "MD&A?"                  Mark writes the week's commentary (multiline).
    ↓ then fully automatic
Fresh Asana pull, now (not the 3:00 snapshot)
    ↓
render.py fills templates/sales_pulse.html
    ↓
Integrity checks. Any failure aborts before commit.
    ↓
Commit and push briefs/YYYY-MM-DD.html
    ↓
GitHub Action mirrors the newest dated brief to briefs/latest.html
    ↓
Slack notification with the live link (notification, not a gate)
```

There are exactly two prompts. Everything after the MD&A capture runs without further input.

## Design principles

- **One gate, one owner.** Only Mark certifies that the board is true. No second approval gate.
- **Fresh pull on confirm.** Asana is pulled when Mark answers yes, never from the 3:00 snapshot.
- **MD&A is authored, never stale.** Captured fresh each run. If blank, the brief says "Commentary pending." It never reprints last week.
- **The template holds no data.** Every metric is a placeholder. Hardcoding a value into the template is how the previous version drifted.
- **Missing data is shown, not hidden.** If 17 of 40 open deals have ARR, the brief says so in red. You cannot clean up data you cannot see.
- **No em dashes** in Mark-visible copy. Commas, periods, parentheses, or the middle dot.

## The MD&A block

One commentary block per week covers both what moved and what we are doing about it. It is not split into a separate priorities prompt.

The leading prose lands in the banner. If the commentary contains numbered lines, those are lifted into the "Priorities · This Week" list at the foot of the brief. Write numbered items to get the numbered visual; write plain prose to skip that section entirely.

## What changes when

| File | How often | Who |
|---|---|---|
| `templates/sales_pulse.html` | Rarely, on redesign | Mark + Claude |
| `pipeline/*.py` | Occasionally, on rule changes | Mark + Claude |
| `docs/data_definitions.md` | When taxonomy evolves | Mark + Danielle |
| `data/*.json` | Every run, regenerated | Automatic |
| `briefs/*.html` | Weekly | Automatic |

## Cadence

- **Weekly, Friday afternoon:** run the Pulse, notification posts to Slack.
- **Monthly:** review dashboard structure.
- **Quarterly:** review whether the brief still serves its purpose.

## Related

- **Asana Sales Pipeline:** https://app.asana.com/1/1214587766552282/project/1214587430477572
- **Asana Inbound Leads:** project `1216056878497593`
- **Reference architecture:** `marklainsworth/lgv-ops` (LGV daily brief)
- **Website:** cellareye.com

## Maintained by

Mark Ainsworth, CEO CellarEye Inc. mark@cellareye.com
