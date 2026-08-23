"""Integrity checks. Run before anything is committed; abort on failure.

Section 7 of the build spec, plus three additions from docs/build_decisions.md:
no literal deal name baked into the template, no curly quote inside <style>,
no unresolved placeholder in the output.

A check returns (ok, detail). Warnings do not block; failures do.
"""
from __future__ import annotations

import json
import re
from datetime import date

import config


# --- template checks (run against templates/sales_pulse.html) ----------------

def template_no_baked_data(tpl: str):
    """The dealData blob was hardcoded once. It must never come back."""
    blocks = re.findall(r'<script id="(?:deal|lead)Data"[^>]*>(.*?)</script>', tpl, re.S)
    for b in blocks:
        body = b.strip()
        if body and not re.fullmatch(r"\{\{\w+\}\}", body):
            return False, "a JSON script block holds literal data, not a placeholder"
    return True, "both JSON blocks are placeholders"


def template_no_curly_quotes_in_css(tpl: str):
    """iPad smart punctuation silently invalidated 30 font-family rules once."""
    a, b = tpl.find("<style>"), tpl.find("</style>")
    if a == -1:
        return True, "no style block"
    bad = [c for c in "‘’“”" if c in tpl[a:b]]
    return (not bad), ("curly quotes in <style>: %s" % " ".join(bad)) if bad else "none"


def template_no_endash_in_var(tpl: str):
    hits = re.findall(r"var\(\s*[–—]", tpl)
    return (not hits), "%d en/em dash in var()" % len(hits) if hits else "none"


# --- output checks (run against the rendered brief) --------------------------

def no_unresolved_placeholders(html: str):
    left = sorted(set(re.findall(r"\{\{[^}]*\}\}", html)))
    return (not left), ", ".join(left) if left else "none"


def json_blocks_parse(html: str):
    out = {}
    for name in ("dealData", "leadData"):
        m = re.search(r'<script id="%s"[^>]*>(.*?)</script>' % name, html, re.S)
        if not m:
            return False, "%s block missing" % name
        try:
            out[name] = json.loads(m.group(1).strip())
        except json.JSONDecodeError as e:
            return False, "%s does not parse: %s" % (name, e)
    return True, "dealData and leadData both parse"


def counts_reconcile(html: str, deals: dict):
    m = re.search(r"Generated [^<]*· (\d+) deals tracked", html)
    if not m:
        return False, "could not find the deals-tracked line"
    stated = int(m.group(1))
    actual = sum(len(v) for v in deals.values())
    if stated != actual:
        return False, "header says %d, data holds %d" % (stated, actual)
    return True, "%d deals, header and data agree" % actual


def lead_total_matches(html: str, leads: list):
    m = re.search(r'<script id="leadData"[^>]*>(.*?)</script>', html, re.S)
    n = len(json.loads(m.group(1).strip())) if m else -1
    return (n == len(leads)), "leadData holds %d, pull returned %d" % (n, len(leads))


def mda_present(html: str, mda: str):
    if not (mda or "").strip():
        return ("Commentary pending." in html), "blank MD&A must render as 'Commentary pending.'"
    return True, "commentary captured (%d chars)" % len(mda.strip())


def date_is_current_friday(render_date: date):
    return (render_date.weekday() == 4), "%s is a %s" % (
        render_date.isoformat(), render_date.strftime("%A"))


# --- runner ------------------------------------------------------------------

def run_all(html: str, tpl: str, deals: dict, leads: list, mda: str,
            render_date: date, strict_friday: bool = True):
    """Returns (failures, warnings, lines) with one line per check."""
    results = [
        ("template: no baked data", template_no_baked_data(tpl), True),
        ("template: no curly quotes in CSS", template_no_curly_quotes_in_css(tpl), True),
        ("template: no dash in var()", template_no_endash_in_var(tpl), True),
        ("output: no unresolved placeholders", no_unresolved_placeholders(html), True),
        ("output: JSON blocks parse", json_blocks_parse(html), True),
        ("output: deal counts reconcile", counts_reconcile(html, deals), True),
        ("output: lead total matches", lead_total_matches(html, leads), True),
        ("output: MD&A present", mda_present(html, mda), True),
        ("output: date is a Friday", date_is_current_friday(render_date), strict_friday),
    ]
    failures, warnings, lines = [], [], []
    for name, (ok, detail), blocking in results:
        mark = "ok  " if ok else ("FAIL" if blocking else "warn")
        lines.append("  %s  %-38s %s" % (mark, name, detail))
        if not ok:
            (failures if blocking else warnings).append(name)
    return failures, warnings, lines
