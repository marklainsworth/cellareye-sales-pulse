"""The out-of-band nudge: a push that does not depend on Slack.

Slack suppresses mobile push while it thinks you are active on desktop, and
"active" includes a forgotten browser tab on another desktop. That makes the
Friday buzz conditional on something Mark cannot see or remember, and a gate he
never notices is a gate that does not fire. So the nudge rides its own channel.

ntfy.sh rather than iMessage on purpose. iMessage needs a macOS Automation
grant, and TCC grants attach to the responsible process, so one that works from
Terminal can silently fail when launchd runs the same script. That is precisely
the quiet-Friday failure we are designing out. This is one HTTPS POST with no
permissions involved.

The topic is the only secret. Anyone who knows it can publish, so it is random
and lives in config/ntfy.env, gitignored. The nudge itself carries no data, only
"go answer the gate".
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

ENV = config.REPO_ROOT / "config" / "ntfy.env"
TIMEOUT = 15


def load() -> dict:
    """Returns {} when unconfigured. The nudge is an enhancement, never a gate."""
    if not ENV.exists():
        return {}
    out = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def send(title: str, message: str, click: str | None = None,
         priority: str = "high", tags: str = "bell") -> tuple[bool, str]:
    """Best effort. Returns (sent, detail) and never raises.

    A failed nudge must not stop the gate from opening: the Slack message is the
    real artefact, this only tells Mark to go look at it.
    """
    cfg = load()
    topic = cfg.get("NTFY_TOPIC")
    if not topic:
        return False, "not configured (config/ntfy.env missing NTFY_TOPIC)"

    server = cfg.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    headers = {
        "Title": title,
        "Priority": priority,
        "Tags": tags,
        "Content-Type": "text/plain; charset=utf-8",
    }
    if click:
        headers["Click"] = click
    if cfg.get("NTFY_TOKEN"):
        headers["Authorization"] = "Bearer " + cfg["NTFY_TOKEN"]

    req = urllib.request.Request("%s/%s" % (server, topic),
                                 data=message.encode("utf-8"), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = json.loads(r.read().decode("utf-8") or "{}")
        return True, "delivered (id %s)" % body.get("id", "?")
    except urllib.error.HTTPError as e:
        return False, "ntfy %s: %s" % (e.code, e.read()[:120].decode("utf-8", "replace"))
    except urllib.error.URLError as e:
        return False, "ntfy unreachable: %s" % e


def slack_deep_link(team_id: str, channel_id: str) -> str:
    return "slack://channel?team=%s&id=%s" % (team_id, channel_id)


def pulse_ready(team_id: str, channel_id: str) -> tuple[bool, str]:
    return send(
        title="It's Time!!!",
        message="Sales Pulse is ready. Answer in #sales-pulse.",
        click=slack_deep_link(team_id, channel_id),
        priority="high",
        tags="wine_glass",
    )
