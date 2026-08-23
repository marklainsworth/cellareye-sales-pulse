"""One tick of the Slack gate. launchd runs this every 60 seconds.

Short-lived by design. With no gate open it exits immediately without calling
Slack, so it costs nothing for the 167 hours a week the gate is closed. Missed
ticks while the Air sleeps are harmless: state is on disk and the reply waits in
Slack history.

    python -m pipeline.gate_runner --open          post the prompt, open a gate
    python -m pipeline.gate_runner                 one tick
    python -m pipeline.gate_runner --status        show state, touch nothing
    python -m pipeline.gate_runner --close         abandon an open gate
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import checks        # noqa: E402
import config        # noqa: E402
import pull_asana    # noqa: E402
import render as render_mod  # noqa: E402
import slack_gate as sg      # noqa: E402
import summarize     # noqa: E402


def log(msg: str) -> None:
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg), flush=True)


def do_pull(env, state):
    """Fresh pull on yes, then straight to the MD&A. Two prompts, no third."""
    log("pull: fetching Asana")
    previous = None
    cur = config.DATA_DIR / "deal_data_current.json"
    if cur.exists():
        previous = json.loads(cur.read_text(encoding="utf-8"))

    token = pull_asana.load_token()
    deals, _ = pull_asana.pull_deals(token)
    leads = pull_asana.pull_leads(token)
    pull_asana.apply_overrides(deals)
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    cur.write_text(json.dumps(deals, ensure_ascii=False, indent=1), encoding="utf-8")
    (config.DATA_DIR / "lead_data_current.json").write_text(
        json.dumps(leads, ensure_ascii=False, indent=1), encoding="utf-8")

    log("summarise: compressing deal notes")
    summarize.main([])
    deals = json.loads(cur.read_text(encoding="utf-8"))

    state["pulled_at"] = datetime.now().strftime("%H:%M PT")
    line = sg.pull_line(deals, leads)
    log("pull: %s" % line)
    return sg.ask_mda(env, state, pulled=line)


def do_render(env, state, mda, test):
    deals = json.loads((config.DATA_DIR / "deal_data_current.json").read_text(encoding="utf-8"))
    leads = json.loads((config.DATA_DIR / "lead_data_current.json").read_text(encoding="utf-8"))
    render_date = date.fromisoformat(state["render_date"])
    tpl = config.TEMPLATE.read_text(encoding="utf-8")

    log("render")
    html = render_mod.render(deals, leads, mda, render_date,
                            state.get("pulled_at", ""), template=tpl)

    failures, warnings, lines = checks.run_all(
        html, tpl, deals, leads, mda, render_date, strict_friday=not test)
    for ln in lines:
        log(ln.rstrip())
    if failures:
        sg.notify(env, state, ":x: Aborted. %d integrity check(s) failed, nothing written:\n%s"
                  % (len(failures), "\n".join("- " + f for f in failures)))
        return None

    name = ("test-%s.html" if test else "%s.html") % render_date.isoformat()
    out = config.BRIEFS_DIR / name
    out.write_text(html, encoding="utf-8")
    log("wrote %s" % out.relative_to(config.REPO_ROOT))
    return out


def tick(env, state, test: bool):
    msg = sg.next_reply(env, state)
    if not msg:
        return state
    log("reply at step %s: %r" % (state["step"], msg["text"][:60]))
    sg.consume(state, msg)
    kind = sg.classify(msg["text"])

    if state["step"] == sg.ASK_READY:
        if kind == "no":
            sg.notify(env, state, "Stood down. Nothing pulled, nothing published.")
            sg.clear_state()
            log("stood down")
            return None
        if kind != "yes":
            sg.notify(env, state, "Reply *yes* when the board is current, or *not yet* to stand down.")
            return state
        return do_pull(env, state)

    if state["step"] == sg.ASK_MDA:
        mda = "" if msg["text"].strip().lower() in ("skip", "none", "-") else msg["text"]
        out = do_render(env, state, mda, test)
        if out is None:
            return state
        link = "briefs/%s" % out.name
        if test:
            sg.notify(env, state,
                      ":white_check_mark: Test brief rendered: `%s`\n"
                      "_Test run: latest.html untouched, nothing committed._" % link)
        else:
            sg.notify(env, state, ":white_check_mark: Pulse published: `%s`" % link)
        sg.clear_state()
        log("done")
        return None

    return state


def main(argv=None):
    p = argparse.ArgumentParser(description="One tick of the Slack gate.")
    p.add_argument("--open", action="store_true", help="post the prompt and open a gate")
    p.add_argument("--status", action="store_true", help="show state, change nothing")
    p.add_argument("--close", action="store_true", help="abandon an open gate")
    p.add_argument("--test", action="store_true", help="render to the test path, never publish")
    p.add_argument("--date", help="render date YYYY-MM-DD")
    a = p.parse_args(argv)

    state = sg.read_state()

    if a.status:
        if not state:
            print("no gate open")
        else:
            age = (datetime.now().timestamp() - state["opened_at"]) / 60
            print(json.dumps({**state, "age_minutes": round(age, 1),
                              "stale": sg.is_stale(state)}, indent=1))
        return 0

    if a.close:
        sg.clear_state()
        print("gate closed")
        return 0

    try:
        env = sg.load_env()
    except sg.SlackError as e:
        log("config error: %s" % e)
        return 1

    if a.open:
        if state and not sg.is_stale(state):
            log("a gate is already open, not opening another")
            return 0
        render_date = date.fromisoformat(a.date) if a.date else date.today()
        state = sg.open_gate(env, render_date, test=a.test)
        log("gate opened, ts %s" % state["gate_ts"])
        return 0

    if not state:
        return 0                      # nothing pending, the common case
    if sg.is_stale(state):
        log("gate stale, closing")
        sg.notify(env, state, "This Pulse gate expired without an answer. Nothing was published.")
        sg.clear_state()
        return 0

    # the gate's own record wins; --test can only add caution, never remove it
    test = bool(state.get("test")) or a.test
    try:
        tick(env, state, test=test)
    except sg.SlackError as e:
        log("slack error: %s" % e)
        return 1
    except Exception:
        log("unexpected failure:\n%s" % traceback.format_exc())
        try:
            sg.notify(env, state, ":x: The Pulse run hit an error and stopped. Nothing published.")
        except sg.SlackError:
            pass
        sg.clear_state()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
