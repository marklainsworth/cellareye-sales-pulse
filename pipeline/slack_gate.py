"""The Slack gate. Posts the prompt, reads Mark's reply, certifies it was him.

The Air only ever makes outbound HTTPS calls to slack.com. Nothing listens on a
port, there is no webhook and no tunnel. A reply waits in Slack history until
something reads it, so the Air sleeping while Mark answers from the road costs
nothing: it wakes, polls, and finds the answer waiting. A socket would have
dropped that event.

State lives in data/gate_state.json so the poller can be a short-lived process
that launchd starts every 60 seconds rather than a daemon holding a connection.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

API = "https://slack.com/api/"
STATE = config.DATA_DIR / "gate_state.json"
ENV = config.REPO_ROOT / "config" / "slack.env"

GATE_TTL_SECONDS = 6 * 60 * 60      # a gate older than this has gone stale
POLL_TIMEOUT = 25

# Conversation steps. The gate walks these in order and never skips one.
ASK_READY, ASK_MDA, DONE = "ask_ready", "ask_mda", "done"

AFFIRMATIVE = {"y", "yes", "ready", "yep", "yup", "go", "ok", "okay", "run it"}
NEGATIVE = {"n", "no", "not yet", "notyet", "later", "stop", "cancel", "abort"}


class SlackError(RuntimeError):
    pass


# --- credentials -------------------------------------------------------------

def load_env() -> dict:
    if not ENV.exists():
        raise SlackError("config/slack.env missing. See config/slack.env.example.")
    out = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("SLACK_BOT_TOKEN", "SLACK_CHANNEL_ID", "SLACK_USER_ID"):
        if not out.get(k):
            raise SlackError("config/slack.env is missing %s" % k)
    if not re.match(r"^C[A-Z0-9]+$", out["SLACK_CHANNEL_ID"]):
        raise SlackError("SLACK_CHANNEL_ID must be a channel ID (C...), not a name")
    return out


# --- transport ---------------------------------------------------------------

def api(method: str, env: dict, payload: dict | None = None, params: dict | None = None):
    token = env["SLACK_BOT_TOKEN"]
    if params is not None:
        req = urllib.request.Request(
            API + method + "?" + urllib.parse.urlencode(params),
            headers={"Authorization": "Bearer " + token})
    else:
        req = urllib.request.Request(
            API + method, data=json.dumps(payload or {}).encode("utf-8"),
            headers={"Authorization": "Bearer " + token,
                     "Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=POLL_TIMEOUT) as r:
            body = json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise SlackError("slack unreachable: %s" % e)
    if not body.get("ok"):
        raise SlackError("%s failed: %s" % (method, body.get("error")))
    return body


def post(env: dict, text: str, thread_ts: str | None = None) -> str:
    """Post to the channel, keeping the gate conversation threaded.

    reply_broadcast matters more than it looks. A plain threaded reply shows in
    the channel only as a small "1 reply" link under the parent, which is easy
    to miss on a phone, and the whole point of this gate is that Mark sees it
    while away from the machine. Broadcasting keeps the thread tidy AND puts
    every question in the channel where he is actually looking.
    """
    payload = {"channel": env["SLACK_CHANNEL_ID"], "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts
        payload["reply_broadcast"] = True
    return api("chat.postMessage", env, payload)["ts"]


# --- identity ----------------------------------------------------------------

def _is_mark(m: dict, env: dict, gate_ts: str) -> bool:
    """Certification: did a live person, specifically Mark, write this?

      author is the configured user      not anyone else
      no bot_id                          a bot token cannot post without one
      no subtype                         excludes joins, topic changes, edits
      posted after the prompt            not an older message
      text is non-empty

    Note what is NOT required: that it be a threaded reply. Answering in the
    channel is the natural thing to do from a phone, and only one gate is ever
    open at a time, so a message from Mark after the prompt is unambiguous.
    Insisting on a thread would add a tap every week and buy no certification.
    """
    if m.get("user") != env["SLACK_USER_ID"]:
        return False
    if m.get("bot_id") or m.get("subtype"):
        return False
    if float(m.get("ts", 0)) <= float(gate_ts):
        return False
    return bool((m.get("text") or "").strip())


def accepted_replies(env: dict, gate_ts: str) -> list:
    """Everything Mark has said since the prompt, in the thread or the channel."""
    seen, out = set(), []
    for method, params in (
        ("conversations.replies",
         {"channel": env["SLACK_CHANNEL_ID"], "ts": gate_ts, "limit": 200}),
        ("conversations.history",
         {"channel": env["SLACK_CHANNEL_ID"], "oldest": gate_ts, "limit": 200}),
    ):
        try:
            body = api(method, env, params=params)
        except SlackError:
            continue
        for m in body.get("messages", []):
            if m["ts"] in seen or not _is_mark(m, env, gate_ts):
                continue
            seen.add(m["ts"])
            out.append({"ts": m["ts"], "text": m["text"].strip()})
    out.sort(key=lambda m: float(m["ts"]))
    return out


def classify(text: str) -> str:
    t = re.sub(r"[^\w\s]", "", text.strip().lower())
    if t in AFFIRMATIVE:
        return "yes"
    if t in NEGATIVE:
        return "no"
    return "other"


# --- state -------------------------------------------------------------------

def read_state() -> dict | None:
    if not STATE.exists():
        return None
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_state(state: dict) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")


def clear_state() -> None:
    if STATE.exists():
        STATE.unlink()


def is_stale(state: dict) -> bool:
    return (time.time() - state.get("opened_at", 0)) > GATE_TTL_SECONDS


# --- opening the gate --------------------------------------------------------

# The prompt @-mentions Mark deliberately. Slack iOS does not reliably surface a
# plain channel message until the app is opened, and a gate he does not see on
# Friday afternoon is a gate that does not fire. Mentions get notification
# priority. SLACK_USER_ID is substituted at post time.
READY_TEXT = (
    "<@{user}> *Sales Pulse, {date}*\n"
    "Ready to run? Reply *yes* once the Asana board is current.\n"
    "_Answering yes pulls Asana fresh at that moment, so the brief reflects the "
    "board as it stands when you reply, not now._\n"
    "Reply *not yet* to stand down."
)


def open_gate(env: dict, render_date, test: bool = False) -> dict:
    header = ("<@{user}> *Sales Pulse, {date}*" if not test
              else "<@{user}> *Sales Pulse, {date}  (TEST RUN)*")
    text = READY_TEXT.replace("<@{user}> *Sales Pulse, {date}*", header)
    ts = post(env, text.format(user=env["SLACK_USER_ID"],
                               date=render_date.strftime("%A, %B %-d")))
    # test-ness is recorded here, not taken from the poller's argv. A gate opened
    # as a test can never be completed as a real publish by a tick that forgot
    # the flag.
    state = {"gate_ts": ts, "step": ASK_READY, "opened_at": time.time(),
             "render_date": render_date.isoformat(), "test": bool(test),
             "consumed": []}
    write_state(state)
    return state


# --- advancing the conversation ----------------------------------------------

MDA_TEXT = (
    "Pulled Asana just now: {pulled}\n\n"
    "*MD&A for this week?* Reply here: what moved, what is top of mind, "
    "what we are doing about it.\n"
    "Number any priorities (1. 2. 3.) and they become the Priorities list; the "
    "prose above them fills the banner.\n"
    "_Dictation is fine. Reply *skip* and the brief says \"Commentary pending.\"_"
)


def pull_line(deals: dict, leads: list) -> str:
    """One line of context inside the MD&A prompt. Informational, not a gate."""
    c = {k: len(v) for k, v in deals.items()}
    return ("%d deals (open %d, stalled %d, won %d, lost %d), %d leads"
            % (sum(c.values()), c.get("open", 0), c.get("stalled", 0),
               c.get("won", 0), c.get("lost", 0), len(leads)))


def board_summary(deals: dict, leads: list, previous: dict | None = None) -> tuple[str, int]:
    """Kept for the Slack notification after publish, not used as a gate."""
    counts = {k: len(v) for k, v in deals.items()}
    total = sum(counts.values())
    thin = sum(1 for d in sum(deals.values(), []) if d.get("needs_enrichment"))
    lines = [
        "%d deals total" % total,
        "  open %d · stalled %d · won %d · lost %d"
        % (counts.get("open", 0), counts.get("stalled", 0),
           counts.get("won", 0), counts.get("lost", 0)),
        "%d leads" % len(leads),
        "%d deal(s) thin on notes, flagged needs enrichment" % thin,
    ]
    if previous:
        now = {d["name"]: d["stage"] for d in sum(deals.values(), [])}
        was = {d["name"]: d["stage"] for d in sum(previous.values(), [])}
        moved = [(n, was[n], now[n]) for n in now if n in was and was[n] != now[n]]
        added = [n for n in now if n not in was]
        if moved or added:
            lines.append("")
            for n, a, b in moved[:6]:
                lines.append("  moved  %s: %s -> %s" % (n[:34], a, b))
            for n in added[:6]:
                lines.append("  new    %s (%s)" % (n[:34], now[n]))
        else:
            lines.append("  nothing changed stage since the last pull")
    return "\n".join(lines), total


def ask_mda(env: dict, state: dict, pulled: str = "") -> dict:
    post(env, MDA_TEXT.format(pulled=pulled), thread_ts=state["gate_ts"])
    state["step"] = ASK_MDA
    write_state(state)
    return state


def next_reply(env: dict, state: dict) -> dict | None:
    """The oldest reply from Mark that this gate has not already acted on."""
    for m in accepted_replies(env, state["gate_ts"]):
        if m["ts"] not in state.get("consumed", []):
            return m
    return None


def consume(state: dict, msg: dict) -> None:
    state.setdefault("consumed", []).append(msg["ts"])
    write_state(state)


def notify(env: dict, state: dict, text: str) -> None:
    post(env, text, thread_ts=state["gate_ts"])
