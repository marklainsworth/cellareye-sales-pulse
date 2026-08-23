# CellarEye Sales Pulse — Claude Code Build Spec

Build spec for moving the weekly Sales Pulse brief out of chat and into an automated Claude Code pipeline, modeled on the working LGV Daily Brief setup.

Author: Mark Ainsworth (CEO, CellarEye)
Last updated: July 25, 2026
Target repo: `github.com/marklainsworth/cellareye-sales-pulse`

---

## 1. What we are building

A Claude Code pipeline that generates the weekly CellarEye Sales Pulse brief, with one human gate and one authored input:

1. **Friday 3:00pm** — CC prompts: "Board updated and ready to run the Pulse?"
2. Mark reviews Asana. If not ready, he takes ~15 min to update the board, then answers yes.
3. On **yes**, CC asks for the **MD&A commentary** (a few sentences: what moved this week, what is top of mind). This is the one input that cannot be pulled from Asana.
4. CC then runs fully automatically:
   - Pulls both Asana projects **at the moment of confirmation** (not at 3:00 — a fresh pull so the 15-minute updates land)
   - Renders the dated brief from the template
   - Runs integrity checks
   - Commits and pushes `briefs/YYYY-MM-DD.html` (and the template if changed) to GitHub
   - The existing GitHub Action mirrors the newest dated brief to `briefs/latest.html`
   - Posts a notification to Slack and/or texts Danielle with the live link (notification, NOT a gate)

### Design principles (do not violate)

- **One gate, one owner.** Only Mark certifies "the board is true." Do not add a second approval gate (e.g. Danielle). Danielle gets a notification after publish, not a vote before it.
- **Fresh pull on confirm.** Pull Asana when Mark hits yes, never cache the 3:00 snapshot.
- **MD&A is authored, never stale.** The commentary is captured fresh each run. If left blank, the brief must say "commentary pending" — never reprint last week's narrative.
- **The gate is load-bearing.** The "yes" only protects the brief if the board is actually current. Prompt wording should remind Mark what yes means.
- **No em dashes** anywhere in Mark-visible copy. Use commas, periods, or parentheses.
- **Calm authority voice.** Confident, collaborative, surface urgency without proving it. Mark is a stabilizer, not a critic. Honest "data is inherited" framing, never "prior regime."

---

## 2. Repo structure to build

```
cellareye-sales-pulse/
├── templates/
│   └── sales_pulse.html          # master template with {{placeholders}} (v0.12 — provided)
│   └── logo.png                  # CellarEye logo (already in repo)
├── briefs/
│   ├── YYYY-MM-DD.html           # weekly dated archive (generated)
│   └── latest.html               # stable Slack-pinned URL (Action mirrors newest dated brief here)
├── pipeline/
│   ├── render.py                 # the renderer (spec in section 5)
│   ├── pull_asana.py             # fetches both Asana projects, writes data JSON (spec in section 4)
│   ├── run.py                    # orchestrator: prompt gate, MD&A capture, pull, render, commit, notify
│   └── config.py                 # GIDs, field IDs, channel taxonomy (spec in section 3)
├── data/
│   ├── deal_data_current.json    # last pull (regenerated each run)
│   └── lead_data_current.json    # last pull (regenerated each run)
├── .github/workflows/
│   └── update-latest.yml         # EXISTS — mirrors newest dated brief to latest.html
└── SALES_PULSE_BUILD_SPEC.md     # this file
```

The current working `render.py` logic, the v0.12 template, and today's recovered data JSON are provided alongside this spec. Start from those, do not rebuild from scratch.

---

## 3. config.py — IDs and taxonomy

All Asana GIDs and custom field IDs, verified live July 24, 2026.

### Projects
- Sales Pipeline project: `1214587430477572`
- Inbound Leads project: `1216056878497593`

### Sales Pipeline sections (stage = section membership)
| Stage        | Section GID          |
|--------------|----------------------|
| Cold         | `1214587157612922`   |
| Warm         | `1214587157150176`   |
| Qualified    | `1214601903352407`   |
| Demo         | `1214587431234795`   |
| Proposal     | `1214587336363810`   |
| Stalled      | `1214588235873011`   |
| Closed Won   | `1214587336732857`   |
| Closed Lost  | `1214587364624571`   |

