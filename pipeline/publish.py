"""Commit, push, and announce the finished brief.

Kept apart from render so the renderer stays pure and offline. Everything here
touches the outside world: git, GitHub, Slack.

The GitHub Action mirrors the newest briefs/2*.html to briefs/latest.html, which
is the stable URL pinned in Slack. Test briefs are named test-<date>.html and so
do not match that glob, which is what keeps a rehearsal off the live link.
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

PAGES = "https://marklainsworth.github.io/cellareye-sales-pulse"
LIVE_URL = PAGES + "/briefs/latest.html"
MIRROR_TIMEOUT = 300   # seconds to wait for the live URL; module-level so tests can shorten it


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

    # The mirror Action commits latest.html on GitHub's side, so origin is
    # almost always ahead of us by the time the next run pushes. Two consecutive
    # runs needed this by hand. Rebase onto it rather than merging, to keep the
    # brief history linear.
    git("fetch", "origin", "main")
    behind = git("rev-list", "--count", "HEAD..origin/main", check=False)
    if behind and behind != "0":
        git("rebase", "origin/main")
        sha = git("rev-parse", "--short", "HEAD")
    git("push", "origin", "main")
    return sha


def fetch_live(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={
        "Cache-Control": "no-cache", "Pragma": "no-cache",
        "User-Agent": "cellareye-sales-pulse/verify"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, urllib.error.HTTPError):
        return ""


def wait_for_mirror(brief_name: str, marker: str, timeout: int | None = None) -> tuple[bool, str]:
    """Confirm the LIVE site is serving this brief. Returns (verified, detail).

    Git state is not proof of publication. On 2026-08-23 the mirror Action ran
    correctly, latest.html matched the dated brief in git, and the site was
    still serving a month-old cached build because every Pages build had been
    failing. The old check reported success and Slack announced a link that was
    live but wrong.

    So this fetches the served HTML and looks for a marker unique to this run,
    the pull timestamp. Anything less can be satisfied by a stale cache.
    """
    deadline = time.time() + (MIRROR_TIMEOUT if timeout is None else timeout)
    last = "no response from the live URL"
    while time.time() < deadline:
        time.sleep(15)
        html = fetch_live(LIVE_URL)
        if not html:
            last = "live URL unreachable"
            continue
        if marker in html:
            return True, "live URL is serving this run (%s)" % marker
        m = re.search(r"Generated ([^<]{0,40})", html)
        last = "live URL still serving %s" % (m.group(1).strip() if m else "older content")
    return False, last


def announce(env, gate_state, brief_name: str, sha: str, counts: dict,
             verified: bool, detail: str, notify_fn) -> None:
    """Announce the truth. An unverified publish is reported as a failure.

    The brief is committed and pushed either way; what is uncertain is whether
    anyone can read it. Saying "published" when the live URL serves something
    else is the failure this whole check exists to prevent.
    """
    total = sum(counts.values())
    counts_line = ("%d deals: open %d, stalled %d, won %d, lost %d"
                   % (total, counts.get("open", 0), counts.get("stalled", 0),
                      counts.get("won", 0), counts.get("lost", 0)))
    if verified:
        lines = [":white_check_mark: *Sales Pulse published*", LIVE_URL, "", counts_line]
        if sha:
            lines.append("_commit %s_" % sha)
    else:
        lines = [
            ":x: *Sales Pulse publish NOT confirmed*",
            "The brief is committed and pushed%s, but the live URL is not serving it."
            % ((" as %s" % sha) if sha else ""),
            "```%s```" % detail,
            "Check the Pages build: "
            "https://github.com/marklainsworth/cellareye-sales-pulse/deployments",
            "",
            "Direct file link, may also be stale: " + dated_url(brief_name),
            counts_line,
        ]
    notify_fn(env, gate_state, "\n".join(lines))
