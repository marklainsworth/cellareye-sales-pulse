# CellarEye Sales Pulse — Generation Prompt

You are generating the weekly Sales Pulse dashboard for CellarEye, a wine inventory SaaS company. This is a serious, version-controlled artifact. Follow the instructions exactly.

## Your job

1. **Pull live pipeline data** from the Asana project "CellarEye Sales Pipeline" (GID: `1214587430477572`)
2. **Calculate the metrics** defined below
3. **Read the template** from this repository at `templates/sales_pulse.html`
4. **Substitute placeholder tokens** with calculated values
5. **Output the rendered HTML** as a single complete file
6. **Do NOT modify the template structure, layout, CSS, or design.** Only fill in placeholders.

## Critical constraint

**Do not make design decisions.** The template is the single source of truth for layout, colors, typography, and structure. Your job is mechanical substitution. If you find yourself wanting to "improve" the template, stop — file an issue in the repo instead, and render the brief with the current template unchanged.

If a metric is missing data, fill the placeholder with the documented fallback value (see below). Do not hide sections, omit metrics, or restructure the output to "look better" with sparse data. **Showing missing data honestly is the point.**

## Data source

**Asana Project:** CellarEye Sales Pipeline
- **GID:** `1214587430477572`
- **URL:** https://app.asana.com/1/1214587766552282/project/1214587430477572

**Sections (with GIDs):**
- Cold: `1214587157612922`
- Warm: `1214587157150176`
- Qualified: `1214601903352407`
- Demo: `1214587431234795`
- Proposal: `1214587336363810`
- Stalled: `1214588235873011`
- Closed Won: `1214587336732857`
- Closed Lost: `1214587364624571`

**Custom field GIDs:**
- Channel: `1214587337205105` (single-select)
- Est Subs ARR: `1214587637337216` (number)
- Est Onboarding Fees: `1214587637337223` (number)
- First Name: `1214587337205112`
- Last Name: `1214587337205114`

**Channel option GIDs:**
- Sommelier Managed: `1214587337205106`
- Reserve-Client Direct: `1214587337205107`
- Cellar Builder: `1214587337205108`
- Hospitality: `1214587337205109`
- Wine Storage: `1214588235873023`
- Retailer-Partner: `1214588439226165`

## Definitions

**Open** = section in {Cold, Warm, Qualified, Demo, Proposal}. Stalled is NOT open.
**Won** = section = Closed Won.
**Lost** = section = Closed Lost.

**ARR** = the `Est Subs ARR` custom field. Subscription revenue, recurring annually. Sum across all deals of interest.
**Onboarding** = the `Est Onboarding Fees` custom field. One-time implementation revenue. Sum across all deals of interest.

**Days in stage** = approximated using `modified_at` timestamp (the proxy for "last activity"). When a real "Stage Entered Date" custom field is added (v0.6+), switch to that.

## Needs Attention rule

A deal appears in "Needs Attention" when **either** of these is true:

1. **Time threshold exceeded** based on current section:
   - Cold: > 14 days since `modified_at`
   - Warm: > 14 days
   - Qualified: > 7 days
   - Demo: > 10 days
   - Proposal: > 14 days
   - Stalled: > 21 days

2. **Fallback rule:** If zero deals meet the threshold, show all Stalled deals (they need a decision: revive or move to Lost).

**Sort order:** Stalled deals first (decision needed), then by stage progression (Proposal → Demo → Qualified → Warm → Cold), then within stage by onboarding value descending.

**Cap:** 8 deals maximum.

**For each shown deal, extract a "meta_line" that combines:**
- The Channel name
- A summary of the "Next Step" line from the task notes (or comments if more recent)
- If notes/comments are empty, use "no recent context recorded"

## Placeholder reference

Every placeholder token in the template, with its data type and source:

### Header / banner
- `{{render_date_long}}` — e.g., "Wednesday, May 6"
- `{{version_stamp}}` — e.g., "v0.5 · Live Data"
- `{{render_time}}` — e.g., "23:55 PT"
- `{{total_deals_count}}` — count of all tasks in project
- `{{company_stage_label}}` — e.g., "Pre-Revenue · Discovery Phase"
- `{{company_stage_text}}` — full sentence describing stage
- `{{launch_countdown}}` — e.g., "T-26 days" (count days from today to 2026-06-01)

### OPEN row metrics
- `{{open_total_count}}` — count of Open deals (not Stalled, not Won, not Lost)
- `{{open_total_subtext}}` — e.g., "across 5 stages · 6 channels" (count active stages and channels)
- `{{open_arr_total_formatted}}` — sum of ARR on Open deals, formatted as "$X,XXX" (no decimals, with thousands commas). If sum is 0, render as "$0".
- `{{open_arr_value_class}}` — CSS class. Use `muted-value` if Open ARR sum is $0 (visually deemphasized). Otherwise empty string.
- `{{open_arr_dq_text}}` — e.g., "17 of 32 · 53% complete"
- `{{open_arr_dq_class}}` — CSS class for data quality text:
  - `positive` if ≥80% complete
  - `warning` if 50-79%
  - `error` if <50%
- `{{open_conversion_value}}` — Conversion rate Cold→Qualified. If <30 days of closed cycles available, render "—".
- `{{open_conversion_subtext}}` — e.g., "trailing 30 days" or "no closed cycles yet"
- `{{open_onboarding_total_formatted}}` — sum of Onboarding on Open deals, formatted as "$X,XXX"
- `{{open_onb_dq_text}}` — e.g., "17 of 32 · 53% complete"
- `{{open_onb_dq_class}}` — same logic as `open_arr_dq_class`