### Sales Pipeline custom fields
| Field            | GID                  | Notes |
|------------------|----------------------|-------|
| Channel          | `1214587337205105`   | enum, 8 options (see below) |
| First name       | `1214587337205112`   | text |
| Last name        | `1214587337205114`   | text |
| Email            | `1214587337205116`   | text |
| Phone            | `1214587337205118`   | text |
| Cellar size      | `1214587337205126`   | enum (0-2,500 / 2,501-5,000 / 5,001-10,000 / 10,001 above) |
| Clients          | `1214587637337214`   | number |
| ARR              | `1214587637337216`   | number |
| Onboarding Path  | `1214587637337218`   | enum (e.g. "Path A \| CellarEye") |
| Onboarding value | `1214587637337223`   | number |
| Website          | `1214586791774168`   | text (not on all tasks) |
| Business name    | `1216016965299619`   | text |

### Channel enum option GIDs (Sales Pipeline)
| Channel               | Option GID           |
|-----------------------|----------------------|
| Sommelier Managed     | `1214587337205106`   |
| Reserve-Client Direct | `1214587337205107`   |
| Cellar Builder        | `1214587337205108`   |
| Hospitality           | `1214587337205109`   |
| Retailer-Partner      | `1214588439226165`   |
| Wine Storage          | `1214588235873023`   |
| Sommelier Program     | `1216016965299601`   |

### Inbound Leads project
- Sections: "Ready To Email" (`1216056878497594`), "Linkedin Outreach" (`1216607644993202`)
- Channel field on leads: `1214587337205105` (same field, 8 enum options)
- As of 7/24: 104 leads total — 86 Sommelier Program, 18 Hospitality, 0 in the other 6 channels

### Full channel taxonomy (always display all 8, even at 0)
Sommelier Program, Hospitality, Sommelier Managed, Retailer-Partner, Wine Storage, Cellar Builder, Reserve-Client Direct, Direct to Consumer

Short display names used in Target Accounts cards: Somm Program, Hospitality, Somm Managed, Retailer, Wine Storage, Cellar Builder, Reserve Direct, DTC

### Slack
- Delivery channel for notification: reuse the daily-brief pattern. #daily-brief is `C0ANTSCM4SV`; create or choose a sales channel as preferred.

---

## 4. pull_asana.py — data fetch

Fetches both projects and writes `data/deal_data_current.json` and `data/lead_data_current.json`.

### Deal pull
- Get all tasks in Sales Pipeline project `1214587430477572` with opt_fields:
  `name, memberships.section.gid, memberships.section.name, custom_fields.gid, custom_fields.enum_value.name, custom_fields.number_value, custom_fields.display_value`
- 50+ tasks, single page (limit 100).
- For each task derive: name, stage (from section), channel, arr, onb, first, last, notes.
- Note: the Asana MCP does not return the task `notes`/description in the bulk list reliably. The current chat-based renderer carries hand-maintained notes per deal. **Decision needed at build:** either (a) pull notes per-task with `get_task` (50 extra calls, slow), or (b) keep a `deal_notes.json` override file keyed by task GID that Mark maintains. Recommend (b) — notes change rarely and are curated copy.

### Lead pull
- Get all tasks in Inbound Leads project `1216056878497593` with opt_fields:
  `name, custom_fields.gid, custom_fields.enum_value.name, memberships.section.name`
- 104 tasks. Paginate if needed (limit 100 returns 100; grab the last page for the final 4).
- For each: business (task name), channel, section. First/last name are parsed from the task or a linked contact — current data has them; confirm field mapping at build.

### Output shape
`deal_data_current.json`:
```json
{
  "open":  [{"name","first","last","channel","arr","onb","stage","notes"}, ...],
  "won":   [...],
  "lost":  [...]
}
```
Open deals sorted by stage order (Cold, Warm, Qualified, Demo, Proposal) then onboarding value descending. Won/Lost sorted by onboarding descending.

`lead_data_current.json`:
```json
[{"business","first","last","channel","section"}, ...]
```

### MCP note
Asana, Gmail, Google Calendar, Slack, Granola tools are **deferred** — they require `tool_search` before first invocation in each session. The daily-brief pipeline already handles this pattern; reuse it.

