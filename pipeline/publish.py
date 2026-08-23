"""Commit, push, and announce the finished brief.

Kept apart from render so the renderer stays pure and offline. Everything here
touches the outside world: git, GitHub, Slack.

The GitHub Action mirrors the newest briefs/2*.html to briefs/latest.html, which
is the stable URL pinned in Slack. Test briefs are named test-<date>.html and so
do not match that glob, which is what keeps a rehearsal off the live link.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

PAGES = "https://marklainsworth.github.io/cellareye-sales-pulse"
LIVE_URL = PAGES + "/briefs/latest.html"


def dated_url(name: str) -> str:
    return "%s/briefs/%s" % (PAGES, name)


def git(*args, check=True):
    r = subprocess.run(["git", *args], cwd=str(config.REPO_ROOT),
                       capture_output=True, text=True, timeout=120)
    if check and r.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), r.stderr.strip()[:300]))
    return r.stdout.strip()


def commit_and_push(brief: Path, render_date, counts: dict) -> str:
    """Commit the brief plus the data snapshot it was built from, and push.

    The data files go in with it deliberately: a brief you cannot reproduce from
    what is in the repo is not much of an archive.
    """
    rel = str(brief.relative_to(config.REPO_ROOT))
    paths = [rel, "data/deal_data_current.json", "data/lead_data_current.json"]
    existing = [p for p in paths if (config.REPO_ROOT / p).exists()]
    git("add", *existing)

    if not git("diff", "--cached", "--name-only"):
        return ""                      # nothing changed, nothing to push

    total = sum(counts.values())
    subject = "Sales Pulse %s" % render_date.isoformat()
    body = ("%d deals (open %d, stalled %d, won %d, lost %d)\n"
            % (total, counts.get("open", 0), counts.get("stalled", 0),
               counts.get("won", 0), counts.get("lost", 0)))
    git("commit", "-m", subject, "-m", body)
    sha = git("rev-parse", "--short", "HEAD")
    git("push", "origin", "main")
    return sha


def wait_for_mirror(brief_name: str, timeout: int = 240) -> bool:
    """Wait for the Action to copy the dated brief to latest.html.

    Polls the remote rather than the local clone, since the Action commits on
    GitHub's side. Returns False on timeout rather than raising: a brief that is
    published but not yet mirrored is a delay, not a failure.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(15)
        try:
            git("fetch", "origin", "main", check=False)
            head = git("rev-parse", "origin/main", check=False)
            latest = git("show", "%s:briefs/latest.html" % head, check=False)
            dated = git("show", "%s:briefs/%s" % (head, brief_name), check=False)
            if latest and dated and latest == dated:
                return True
        except RuntimeError:
            pass
    return False


def announce(env, gate_state, brief_name: str, sha: str, counts: dict,
             mirrored: bool, notify_fn) -> None:
    total = sum(counts.values())
    lines = [
        ":white_check_mark: *Sales Pulse published*",
        "%s" % (LIVE_URL if mirrored else dated_url(brief_name)),
        "",
        "%d deals: open %d, stalled %d, won %d, lost %d"
        % (total, counts.get("open", 0), counts.get("stalled", 0),
           counts.get("won", 0), counts.get("lost", 0)),
    ]
    if sha:
        lines.append("_commit %s_" % sha)
    if not mirrored:
        lines.append("_latest.html has not mirrored yet; the dated link above is live now._")
    notify_fn(env, gate_state, "\n".join(lines))