### WON row metrics
- `{{won_count}}` — count of Closed Won deals
- `{{won_subtext}}` — short context, e.g., "via Meritage reseller" if a pattern exists, otherwise blank
- `{{won_arr_total_formatted}}` — sum of ARR on Won deals, formatted "$X,XXX"
- `{{won_arr_value_class}}` — `muted-value` if $0
- `{{won_arr_subtext}}` — e.g., "DTC · no recurring yet" or "X% of total"
- `{{won_avg_deal_formatted}}` — average deal size by Onboarding (sum / count), "$X,XXX". If 0 won deals, "—".
- `{{won_avg_subtext}}` — e.g., "Manny + Ron Montbleau" listing the deals
- `{{won_onboarding_total_formatted}}` — sum of Onboarding on Won deals
- `{{won_onb_dq_text}}` — e.g., "2 of 2 · 100% complete"
- `{{won_onb_dq_class}}` — same logic as above

### LOST row metrics
- `{{lost_count}}` — count of Closed Lost deals
- `{{lost_subtext}}` — short pattern, e.g., "3 Sorrells partnerships" if pattern exists
- `{{lost_arr_total_formatted}}` — sum of ARR on Lost deals
- `{{lost_arr_value_class}}` — `muted-value` if $0
- `{{lost_arr_subtext}}` — e.g., "none assigned to lost"
- `{{lost_top_reason}}` — most common Loss Reason from custom field. If field doesn't exist or majority blank, render "Not tracked" or "X of Y blank · Z stale" if checking notes shows mixed state.
- `{{lost_reason_dq_class}}` — `error` if no Loss Reason field exists or >50% blank
- `{{lost_reason_subtext}}` — e.g., "add field to Asana" or "all 6 need cleanup pass"
- `{{lost_onboarding_total_formatted}}` — sum of Onboarding on Lost deals
- `{{lost_onb_subtext}}` — e.g., "5 of 6 · Sorrells & Four Seasons"

### Data quality alert
- `{{data_quality_summary}}` — one paragraph summarizing the major data hygiene issues found. Mention ARR completeness, Onboarding completeness, Loss Reason availability, and any Closed Lost deals that read as active in their notes.

### Funnel (8 stages)
- `{{stage_cold_count}}`, `{{stage_warm_count}}`, etc. — counts per section
- `{{stage_cold_fill_pct}}`, etc. — visual bar width as percentage. Calculate as `(stage_count / max_stage_count) * 100`, rounded to integer.

### Channels
The `{{#channels}}...{{/channels}}` block iterates. Build an array sorted by deal count descending. For each channel:
- `{{channel_name}}` — e.g., "Retailer-Partner"
- `{{deal_count}}` — number of Open deals in this channel
- `{{onboarding_total_formatted}}` — sum of Onboarding for this channel's Open deals, formatted as "$X" or "$XK" (use K if ≥$1000)
- `{{onboarding_value_class}}` — `muted` if $0
- `{{valued_ratio}}` — e.g., "6/6" or "0/10"

### Channel meta
- `{{channels_with_deals_count}}` — count of channels with at least 1 Open deal

### Needs Attention
The `{{#needs_attention_deals}}...{{/needs_attention_deals}}` block iterates over the deals matching the rule.
- `{{needs_attention_meta}}` — e.g., "Top 5 by Stage Velocity" if threshold hits exist, or "No Threshold Hits · Showing Stalled" if fallback fired
- For each deal:
  - `{{deal_name}}` — task name
  - `{{contact_name}}` — first + last name from custom fields. If missing, omit the contact span entirely (template uses Mustache section conditional `{{#contact_name}}...{{/contact_name}}`).
  - `{{signal_class}}` — `hot`, `warm`, or `cold` based on urgency (Stalled = warm, Proposal stuck = warm, Demo with movement = hot)
  - `{{signal_text}}` — e.g., "Stalled · $15K onb" or "Demo · $200K onb"
  - `{{meta_line}}` — channel + Next Step context

### Rule logic explainer
- `{{rule_logic_explainer}}` — short paragraph explaining WHY the deals shown are shown. Different copy depending on whether threshold hits or fallback fired. Always mention thresholds (Cold/Warm 14d, etc.).

### Priorities
The `{{#priorities}}...{{/priorities}}` block iterates over exactly 3 priorities. Generate these dynamically based on what the data reveals as most important THIS week. For each:
- `{{title}}` — short imperative title
- `{{why}}` — 1-2 sentence rationale grounded in actual data

Priorities should change week to week as the underlying data changes. Don't reuse priorities verbatim from the previous week's brief.

### Footer
- `{{footer_meta}}` — e.g., "Source: Asana CellarEye Sales Pipeline · Manual render · v0.5"

## Output format

Return the complete rendered HTML as a single file. No markdown code fences. No commentary before or after. The output should be valid HTML that opens directly in a browser.

If you cannot complete the render for any reason (Asana data unavailable, template missing, etc.), return a brief error message in plain text instead. Do not return a partial or fabricated dashboard.

## Version

This prompt is v1.0. When updating the prompt, increment the version and document the change at the top of this file.