---

## 5. render.py — the renderer

Pure function: reads the template + the two data JSON files + the MD&A commentary + the render date, writes `briefs/YYYY-MM-DD.html`. No network calls. This keeps rendering testable and separate from the pull.

### Inputs
- `templates/sales_pulse.html`
- `data/deal_data_current.json`, `data/lead_data_current.json`
- MD&A commentary string (from the orchestrator prompt)
- render date (the current Friday)
- pull timestamp (when the Asana pull ran)

### What it computes
- **Stage counts** for the funnel (8 stages), with fill % = count / max count.
- **Open metrics:** total open deals, ARR sum + fill ratio, onboarding sum + fill ratio. DQ class = "warning" if ≥40% filled else "error".
- **Won metrics:** count, ARR sum, avg onboarding, onboarding sum.
- **Lost metrics:** count, ARR sum, onboarding sum + valued count.
- **Channels (open only):** per-channel deal count, onboarding total, valued ratio. Sorted by deal count desc.
- **Target Accounts:** per-channel lead counts (all 8 channels, zeros shown), total, added-this-week, qualified-this-week, qual rate. Leader card = highest count. Clickable cards get `data-view="ta-<channelslug>"` where slug = channel full name lowercased, non-alphanumerics stripped.
- **Deals needing attention:** Stalled deals + Proposal deals, formatted as rows.
- **Priorities:** 3 items (title + why). These are currently authored. **Decision:** either fold priorities into the MD&A capture (Mark writes them at run time) or keep a rotating default. Recommend capturing at run time alongside MD&A — they are judgment, not data.

### Template mechanics
- 81 placeholders total. Scalar `{{name}}` and loop blocks `{{#loop}}...{{/loop}}`.
- Loops: `{{#ta_channels}}`, `{{#priorities}}`, `{{#channels}}`, `{{#attention_deals}}`.
- Deal drill-down data is injected into `<script id="dealData">` as JSON.
- Lead drill-down data is injected into `<script id="leadData">` as JSON via `{{lead_data_json}}`.
- Prepend a pull-timestamp HTML comment at the very top of every render.

### Full placeholder list
render_date_long, version_stamp, render_time, total_deals_count, company_stage_label, company_stage_text, launch_countdown, open_count, open_subtext, open_arr, open_arr_dq, open_arr_dq_class, open_onb, open_onb_dq, open_onb_dq_class, won_count, won_arr, won_avg, won_onb, won_onb_dq, lost_count, lost_subtext, lost_arr, lost_arr_subtext, lost_onb, lost_onb_subtext, cold_leader_class, channel_count, data_quality_summary, ta_meta, ta_total, ta_total_subtext, ta_added, ta_added_subtext, ta_qualified, ta_qual_class, ta_qual_subtext, ta_qual_rate, ta_rate_class, ta_rate_subtext, lead_data_json, plus stage_{cold,warm,qualified,demo,proposal,stalled,won,lost}_{count,fill}, plus loop vars (ch_name, ch_count, ch_added, ch_qual, ch_fill_pct, leader_class, zero_class, ta_clickable, ta_data_view / priority_title, priority_why / channel_name, channel_deals, channel_onb, channel_onb_class, channel_valued / deal_name, deal_contact, deal_signal, deal_meta).

`company_stage_text` is where the MD&A commentary goes. `company_stage_label` stays "Pre-Revenue · Discovery Phase" until revenue changes it.

### The discovery-phase website is cellareye.com (not .io).

---

## 6. run.py — orchestrator

The interactive entry point Mark invokes from phone/iPad/desktop.

```
1. Prompt: "Board updated and ready to run the Pulse? (yes / not yet)"
   - "not yet"  -> stand down cleanly, no partial files, exit.
   - "yes"      -> continue.
2. Prompt: "MD&A commentary for this week (a few sentences: what moved, what's top of mind):"
   - capture multiline input.
   - Optionally prompt for the 3 priorities here too.
   - If blank -> set company_stage_text to "Commentary pending." (never reuse last week).
3. Run pull_asana.py  (FRESH pull, now — not at 3:00).
4. Run render.py with today's Friday date + captured MD&A.
5. Integrity checks (section 7). Abort + report if any fail.
6. git add briefs/YYYY-MM-DD.html (+ template if changed); commit; push to main.
7. Wait for Action to mirror latest.html (or mirror locally and push).
8. Notify: post to Slack + text Danielle with the live latest.html link. NOTIFICATION ONLY.
9. Print the live URL and a one-line summary (counts, ARR, what moved).
```

