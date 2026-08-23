# Data Definitions

This document defines what every metric on the Sales Pulse dashboard means and how it is calculated. Reference this when reviewing the brief or when something looks off.

## Pipeline taxonomy

### Stages and what they mean

| Section | Meaning | Threshold (days inactive) |
|---|---|---|
| Cold | Lead identified, no qualified conversation yet | 14 |
| Warm | Initial conversation, basic interest established | 14 |
| Qualified | Confirmed fit, budget/authority/timeline understood | 7 |
| Demo | Product demonstration scheduled or completed | 10 |
| Proposal | Pricing or contract under discussion | 14 |
| Stalled | Active deal that has paused for internal reason | 21 |
| Closed Won | Signed customer | n/a |
| Closed Lost | Did not close | n/a |

### Definitions

- **Open** = section is one of {Cold, Warm, Qualified, Demo, Proposal}. Does NOT include Stalled.
- **Stalled** = a deal that was active but has paused. Stays separately tracked because the right move may be to revive OR to close out as Lost.
- **Won** = section is Closed Won.
- **Lost** = section is Closed Lost.

## Revenue definitions

### Subscription ARR

The `Est Subs ARR` custom field. This represents the **annualized recurring revenue** the deal would generate if signed.

- Use the full annual amount, not monthly
- For tiered customers, use the most likely tier
- For partner-channel deals where CellarEye gets a revenue share, use CellarEye's share, NOT the total contract value

### Onboarding revenue

The `Est Onboarding Fees` custom field. This represents **one-time implementation revenue**.

- Includes setup, training, custom configuration, white glove migration
- For partner-channel deals, again use CellarEye's share, NOT the total project value
- A deal can have $0 ARR + significant Onboarding (DTC sale) or significant ARR + low Onboarding (self-serve setup) — both are valid

### Why we separate them

ARR runs the company. Onboarding pays bills today. They are not interchangeable. The dashboard always shows them as separate metrics for that reason.

## Channel definitions

All 8 channels are always displayed on the brief, including any sitting at zero.

| Channel | Short name (Target Accounts cards) | What it means |
|---|---|---|
| Sommelier Program | Somm Program | Sommeliers enrolled through the CellarEye program (lead-heavy channel) |
| Hospitality | Hospitality | Restaurants, hotels, golf clubs, private clubs |
| Sommelier Managed | Somm Managed | Sold to and through professional sommeliers managing client cellars |
| Retailer-Partner | Retailer | Wine retailers, both standalone shops and grocery wine programs |
| Wine Storage | Wine Storage | Storage facilities and logistics partners |
| Cellar Builder | Cellar Builder | Companies who build wine cellars for clients (partner channel) |
| Reserve-Client Direct | Reserve Direct | Direct individual collectors, often Mostafa's network |
| Direct to Consumer | DTC | Individual buyers with no partner or somm intermediary |

Channel field controls implementation/onboarding context. It does NOT determine pricing.

## Time-in-stage rule (Needs Attention)

A deal is flagged for attention when it has been sitting in its current stage longer than the threshold defined for that stage.

**Calculation:** uses Asana's `modified_at` timestamp as the proxy for "last activity."

**Limitation:** `modified_at` updates on ANY edit to the task, not just meaningful sales activity. Updating a phone number resets the clock. This is a v0.5 limitation. v0.6 will add a manual "Last Activity Date" custom field for cleaner signal.

**Fallback rule:** When zero deals meet the threshold, all Stalled deals are surfaced by default. They always need a decision.

**Cap:** Maximum 8 deals shown.

**This rule is canonical.** `SALES_PULSE_BUILD_SPEC.md` section 5 proposes a simplified
"Stalled plus Proposal" list. That is superseded: use the thresholds above. The pull must
therefore request `modified_at` on every task.

**Sort order:**
1. Stalled deals first (decision overdue)
2. Then by stage progression (Proposal → Demo → Qualified → Warm → Cold)
3. Within stage, by Onboarding value descending

## Deal counting

### total_deals_count

`total_deals_count` is the raw number of tasks in the Sales Pipeline project, across all
eight sections:

```
total_deals_count = open + stalled + won + lost
                  = (Cold + Warm + Qualified + Demo + Proposal) + Stalled + Closed Won + Closed Lost
```

Rules:

- **Includes** Stalled, Closed Won and Closed Lost. It is a project total, not a pipeline total.
- **Includes** known duplicates. The count is raw so that the funnel reconciles: the eight
  stage counts must sum to `total_deals_count` exactly. Suppressing duplicates here would
  break that check.
