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
- A summary of the "Next Step" line from the task notes (or comme