### Scheduling
- Trigger the "ready?" prompt at Friday 3:00pm PT. On the always-on Mac Air, mirror the daily-brief approach (launchd, or an Apple Shortcut "Run the Pulse"). The daily brief uses launchd 5am weekday; this is a weekly Friday 15:00 job.
- Because the flow is interactive (needs Mark's yes + MD&A), the schedule kicks off the *prompt*, then waits for Mark. It does not run headless end to end — that is by design (the gate).

### Git identity
The Mac Air already has git configured for the lgv-ops pushes. Reuse the same credentials/SSH for cellareye-sales-pulse. Confirm the remote and branch (main).

---

## 7. Integrity checks (run before commit, abort on failure)

These are the checks currently done by hand each week. Automate them:

1. **No unresolved placeholders:** `grep -o '{{[^}]*}}'` returns nothing.
2. **No en-dash corruption:** the string `var(<en-dash>` must not appear (iPad Safari smart-punctuation bug — less relevant now that CC writes the file, but keep the check). Also scan for en-dashes in CSS `var()` calls generally.
3. **No smart quotes in CSS:** `content: <curly-quote>` must not appear; use straight quotes.
4. **Deal counts reconcile:** funnel stage counts sum to total; open count = Cold+Warm+Qualified+Demo+Proposal; dealData JSON lengths match metric counts.
5. **Valid JSON:** dealData and leadData script blocks parse.
6. **Lead total matches:** Target Accounts total = len(leadData).
7. **Date is the current Friday.**
8. **MD&A present** (or explicitly "Commentary pending").

If any check fails, do not commit. Print what failed.

---

## 8. Known history / gotchas (so CC does not repeat them)

- **Container/state resets** are why we are moving to the repo. Everything must live as committed files, not in a chat session.
- **The template drifted** in chat because hardcoded values from different renders got baked in. The v0.12 template is fully placeholder-driven — keep it that way. Never hardcode a metric into the template.
- **iPad Safari smart punctuation** historically mangled pastes (en-dashes in `var(--ink)`, curly quotes in CSS `content`). CC writing files directly avoids this, but the integrity checks guard against regressions.
- **Proposal section** was dropped from an earlier pull's opt_fields and caused a mis-render. Always pull `memberships.section.gid` explicitly.
- **Joshua Plack duplicate** exists in Qualified (two tasks, GIDs `1214588513835040` and `1215968666300621`) — needs merging in Asana; until then it inflates Qualified by 1. Flag in data_quality_summary.
- **Layout is correct as published** in `briefs/2026-07-17.html` (verified byte-identical CSS to current). Do not "improve" the layout during the build — match what is published.
- **Friday cadence, Mark's byline.** The review gate is the leadership moment. Do not automate it away.

---

## 9. Build order (suggested)

1. Commit the provided files (v0.12 template, current render.py logic, recovered data JSON) into the structure in section 2.
2. Build `config.py` from section 3.
3. Build `pull_asana.py` (section 4). Test: run it, diff output against `deal_data_current.json` / `lead_data_current.json` — should closely match.
4. Refactor `render.py` (section 5) to read from config + data files + MD&A arg. Test: render, compare to `briefs/2026-07-24.html`.
5. Build integrity checks (section 7) as a module both render and run call.
6. Build `run.py` orchestrator (section 6) — start with everything except commit/notify, verify the file is correct, then wire git push, then wire Slack/text.
7. Schedule the Friday 3pm prompt.
8. Dry-run one full cycle with Mark before trusting it.

---

## 10. Future / deferred

- Bubble chart of deals (ARR vs onboarding) once ARR data is denser.
- MD&A could pull a first draft from Granola meeting notes for Mark to edit, rather than blank capture.
- Qualified-this-week tracking: a lead "qualifies" when its Inbound Leads task also gets added to the Sales Pipeline project (tasks live on both boards). Compute added/qualified-this-week by comparing this pull's lead set to last pull's (store previous pull for diff).