- Duplicates are surfaced in `data_quality_summary` instead, never silently removed.

As of 2026-07-24: 40 open + 3 stalled + 2 won + 6 lost = **51**, of which one is a known
duplicate (see below), so 50 distinct deals.

Note that `data/deal_data_current.json` carries no `stalled` array. It was recovered from the
published brief and that section was lost in recovery, so it totals 48, not 51. The three
Stalled deals are reconstructed in `tests/fixtures/stalled_2026_07_24.json` for the golden
test. The first live pull will supply them properly.

### Known duplicate

Joshua Plack appears twice in Qualified, as `Drink with Me` (onboarding 2250) and
`Plack, Joshua - Drink With Me` (onboarding unset). This inflates Qualified by one.
The two task GIDs must be confirmed against these two task names before any code keys on
them. Until the tasks are merged in Asana, the duplicate is called out in
`data_quality_summary`.

## Data quality flags

The dashboard color-codes data quality on revenue metrics:

- **Green** (positive): ≥80% of deals have the value assigned
- **Gold** (warning): 50-79% of deals have the value assigned
- **Red** (error): <50% of deals have the value assigned

The "DATA QUALITY" alert at the top of the dashboard summarizes the major hygiene issues found in this week's render.

**These thresholds are canonical.** `SALES_PULSE_BUILD_SPEC.md` section 5 proposes a single
40% cutoff. That is superseded: use the three tiers above.

## Loss Reason field (planned for v0.6)

Currently no Loss Reason custom field exists in Asana. The dashboard reads loss context from each Closed Lost deal's notes field, specifically the "Next Step" line carried over from the original Pipeline_2/25 spreadsheet import.

Planned single-select Loss Reason options:
- Price / Pricing structure
- Timing (not now, maybe later)
- Competitor (lost to specific tool)
- No fit / not real ICP
- Lost contact / went dark
- Product Readiness (waiting for features)
- Other

Add this field at: Asana Project > Customize > Add field > single-select. Then back-fill the existing Closed Lost deals.

## Stale Closed Lost detection

A "Closed Lost" deal is flagged as **stale** (potentially mislabeled) when its description contains forward-looking language suggesting it is actually still active. Patterns include:

- "Draft Proposal"
- "in conversation with"
- "wants to test"
- "follow up"
- "next step:" followed by a real action

These deals likely belong in active stages but were moved to Closed Lost prematurely or never updated. Cleanup pass with Danielle is the right next move.

## Pre-revenue context

CellarEye sales motion launches June 1, 2026. Until then, expect:

- **Closed Won counts to remain low** (the existing 2 Won deals are via Meritage reseller, DTC channel)
- **ARR sums to be near zero** even as Onboarding pipeline grows
- **Conversion rates to be unmeasurable** until enough closed cycles exist
- **The dashboard's "Top 3 Priorities" to focus on data hygiene** more than deal motion

This is correct, not a sign of dashboard malfunction.

## Field GIDs reference

For anyone building automation against this project, the relevant Asana GIDs:

**Project:** `1214587430477572`

**Sections:**
- Cold: `1214587157612922`
- Warm: `1214587157150176`
- Qualified: `1214601903352407`
- Demo: `1214587431234795`
- Proposal: `1214587336363810`
- Stalled: `1214588235873011`
- Closed Won: `1214587336732857`
- Closed Lost: `1214587364624571`

**Custom fields:**
- Channel: `1214587337205105`
- First Name: `1214587337205112`
- Last Name: `1214587337205114`
- Email Address: `1214587337205116`
- Phone Number: `1214587337205118`
- Street Address: `1214587337205120`
- State: `1214587337205122`
- Zip Code: `1214587337205124`
- Cellar Size: `1214587337205126`
- Cellars Managed: `1214587637337214`
- Est Subs ARR: `1214587637337216`
- Onboarding Path: `1214587637337218`
- Est Onboarding Fees: `1214587637337223`
- Expected Close: `1214587637337225`
- Onboarding Date: `1214587637337227`
- Website: `1214586791774168`

**Channel option GIDs:**
- Sommelier Managed: `1214587337205106`
- Reserve-Client Direct: `1214587337205107`
- Cellar Builder: `1214587337205108`
- Hospitality: `1214587337205109`
- Wine Storage: `1214588235873023`
- Retailer-Partner: `1214588439226165`
- Sommelier Program: `1216016965299601`
- Direct to Consumer: **TBD, look up at build time.** The Channel enum reports 8 options
  but only 7 GIDs have been captured. `pull_asana.py` must resolve this one live and
  this line must be filled in before the first real run.
