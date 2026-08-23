# Build Decisions

Resolved decisions from the build-spec review, August 23 2026. Where this file disagrees
with `SALES_PULSE_BUILD_SPEC.md`, this file wins. The spec is the original brief, this is
the record of what we actually settled on.

## Template

| # | Decision |
|---|---|
| 1 | `dealData` was a hardcoded 41-deal blob baked into v0.12. Replaced with `{{deal_data_json}}`, mirroring the lead block. |
| 5 | Conversion C→Q and the footer version were hardcoded. Now `{{conversion_c_q}}`, `{{conversion_subtext}}`, `{{footer_meta}}`. |
| — | Three further hardcodes found and fixed, same defect class: the RULE LOGIC paragraph (`{{rule_logic_explainer}}`), the attention panel meta (`{{attention_meta}}`), and `class="signal warm"` on every attention row (`{{deal_signal_class}}`, which had made the hot and cold states unreachable). |
| — | `launch_countdown` retired. Placeholder and countdown div removed, June 1 2026 launch is 83 days past. The banner body takes the space via the existing `flex: 1`, no CSS change. |
| — | `company_stage_label` retired. Banner label is now the fixed string "This Week's Pulse". |
| — | Curly quotes in `<style>` fixed, 62 of them. `content: ‘CASH’` and 30 of 33 `font-family` declarations were invalid CSS, so the Google Fonts faces silently fell back to browser defaults in every published brief. Body copy outside `<style>` untouched. |

Template is fully placeholder-driven. No metric is hardcoded. 87 placeholders: 82 scalars, 5 blocks.

## Banner and MD&A

One commentary block per week, captured at run time, covering both what moved and what we
are doing about it. There is no separate priorities prompt.

Split rule:

- Prose before the first numbered line fills `{{company_stage_text}}` in the banner.
- Numbered lines become `{{#priorities}}` rows, split on the first colon into
  `priority_title` and `priority_why`.
- No numbered lines means `has_priorities` is false and the Priorities section is omitted.
- Blank MD&A sets `company_stage_text` to "Commentary pending." It never reuses last week.

The banner is a centered 13.5px strip built for one short paragraph. Keep the banner text
tight and push detail into the numbered priorities. Do not widen it with CSS.

## Data contract

Deal data shape is `{open, stalled, won, lost}`. Stalled was absent from the spec's shape but
is required by both `stage_stalled_count` and the attention rule.

`data/deal_data_current.json` as committed was **recovered from `briefs/2026-07-24.html`**, not
pulled from Asana. Its `notes` are byte-identical to that brief's `dealData` across all 48
deals. Treat it as a reference fixture, not as pull output.

**Notes come from an override file**, `deal_notes.json` keyed by task GID, per spec option (b).
The recovered notes are editorially curated, not Asana field values: the earlier blob carries
all-caps prefixes (`TIER 1 -`, `VERIFIED OWNER`, `COMPETITIVE INTEL`) and the recovered
versions are rewritten and compressed. The first `pull_asana.py` run must dump raw Asana task
descriptions to a scratch file for comparison before notes are wired in.

### total_deals_count

Raw task count across all eight sections, `open + stalled + won + lost`. Includes Stalled,
Won, Lost and known duplicates, so the eight stage counts reconcile exactly. Duplicates are
surfaced in `data_quality_summary`, never silently removed. As of 2026-07-24: 51 raw, 50
distinct. The recovered fixture is missing its Stalled section and so totals 48.

## Rules

**Needs Attention** uses the per-stage day thresholds in `data_definitions.md` (Cold and Warm
14, Qualified 7, Demo 10, Proposal 14, Stalled 21), with the Stalled fallback and the 8-deal
cap. The spec's simplified "Stalled plus Proposal" version is superseded. The pull must
request `modified_at`.

**Data quality tiers** are green at 80% or above, gold 50 to 79, red below 50. The spec's
single 40% cutoff is superseded.

**Channels**: all 8 always displayed, including zeros. Direct to Consumer's enum option GID is
still unresolved and must be looked up live in `pull_asana.py` before the first real run.

**Joshua Plack duplicate**: two Qualified tasks, `Drink with Me` and
`Plack, Joshua - Drink With Me`. Confirm both task GIDs against those names before keying on
them. Flag in `data_quality_summary` until merged in Asana.

## Orchestrator

Exactly two prompts, then fully automatic.

1. "Are we ready?" No means stand down cleanly, no partial files.
2. "MD&A?" Multiline capture, then: fresh Asana pull, render, integrity checks, commit, push,
   Slack notification.

The pull happens at yes, never from the 3:00pm snapshot. No third prompt. Notification is not
a gate.

## Integrity checks

Spec section 7 plus these additions:

- No literal deal name in either JSON script block (guards against a re-baked `dealData`).
- No curly quote anywhere inside `<style>` (guards the regression just fixed).
- No unresolved `{{placeholder}}` in the output.

## Versioning

One version line, in `VERSION` at the repo root. `config.py` reads it. It feeds both
`{{version_stamp}}` in the header and `{{footer_meta}}` in the footer. Currently 0.13.

## Testing

Golden test: rendering `data/*.json` plus the known 7/24 commentary must reproduce
`briefs/2026-07-24.html`. **Body only, excluding the `<style>` block**, since the quote fix
intentionally changes the CSS. `render.py` takes a `--date` override for testing and backfill.

## Kept deliberately

`prompt/sales_pulse_prompt.md` holds the original Needs Attention logic the build spec dropped.
`docs/data_definitions.md` is the metric source of truth. Neither is superseded by the pipeline.

## Renderer notes (added with pipeline/render.py)

`render.py` is pure: no network, and no clock reads either. The render date and the pull
timestamp are both arguments, so a run is reproducible and the golden test is meaningful.

**Authored inputs.** A single pull cannot derive every string on the brief. These are passed
in by `run.py`, with empty defaults so a run never silently reprints last week:
`ta_meta`, `ta_total_subtext`, `ta_added_subtext`, `ta_qual_subtext`, `ta_rate_subtext`,
`lost_subtext`, `lost_arr_subtext`, `lost_onb_subtext`, `data_quality_summary`.
Deciding how these get captured is open, see below.

**Deferred to the previous-pull diff** (spec section 10): `ta_added`, `ta_qualified`,
`ta_qual_rate` and the per-card `ch_added` / `ch_qual` are hardcoded to zero until
`pull_asana.py` stores the prior lead set to diff against.

**Inert placeholder.** `zero_class` renders empty because the stylesheet has no `.zero` rule.
Kept for template parity.

**Channel sort.** Deal count descending, ties broken by onboarding total descending, then
name. The alphabetical tiebreak was wrong and the golden test caught it: Wine Storage and
Cellar Builder both hold 4 deals and the published brief orders Wine Storage first.

**Signal class.** `.hot` for Demo, `.warm` otherwise, following
`prompt/sales_pulse_prompt.md`. The stylesheet defines no `.cold`, so that state is
unreachable and the third tier the prompt describes does not exist.

## Known defects in briefs/2026-07-24.html

Found while building the golden test. The renderer deliberately does not reproduce these.

1. `attention_meta` reads "Top 8 by Stage Velocity" above 5 rows.
2. A deal with no onboarding value renders "Proposal · onb unset onb", the word duplicated.
3. Headline `ta_added` is 0 while every Target Accounts card shows added equal to its full
   count.

All three are consistent with the brief having been assembled by hand.
