"""Golden test: reproduce briefs/2026-07-24.html from the recovered data.

Compares the renderer's output field by field against the values actually
published in that brief, which are recovered by aligning the template against
the brief. Field-level rather than byte-level, for two reasons:

  * the CSS was deliberately changed (the curly-quote fix), so the <style>
    block is excluded by design, and
  * the published brief contains three known defects that must not be
    reproduced (see PUBLISHED_DEFECTS below).

Every divergence from the published brief must be declared in EXPECTED_DIVERGENCES
with a reason. Anything else is a failure.

Run:  python3 tests/test_golden_2026_07_24.py
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import render  # noqa: E402

BRIEF = ROOT / "briefs" / "2026-07-24.html"
RENDER_DATE = date(2026, 7, 24)
PULL_TIME = "20:15 PT"
PUBLISHED_VERSION = "0.12"


# Chrome we intentionally changed in the template. Excluded from comparison.
RETIRED = {"company_stage_label", "launch_countdown", "footer_meta", "version_stamp"}

# Divergences we accept, each with the decision that caused it.
EXPECTED_DIVERGENCES = {
    "open_arr_dq_class": "DQ tiers changed to the docs three-tier rule; 42% is error, not warning",
    "open_onb_dq_class": "DQ tiers changed to the docs three-tier rule; 42% is error, not warning",
    "attention_meta": "attention rule changed to thresholds; fixture has no modified_at so the Stalled fallback fires",
    "rule_logic_explainer": "same as attention_meta",
    "priorities": ("the 7/24 brief predates the folded-MD&A design, where priorities are "
                   "parsed out of the commentary; its 3 priorities were authored separately "
                   "and its banner text carries no numbered lines"),
}

# Defects in the published brief that the renderer deliberately does not reproduce.
PUBLISHED_DEFECTS = {
    "attention_meta": 'says "Top 8 by Stage Velocity" while showing 5 rows',
    "deal_signal": 'renders "onb unset onb", the word onb duplicated',
    "ch_added": "per-card added equals the full channel count while the headline ta_added is 0",
}


def extract_published():
    """Recover the rendered value of every placeholder from the published brief."""
    tmpl = (ROOT / "templates" / "sales_pulse.html").read_text(encoding="utf-8")
    brief = BRIEF.read_text(encoding="utf-8")
    body = lambda s: s[s.index("</style>") + len("</style>"):]
    t, b = body(tmpl), body(brief)

    # put the retired chrome back so the template lines up with the older brief
    t = t.replace("<div class=\"label\">This Week's Pulse</div>",
                  "<div class=\"label\">{{company_stage_label}}</div>")
    t = t.replace("  <div class=\"text\">{{company_stage_text}}</div>\n",
                  "  <div class=\"text\">{{company_stage_text}}</div>\n"
                  "  <div class=\"countdown\">{{launch_countdown}}</div>\n")
    t = t.replace("<h3>Priorities · This Week</h3>", "<h3>Top 3 Priorities — This Week</h3>")
    t = t.replace("{{#has_priorities}}", "").replace("{{/has_priorities}}\n", "")

    loops = dict(re.findall(r"\{\{#(\w+)\}\}(.*?)\{\{/\1\}\}", t, re.S))
    work = t
    for name in loops:
        work = re.sub(r"\{\{#%s\}\}.*?\{\{/%s\}\}" % (name, name),
                      "\x00%s\x00" % name, work, flags=re.S)

    pat, seen = "", []
    for p in re.split(r"(\x00\w+\x00|\{\{\w+\}\})", work):
        if p.startswith("\x00"):
            pat += "(?P<loop_%s>.*?)" % p.strip("\x00")
        elif re.fullmatch(r"\{\{\w+\}\}", p):
            n = p[2:-2]
            pat += ("(?P=%s)" % n) if n in seen else ("(?P<%s>.*?)" % n)
            seen.append(n)
        else:
            pat += re.escape(p)

    m = re.fullmatch(pat, b, re.S)
    assert m, "template no longer aligns with the published brief"
    g = m.groupdict()
    scalars = {k: v for k, v in g.items() if not k.startswith("loop_")}
    rows = {}
    for name, inner in loops.items():
        seg = g["loop_" + name]
        ipat = "".join("(?P<%s>.*?)" % p[2:-2] if re.fullmatch(r"\{\{\w+\}\}", p) else re.escape(p)
                       for p in re.split(r"(\{\{\w+\}\})", inner))
        rows[name] = [mm.groupdict() for mm in re.finditer(ipat, seg, re.S)]
    return scalars, rows


def main():
    published, published_rows = extract_published()

    deals = json.loads((ROOT / "data" / "deal_data_current.json").read_text(encoding="utf-8"))
    leads = json.loads((ROOT / "data" / "lead_data_current.json").read_text(encoding="utf-8"))
    # The recovered data file was rebuilt from this brief and lost the Stalled
    # section. Restore it from the brief's own attention rows so the funnel and
    # the project total can be checked. Reference fixture, not pull output.
    deals["stalled"] = json.loads(
        (ROOT / "tests" / "fixtures" / "stalled_2026_07_24.json").read_text(encoding="utf-8"))
    authored = json.loads(
        (ROOT / "tests" / "fixtures" / "authored_2026_07_24.json").read_text(encoding="utf-8"))

    ctx = render.build_context(deals, leads, published["company_stage_text"],
                              RENDER_DATE, PULL_TIME, authored=authored,
                              version=PUBLISHED_VERSION)

    failures, diverged, checked = [], [], 0
    for key in sorted(published):
        if key in RETIRED or key.endswith("_json"):
            continue
        checked += 1
        got, want = str(ctx.get(key, "<missing>")), published[key]
        if got == want:
            continue
        if key in EXPECTED_DIVERGENCES:
            diverged.append((key, got, want))
        else:
            failures.append((key, got, want))

    # channel rows must match exactly, order included
    for i, (got, want) in enumerate(zip(ctx["channels"], published_rows["channels"])):
        checked += 1
        if got != want:
            failures.append(("channels[%d]" % i, got, want))
    if len(ctx["channels"]) != len(published_rows["channels"]):
        failures.append(("channels", len(ctx["channels"]), len(published_rows["channels"])))

    # target accounts: names, counts and fills. ch_added is a published defect.
    for i, (got, want) in enumerate(zip(ctx["ta_channels"], published_rows["ta_channels"])):
        checked += 1
        for f in ("ch_name", "ch_count", "ch_fill_pct", "ta_data_view"):
            if got[f] != want[f]:
                failures.append(("ta_channels[%d].%s" % (i, f), got[f], want[f]))
        # leader_class, zero_class and ta_clickable sit adjacent in the template, so the
        # extractor cannot attribute them individually. Compare the resulting class string.
        cls = lambda r: (r["leader_class"] + r["zero_class"] + r["ta_clickable"])
        if cls(got) != cls(want):
            failures.append(("ta_channels[%d].class" % i, cls(got), cls(want)))

    # priorities parsed out of the MD&A
    checked += 1
    if len(ctx["priorities"]) != len(published_rows["priorities"]):
        diverged.append(("priorities", "%d parsed" % len(ctx["priorities"]),
                         "%d published" % len(published_rows["priorities"])))

    html = render.render(deals, leads, published["company_stage_text"], RENDER_DATE,
                         PULL_TIME, authored=authored, version=PUBLISHED_VERSION)
    left = render.unresolved(html)
    if left:
        failures.append(("unresolved placeholders", left, "none"))

    print("checked %d fields against briefs/2026-07-24.html\n" % checked)
    if diverged:
        print("expected divergences (%d):" % len(diverged))
        for k, got, want in diverged:
            print("  %-22s got %-38s published %s" % (k, str(got)[:38], str(want)[:44]))
            print("  %-22s reason: %s" % ("", EXPECTED_DIVERGENCES.get(k, "see notes")))
        print()
    if failures:
        print("FAILURES (%d):" % len(failures))
        for k, got, want in failures:
            print("  %-22s got %-38s published %s" % (k, str(got)[:38], str(want)[:44]))
        return 1
    print("PASS: every computed field matches, or is a declared divergence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
