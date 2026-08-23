"""The Sales Pulse orchestrator, local terminal path.

This is the fallback for when Mark is at the machine. The production path is
Slack, because the Air lives in the casita and Mark is usually not next to it:

    bin/pulse-prompt                   opens the gate in #sales-pulse
    bin/pulse-gate                     one tick, launchd runs it every 60s
    python -m pipeline.gate_runner --status

Both paths share the same pull, summarise, render and checks. Only the way the
two questions get asked differs.

    python -m pipeline.run --test     rehearsal: writes briefs/test-<date>.html,
                                      never touches latest.html, never commits,
                                      never notifies
    python -m pipeline.run            the real Friday run, from this machine

The gate is the point. Only Mark certifies that the board is true, and the pull
happens when he says yes, never from a stale 3:00 snapshot. There is no second
approval gate: Danielle gets a notification after publish, not a vote before it.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import checks      # noqa: E402
import config      # noqa: E402
import pull_asana  # noqa: E402
import render as render_mod  # noqa: E402
import summarize   # noqa: E402

READY_PROMPT = (
    "Board updated and ready to run the Pulse?\n"
    "  Answering yes pulls Asana fresh, right now, and the brief you publish is\n"
    "  whatever the board says at this moment.\n"
    "  [yes / not yet]: ")

MDA_PROMPT = """
MD&A commentary for this week.
  A few sentences: what moved, what is top of mind, what we are doing about it.
  Number any priorities (1. 2. 3.) and they become the Priorities list; the
  prose above them fills the banner. Leave blank and the brief says
  "Commentary pending." It never reprints last week.

  Finish with a single "." on its own line, or Ctrl-D.
"""


def say(step, detail=""):
    stamp = datetime.now().strftime("%H:%M:%S")
    print("[%s] %s%s" % (stamp, step, ("  " + detail) if detail else ""), flush=True)


def ask_ready() -> bool:
    if not sys.stdin.isatty():
        raise SystemExit(
            "run.py needs a terminal. The gate cannot be answered by a pipe.\n"
            "To answer remotely, use the Slack path instead:\n"
            "  bin/pulse-prompt      opens the gate in #sales-pulse\n"
            "  bin/pulse-gate        reads your reply")
    answer = input(READY_PROMPT).strip().lower()
    return answer in ("y", "yes")


def ask_mda() -> str:
    print(MDA_PROMPT)
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == ".":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def main(argv=None):
    p = argparse.ArgumentParser(description="Run the weekly Sales Pulse.")
    p.add_argument("--test", action="store_true",
                   help="rehearsal: test path, no latest.html, no commit, no notify")
    p.add_argument("--date", help="render date YYYY-MM-DD, defaults to today")
    p.add_argument("--mda-file", help="read the MD&A from a file instead of prompting")
    p.add_argument("--skip-pull", action="store_true",
                   help="reuse data/ as-is instead of pulling (rehearsal only)")
    p.add_argument("--no-summarise", action="store_true", help="skip the summariser")
    a = p.parse_args(argv)

    render_date = date.fromisoformat(a.date) if a.date else date.today()
    if a.skip_pull and not a.test:
        raise SystemExit("--skip-pull is only allowed with --test")

    print()
    say("Sales Pulse", "%s%s" % (render_date.isoformat(), "  TEST RUN" if a.test else ""))
    print()

    # --- gate 1 --------------------------------------------------------------
    if not ask_ready():
        print()
        say("stood down", "nothing pulled, nothing written, nothing published")
        return 0

    # --- gate 2 --------------------------------------------------------------
    mda = (Path(a.mda_file).read_text(encoding="utf-8") if a.mda_file else ask_mda())
    print()
    if mda.strip():
        say("commentary", "%d chars captured" % len(mda.strip()))
    else:
        say("commentary", "blank, the brief will say 'Commentary pending.'")

    # --- everything from here runs on its own --------------------------------
    if a.skip_pull:
        say("pull", "SKIPPED, reusing data/ as-is")
        pulled_at = "reused"
    else:
        say("pull", "fetching both Asana projects now")
        token = pull_asana.load_token()
        deals, dump = pull_asana.pull_deals(token)
        leads = pull_asana.pull_leads(token)
        pull_asana.apply_overrides(deals)
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        (config.DATA_DIR / "deal_data_current.json").write_text(
            json.dumps(deals, ensure_ascii=False, indent=1), encoding="utf-8")
        (config.DATA_DIR / "lead_data_current.json").write_text(
            json.dumps(leads, ensure_ascii=False, indent=1), encoding="utf-8")
        pulled_at = datetime.now().strftime("%H:%M PT")
        say("pull", "%s deals, %d leads" % ({k: len(v) for k, v in deals.items()}, len(leads)))

    if not a.no_summarise:
        say("summarise", "compressing deal notes")
        summarize.main([])

    deals = json.loads((config.DATA_DIR / "deal_data_current.json").read_text(encoding="utf-8"))
    leads = json.loads((config.DATA_DIR / "lead_data_current.json").read_text(encoding="utf-8"))
    if pulled_at == "reused":
        pulled_at = datetime.now().strftime("%H:%M PT")

    say("render", "filling the template")
    tpl = config.TEMPLATE.read_text(encoding="utf-8")
    html = render_mod.render(deals, leads, mda, render_date, pulled_at, template=tpl)

    # --- integrity checks ----------------------------------------------------
    say("checks", "")
    failures, warnings, lines = checks.run_all(
        html, tpl, deals, leads, mda, render_date, strict_friday=not a.test)
    for ln in lines:
        print(ln)
    if failures:
        print()
        say("ABORTED", "%d check(s) failed, nothing written" % len(failures))
        return 1
    if warnings:
        say("checks", "%d warning(s), continuing" % len(warnings))

    # --- write ---------------------------------------------------------------
    name = ("test-%s.html" if a.test else "%s.html") % render_date.isoformat()
    out = config.BRIEFS_DIR / name
    out.write_text(html, encoding="utf-8")
    say("wrote", "%s  (%d KB)" % (out.relative_to(config.REPO_ROOT), len(html) // 1024))

    if a.test:
        print()
        say("TEST RUN", "latest.html untouched, nothing committed, nothing notified")
        say("review", "open %s" % out)
        return 0

    say("commit", "not wired yet")
    say("notify", "not wired yet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
