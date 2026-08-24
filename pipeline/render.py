"""Pure renderer for the CellarEye Sales Pulse.

Reads the template, the two data JSON files, the MD&A commentary and the render
date, and returns the finished HTML. No network calls, no clock reads: every
time-dependent value arrives as an argument so the output is reproducible.

Usage:
    python -m pipeline.render --date 2026-08-28 --mda-file mda.txt
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402


# --- formatting --------------------------------------------------------------

def money(value) -> str:
    """1234.5 -> '$1,235'. None and 0 both render as '$0'."""
    return "$%s" % format(int(round(value or 0)), ",d")


def money_k(value) -> str:
    """50500 -> '$50.5K'. Used on the channel cards, which are tight for space."""
    v = value or 0
    return "$0" if v == 0 else "$%.1fK" % (v / 1000.0)


def pct(part: int, whole: int) -> int:
    return 0 if not whole else int(round(part * 100.0 / whole))


def dq_text(filled: int, total: int) -> str:
    return "%d of %d · %d%% complete" % (filled, total, pct(filled, total))


def dq_class(filled: int, total: int) -> str:
    """Data quality tier. docs/data_definitions.md: >=80 green, 50-79 gold, <50 red."""
    share = pct(filled, total)
    for floor, name in config.DQ_TIERS:
        if share >= floor:
            return name
    return "error"


def no_em_dash(text: str) -> str:
    """House style: no em dashes in Mark-visible copy. Asana names and notes carry
    them, so anything sourced from Asana passes through here."""
    if not text:
        return text
    t = re.sub(r"\s*\u2014\s*", " - ", text)     # em dash becomes a spaced hyphen
    return re.sub(r"\u2013", "-", t)              # en dash becomes a hyphen


def money_short(value) -> str:
    """150000 -> '$150K', 27800 -> '$27.8K'. Drops a trailing .0, for subtexts."""
    v = value or 0
    if v == 0:
        return "$0"
    t = "%.1f" % (v / 1000.0)
    return "$%sK" % (t[:-2] if t.endswith(".0") else t)


def short_name(name: str) -> str:
    """'The Ritz London (Sorrells)' -> 'Ritz London'. For inline lists."""
    n = re.split(r"\s+[(\u2014-]\s*", name.strip(), maxsplit=1)[0]
    return re.sub(r"^The\s+", "", n).strip() or name.strip()


def slug(channel: str) -> str:
    return "ta-" + re.sub(r"[^a-z0-9]", "", channel.lower())


# --- MD&A --------------------------------------------------------------------

# Dictated commentary does not produce a markdown list. Speaking "one, do this,
# two, do that" comes back as one paragraph with "2.)" and "3.)" sitting inline,
# and the first item often carries no marker at all. So markers are found
# anywhere, not just at line start.
INLINE_MARKER = re.compile(r"(?<![\d.$])([1-9])\s*[.)]+[\s)]+")
# A phrase that announces the list, so the banner can be cut before it even when
# the first item is unnumbered.
CUE = re.compile(r"(?:^|[.!?]\s+)([^.!?]*\bpriorit\w*\b[^.!?]*?)(?=\s|$)", re.I)
CUE_STRIP = re.compile(r"^(?:the\s+)?priorit\w*\s*(?:were|are|is|for)?\s*"
                       r"(?:the\s+following\s+week|the\s+following|this\s+week|"
                       r"next\s+week|for\s+the\s+week)?\s*[:,-]?\s*", re.I)


def _split_marked(text: str):
    """Return [segment, ...] split on inline numeric markers, or [] if not a list."""
    marks = [(m.start(), m.end(), int(m.group(1))) for m in INLINE_MARKER.finditer(text)]
    # Two markers minimum, and they must ascend. One stray "2." in prose is not a list.
    if len(marks) < 2:
        return []
    nums = [n for _, _, n in marks]
    if nums != sorted(nums) or len(set(nums)) != len(nums):
        return []
    segs, prev_end = [], None
    for i, (a, b, _) in enumerate(marks):
        if prev_end is None:
            segs.append(text[:a])          # whatever precedes the first marker
        else:
            segs.append(text[prev_end:a])
        prev_end = b
    segs.append(text[prev_end:])
    return [s.strip() for s in segs]


def split_mda(text: str):
    """Split one commentary block into banner prose and priorities.

    Handles both shapes: a typed markdown list with markers at line start, and
    dictated prose where the markers land mid-sentence.
    Returns (banner_text, [{'priority_title', 'priority_why'}, ...]).
    """
    text = " ".join((text or "").split("\n"))
    text = re.sub(r"\s{2,}", " ", text).strip()
    if not text:
        return config.MDA_PENDING, []

    segs = _split_marked(text)
    if not segs:
        return text, []

    lead = segs[0]
    items = segs[1:]

    # If the lead ends with a phrase announcing the list, the text after that
    # phrase is the first, unnumbered priority.
    cue = None
    for m in CUE.finditer(lead):
        cue = m
    if cue:
        banner = lead[:cue.start(1)].strip()
        first = CUE_STRIP.sub("", lead[cue.start(1):]).strip()
        if first:
            items.insert(0, first)
    else:
        banner = lead

    out = []
    for item in items:
        item = item.strip().strip(".").strip()
        if not item:
            continue
        title, sep, why = item.partition(":")
        if sep:
            out.append({"priority_title": title.strip() + ".",
                        "priority_why": why.strip()})
        else:
            # No colon, which dictation rarely produces. Use the first sentence
            # as the title and the rest as the reason.
            parts = re.split(r"(?<=[.!?])\s+", item, maxsplit=1)
            head = parts[0].rstrip(".")
            out.append({"priority_title": head + ".",
                        "priority_why": parts[1].strip() if len(parts) > 1 else ""})
    return (banner or config.MDA_PENDING), out


# --- metric computation ------------------------------------------------------

# The drill-down script reads exactly these fields. Everything else the pull
# collects (gid, modified_at, the comment bodies) is working data the page never
# displays, and embedding it doubled the file for no visible benefit.
DRILLDOWN_FIELDS = ("name", "first", "last", "channel", "arr", "onb", "stage", "notes")
LEAD_FIELDS = ("business", "first", "last", "channel", "section")


def drilldown_payload(deals: dict) -> dict:
    """Embed only what the page shows. Notes prefer the summarised line."""
    out = {}
    for bucket, rows in deals.items():
        out[bucket] = [
            {f: (r.get("note_summary") or r.get("notes") or None) if f == "notes"
             else r.get(f) for f in DRILLDOWN_FIELDS}
            for r in rows
        ]
    return out


def lead_payload(leads: list) -> list:
    return [{f: l.get(f) for f in LEAD_FIELDS} for l in leads]


def stage_counts(deals: dict) -> dict:
    counts = {s: 0 for s in config.FUNNEL_STAGES}
    for bucket in deals.values():
        for d in bucket:
            if d.get("stage") in counts:
                counts[d["stage"]] += 1
    return counts


def channel_rows(open_deals: list) -> list:
    """Open pipeline by channel. Only channels holding deals, count descending."""
    by = {}
    for d in open_deals:
        ch = d.get("channel")
        if not ch:
            continue
        b = by.setdefault(ch, {"deals": 0, "onb": 0.0, "valued": 0})
        b["deals"] += 1
        if d.get("onb") is not None:
            b["onb"] += d["onb"]
            b["valued"] += 1
    rows = []
    # count descending, ties broken by onboarding total descending, then name
    for name, b in sorted(by.items(), key=lambda kv: (-kv[1]["deals"], -kv[1]["onb"], kv[0])):
        rows.append({
            "channel_name": name,
            "channel_deals": str(b["deals"]),
            "channel_onb": money_k(b["onb"]),
            "channel_onb_class": "muted" if b["onb"] == 0 else "",
            "channel_valued": "%d/%d" % (b["valued"], b["deals"]),
        })
    return rows


def ta_rows(leads: list, added: dict | None = None, qualified: dict | None = None) -> list:
    """Target Accounts cards. All 8 channels, zeros included, display order fixed."""
    added, qualified = added or {}, qualified or {}
    counts = {c: 0 for c in config.CHANNELS}
    for l in leads:
        ch = l.get("channel")
        if ch in counts:
            counts[ch] += 1
    top = max(counts.values()) if counts else 0
    rows = []
    for ch in config.CHANNELS:
        n = counts[ch]
        rows.append({
            "ch_name": config.CHANNEL_SHORT_NAMES[ch],
            "ch_count": str(n),
            "ch_added": str(added.get(ch, 0)),
            "ch_qual": str(qualified.get(ch, 0)),
            "ch_fill_pct": str(pct(n, top)),
            "leader_class": " leader" if n and n == top else "",
            "zero_class": "",  # no .zero rule in the stylesheet; kept for template parity
            "ta_clickable": " ta-clickable" if n else "",
            "ta_data_view": 'data-view="%s"' % slug(ch) if n else "",
        })
    return rows


def attention_rows(deals: dict, as_of: date) -> tuple[list, str, str]:
    """Deals needing attention, per docs/data_definitions.md.

    A deal qualifies when days since last activity exceeds its stage threshold.
    If nothing crosses, fall back to every Stalled deal. Capped at 8, sorted
    Stalled first then by stage progression then onboarding descending.
    Returns (rows, panel_meta, rule_explainer).
    """
    candidates = [d for bucket in ("open", "stalled") for d in deals.get(bucket, [])]

    def days_idle(d):
        ts = d.get("modified_at")
        if not ts:
            return None
        seen = datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
        return (as_of - seen).days

    flagged = []
    for d in candidates:
        limit = config.ATTENTION_THRESHOLDS.get(d.get("stage"))
        idle = days_idle(d)
        if limit is not None and idle is not None and idle > limit:
            flagged.append(d)

    fallback = not flagged
    if fallback:
        flagged = [d for d in candidates if d.get("stage") == "Stalled"]

    order = {s: i for i, s in enumerate(config.ATTENTION_SORT_ORDER)}
    flagged.sort(key=lambda d: (order.get(d.get("stage"), 99), -(d.get("onb") or 0)))
    flagged = flagged[:config.ATTENTION_CAP]

    rows = []
    for d in flagged:
        onb = d.get("onb")
        contact = " ".join(x for x in (d.get("first"), d.get("last")) if x)
        # Prefer the summarised line written by pipeline/summarize.py. Fall back
        # to the cleaned description when it has not run.
        note = (d.get("note_summary") or d.get("notes") or "").strip()
        meta = no_em_dash(" · ".join(x for x in (d.get("channel"), note) if x)
                          or "no recent context recorded")
        if d.get("needs_enrichment"):
            meta += " · needs enrichment"
        rows.append({
            "deal_name": no_em_dash(d.get("name", "")),
            "deal_contact": contact or "—",
            "deal_signal": "%s · %s" % (d.get("stage"), money_short(onb) + " onb" if onb else "onb unset"),
            # prompt/sales_pulse_prompt.md: Stalled warm, Proposal stuck warm, Demo hot.
            # The stylesheet only defines .hot and .warm, there is no .cold.
            "deal_signal_class": "hot" if d.get("stage") == "Demo" else "warm",
            "deal_meta": meta,
        })

    if fallback:
        meta = "No Threshold Hits · Showing Stalled"
        why = ("No deal crossed its stage threshold, so every Stalled deal is shown. "
               "Each needs a decision: revive or close out as Lost.")
    else:
        meta = "Top %d by Stage Velocity" % len(rows)
        why = ("Deals shown crossed their stage thresholds (Cold/Warm 14d, Qualified 7d, "
               "Demo 10d, Proposal 14d, Stalled 21d). Sorted: Stalled first, then by stage "
               "progression (Proposal → Cold), then by onboarding value descending.")
    return rows, meta, why


# --- generated subtexts ------------------------------------------------------
#
# These nine strings used to be authored by hand each week. They are number
# restatements, so they are generated from the data. run.py may still override
# any of them; judgment belongs in the MD&A, not here.

def _lead_sections(leads: list) -> str:
    by = {}
    for l in leads:
        by[l.get("section") or "unsectioned"] = by.get(l.get("section") or "unsectioned", 0) + 1
    return " · ".join("%d %s" % (n, s) for s, n in sorted(by.items(), key=lambda kv: -kv[1]))


def generated_subtexts(deals: dict, leads: list, channels: list, ta: list,
                       counts: dict) -> dict:
    open_deals, lost = deals.get("open", []), deals.get("lost", [])
    active_ta = [r for r in ta if int(r["ch_count"])]
    lead_total = len(leads)

    lost_valued = [d for d in lost if d.get("onb") is not None]
    lost_valued.sort(key=lambda d: -(d.get("onb") or 0))
    lost_arr_named = [short_name(d["name"]) for d in lost if d.get("arr") is not None]

    return {
        "ta_meta": "%d leads · %d of %d channels active" % (
            lead_total, len(active_ta), len(ta)),
        "ta_total_subtext": _lead_sections(leads) or "organized in Asana project",
        "ta_added_subtext": "no prior pull to compare",
        "ta_qual_subtext": "no leads converted yet",
        "ta_rate_subtext": "baseline building",
        "lost_subtext": "%d closed lost to date" % len(lost),
        "lost_arr_subtext": (" + ".join(lost_arr_named) if lost_arr_named
                             else "none assigned to lost"),
        "lost_onb_subtext": ("%d of %d valued · %s" % (
            len(lost_valued), len(lost),
            " + ".join("%s %s" % (short_name(d["name"]), money_short(d["onb"]))
                       for d in lost_valued[:3]))
            if lost_valued else "none valued"),
        "data_quality_summary": _quality_summary(deals, channels, counts),
    }


def _quality_summary(deals: dict, channels: list, counts: dict) -> str:
    """The factual base. Judgment goes in the MD&A, never here."""
    open_deals = deals.get("open", [])
    n = len(open_deals)
    parts = []

    arr_n = sum(1 for d in open_deals if d.get("arr") is not None)
    onb_n = sum(1 for d in open_deals if d.get("onb") is not None)
    parts.append("ARR set on %d of %d open deals (%d%%); Onboarding on %d of %d (%d%%)."
                 % (arr_n, n, pct(arr_n, n), onb_n, n, pct(onb_n, n)))

    unvalued = [c for c in channels if c["channel_onb"] == "$0"]
    if unvalued:
        named = ["%s (%s deal%s)" % (c["channel_name"], c["channel_deals"],
                                     "" if c["channel_deals"] == "1" else "s")
                 for c in unvalued]
        joined = named[0] if len(named) == 1 else ", ".join(named[:-1]) + " and " + named[-1]
        parts.append("%s entirely unvalued." % joined)

    no_channel = sum(1 for d in open_deals if not d.get("channel"))
    if no_channel:
        parts.append("%d open deal%s carries no Channel." % (
            no_channel, "" if no_channel == 1 else "s"))

    for label, tasks in getattr(config, "DUPLICATE_TASKS", {}).items():
        parts.append("%s appears twice (%s) and still needs a merge."
                     % (label, ", ".join(no_em_dash(t[1]) for t in tasks)))

    parts.append("No Loss Reason field on the project.")
    return " ".join(parts)


# --- template engine ---------------------------------------------------------

def _expand_blocks(tpl: str, ctx: dict) -> str:
    """Expand {{#name}}...{{/name}}. A list repeats the body, a bool gates it."""
    pattern = re.compile(r"\{\{#(\w+)\}\}(.*?)\{\{/\1\}\}", re.S)
    while True:
        m = pattern.search(tpl)
        if not m:
            return tpl
        name, body = m.group(1), m.group(2)
        value = ctx.get(name)
        if isinstance(value, list):
            out = "".join(_fill_scalars(_expand_blocks(body, {**ctx, **row}), {**ctx, **row})
                          for row in value)
        else:
            out = _expand_blocks(body, ctx) if value else ""
        tpl = tpl[:m.start()] + out + tpl[m.end():]


def _fill_scalars(tpl: str, ctx: dict) -> str:
    return re.sub(r"\{\{(\w+)\}\}",
                  lambda m: str(ctx[m.group(1)]) if m.group(1) in ctx else m.group(0),
                  tpl)


def apply_template(tpl: str, ctx: dict) -> str:
    return _fill_scalars(_expand_blocks(tpl, ctx), ctx)


# --- the renderer ------------------------------------------------------------

# Strings no single pull can derive. run.py may override any of them; the
# defaults keep a run honest rather than reprinting last week's copy.
AUTHORED_DEFAULTS = {
    "ta_meta": "",
    "ta_total_subtext": "organized in Asana project",
    "ta_added_subtext": "",
    "ta_qual_subtext": "",
    "ta_rate_subtext": "",
    "lost_subtext": "",
    "lost_arr_subtext": "",
    "lost_onb_subtext": "",
    "data_quality_summary": "",
}


def build_context(deals: dict, leads: list, mda: str, render_date: date,
                  pull_time: str, authored: dict | None = None,
                  version: str | None = None) -> dict:
    authored = {k: v for k, v in (authored or {}).items()}
    version = version or config.version()

    open_deals = deals.get("open", [])
    won, lost = deals.get("won", []), deals.get("lost", [])
    counts = stage_counts(deals)
    top = max(counts.values()) if counts else 0

    banner, priorities = split_mda(mda)
    channels = channel_rows(open_deals)
    ta = ta_rows(leads)
    attention, attention_meta, rule_why = attention_rows(deals, render_date)

    def valued(rows, field):
        return sum(1 for r in rows if r.get(field) is not None)

    def total(rows, field):
        return sum(r[field] for r in rows if r.get(field) is not None)

    stages_used = sum(1 for s in config.OPEN_STAGES if counts[s])
    ctx = {
        # header and banner
        "render_date_long": render_date.strftime("%A, %B %-d"),
        "render_time": pull_time,
        "version_stamp": "v%s · Live Data" % version,
        "total_deals_count": str(sum(counts.values())),
        "company_stage_text": banner,

        # target accounts
        "ta_total": str(len(leads)),
        "ta_added": "0",
        "ta_qualified": "0",
        "ta_qual_class": "muted-value",
        "ta_qual_rate": "0%",
        "ta_rate_class": "muted-value",

        # open
        "open_count": str(len(open_deals)),
        "open_subtext": "across %d stages · %d channels" % (stages_used, len(channels)),
        "open_arr": money(total(open_deals, "arr")),
        "open_arr_dq": dq_text(valued(open_deals, "arr"), len(open_deals)),
        "open_arr_dq_class": dq_class(valued(open_deals, "arr"), len(open_deals)),
        "open_onb": money(total(open_deals, "onb")),
        "open_onb_dq": dq_text(valued(open_deals, "onb"), len(open_deals)),
        "open_onb_dq_class": dq_class(valued(open_deals, "onb"), len(open_deals)),
        "conversion_c_q": "—",
        "conversion_subtext": "no closed cycles yet",

        # won
        "won_count": str(len(won)),
        "won_arr": money(total(won, "arr")),
        # Average across deals that actually carry a value, not across all won
        # deals. Dividing by the raw count means closing a customer whose
        # onboarding field is still empty makes average deal size fall, which
        # reads as the business getting worse. The Won data quality line beside
        # it reports the coverage.
        "won_avg": (money(total(won, "onb") / valued(won, "onb"))
                    if valued(won, "onb") else "—"),
        "won_onb": money(total(won, "onb")),
        "won_onb_dq": dq_text(valued(won, "onb"), len(won)),

        # lost
        "lost_count": str(len(lost)),
        "lost_arr": money(total(lost, "arr")),
        "lost_onb": money(total(lost, "onb")),

        # channels and attention
        "channel_count": str(len(channels)),
        "cold_leader_class": "has-most",
        "channels": channels,
        "ta_channels": ta,
        "attention_deals": attention,
        "attention_meta": attention_meta,
        "rule_logic_explainer": rule_why,
        "priorities": priorities,
        "has_priorities": bool(priorities),

        # drill-down payloads
        "deal_data_json": json.dumps(drilldown_payload(deals), ensure_ascii=False),
        "lead_data_json": json.dumps(lead_payload(leads), ensure_ascii=False),

        "footer_meta": "Source: Asana CellarEye Sales Pipeline · Automated render · v%s" % version,
    }
    for stage, key in config.STAGE_KEYS.items():
        ctx["stage_%s_count" % key] = str(counts[stage])
        ctx["stage_%s_fill" % key] = str(pct(counts[stage], top))
    generated = generated_subtexts(deals, leads, channels, ta, counts)
    ctx.update({k: v for k, v in generated.items() if v})
    # anything explicitly authored still wins over the generated version
    ctx.update({k: v for k, v in authored.items() if v})
    return ctx


def render(deals: dict, leads: list, mda: str, render_date: date, pull_time: str,
           template: str | None = None, authored: dict | None = None,
           version: str | None = None) -> str:
    tpl = template if template is not None else config.TEMPLATE.read_text(encoding="utf-8")
    ctx = build_context(deals, leads, mda, render_date, pull_time, authored, version)
    html = apply_template(tpl, ctx)
    stamp = "<!-- pulled %s · rendered for %s · pipeline v%s -->\n" % (
        pull_time, render_date.isoformat(), version or config.version())
    return stamp + html


def unresolved(html: str) -> list:
    return sorted(set(re.findall(r"\{\{[^}]*\}\}", html)))


def main(argv=None):
    p = argparse.ArgumentParser(description="Render the Sales Pulse brief.")
    p.add_argument("--date", help="render date YYYY-MM-DD, defaults to today")
    p.add_argument("--mda-file", help="file holding the MD&A commentary")
    p.add_argument("--deals", default=str(config.DATA_DIR / "deal_data_current.json"))
    p.add_argument("--leads", default=str(config.DATA_DIR / "lead_data_current.json"))
    p.add_argument("--authored", help="JSON file of authored strings")
    p.add_argument("--pull-time", default="", help="pull timestamp, e.g. '20:15 PT'")
    p.add_argument("-o", "--out", help="output path, defaults to briefs/<date>.html")
    a = p.parse_args(argv)

    render_date = date.fromisoformat(a.date) if a.date else date.today()
    deals = json.loads(Path(a.deals).read_text(encoding="utf-8"))
    leads = json.loads(Path(a.leads).read_text(encoding="utf-8"))
    mda = Path(a.mda_file).read_text(encoding="utf-8") if a.mda_file else ""
    authored = json.loads(Path(a.authored).read_text(encoding="utf-8")) if a.authored else None

    html = render(deals, leads, mda, render_date, a.pull_time, authored=authored)
    left = unresolved(html)
    if left:
        print("unresolved placeholders: %s" % ", ".join(left), file=sys.stderr)
        return 1

    out = Path(a.out) if a.out else config.BRIEFS_DIR / ("%s.html" % render_date.isoformat())
    out.write_text(html, encoding="utf-8")
    print("wrote %s (%d bytes)" % (out, len(html)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
