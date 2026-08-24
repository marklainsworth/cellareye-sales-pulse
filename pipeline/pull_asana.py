"""Fetch both Asana projects and write the data JSON the renderer reads.

Deterministic: talks to the Asana REST API directly with a personal access
token. No model sits in the data path, so the golden test means something.

    ASANA_TOKEN is read from config/asana.env (KEY=value), or the environment.

    python -m pipeline.pull_asana            # write data/*.json
    python -m pipeline.pull_asana --dump     # also write the raw notes dump

Notes come from two places and the dump shows both:

  * the task description, which carries the structured "Calculator" line and,
    on older prospect records, a research write-up, and
  * the comment thread, which is where Mark and Danielle put the real call
    notes going forward.

The pull stores both verbatim. Choosing which one reaches the brief, and
summarising it, is a render-time decision and is deliberately not made here.
"""
from __future__ import annotations

import argparse
import json
import os
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

API = "https://app.asana.com/api/1.0"
TIMEOUT = 30
RETRIES = 3

DEAL_FIELDS = ",".join([
    "name", "notes", "modified_at", "created_at",
    "memberships.section.gid", "memberships.section.name",
    "custom_fields.gid", "custom_fields.name",
    "custom_fields.enum_value.name", "custom_fields.number_value",
    "custom_fields.display_value",
])
LEAD_FIELDS = ",".join([
    "name", "modified_at",
    "memberships.section.gid", "memberships.section.name",
    "custom_fields.gid", "custom_fields.enum_value.name",
    "custom_fields.display_value",
])
STORY_FIELDS = "text,created_at,created_by.name,resource_subtype"


# --- transport ---------------------------------------------------------------

def load_token() -> str:
    env = config.REPO_ROOT / "config" / "asana.env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() == "ASANA_TOKEN":
                    return v.strip().strip('"').strip("'")
    token = os.environ.get("ASANA_TOKEN", "").strip()
    if token:
        return token
    raise SystemExit(
        "No Asana token. Put ASANA_TOKEN=... in config/asana.env "
        "(Asana > Settings > Apps > Developer > Personal access token).")


def get(path: str, token: str, **params) -> list:
    """GET one endpoint, following offset pagination to the end."""
    out, offset = [], None
    while True:
        q = dict(params)
        q["limit"] = q.get("limit", 100)
        if offset:
            q["offset"] = offset
        url = "%s%s?%s" % (API, path, urllib.parse.urlencode(q))
        req = urllib.request.Request(url, headers={
            "Authorization": "Bearer %s" % token,
            "Accept": "application/json",
        })
        body = None
        for attempt in range(RETRIES):
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                    body = json.loads(r.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < RETRIES - 1:
                    time.sleep(int(e.headers.get("Retry-After", 2)))
                    continue
                raise SystemExit("Asana %s on %s: %s" % (e.code, path, e.read()[:300]))
            except urllib.error.URLError as e:
                if attempt < RETRIES - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise SystemExit("Asana unreachable: %s" % e)
        out.extend(body.get("data", []))
        offset = (body.get("next_page") or {}).get("offset")
        if not offset:
            return out


# --- field helpers -----------------------------------------------------------

def field(task: dict, gid: str):
    for f in task.get("custom_fields") or []:
        if f.get("gid") == gid:
            if f.get("number_value") is not None:
                return f["number_value"]
            if (f.get("enum_value") or {}).get("name"):
                return f["enum_value"]["name"]
            dv = f.get("display_value")
            return dv if dv not in ("", "-", "—") else None
    return None


def section_of(task: dict) -> str | None:
    for m in task.get("memberships") or []:
        name = (m.get("section") or {}).get("name")
        if name in config.SECTIONS:
            return name
    for m in task.get("memberships") or []:
        if (m.get("section") or {}).get("name"):
            return m["section"]["name"]
    return None


# --- description cleaning ----------------------------------------------------

LEAD_EMOJI = re.compile(r"^[\U0001F300-\U0001FAFF☀-➿️\s]+")
CALC_PREFIX = re.compile(r"^Calculator\s*:\s*", re.I)


def clean_description(text: str | None) -> str:
    """Strip the emoji and Calculator prefix, flatten to one line, no em dashes.

    '📊 Calculator: Sommeliers Path B | 5 clients | 2,000 bottles avg'
      -> 'Sommeliers Path B | 5 clients | 2,000 bottles avg'
    """
    if not text:
        return ""
    lines = [ln.strip() for ln in text.replace("\r", "").split("\n")]
    lines = [ln for ln in lines if ln]
    cleaned = []
    for ln in lines:
        ln = LEAD_EMOJI.sub("", ln)
        ln = CALC_PREFIX.sub("", ln)
        if ln:
            cleaned.append(ln)
    one = " ".join(cleaned)
    one = re.sub(r"\s*—\s*", " - ", one)
    one = re.sub(r"–", "-", one)
    return re.sub(r"\s{2,}", " ", one).strip()


# --- pulls -------------------------------------------------------------------

def pull_deals(token: str, with_comments: bool = True) -> tuple[dict, list]:
    tasks = get("/projects/%s/tasks" % config.SALES_PIPELINE_PROJECT, token,
                opt_fields=DEAL_FIELDS)
    records, dump = [], []
    for t in tasks:
        stage = section_of(t)
        comments = []
        if with_comments:
            stories = get("/tasks/%s/stories" % t["gid"], token, opt_fields=STORY_FIELDS)
            comments = [{
                "at": s.get("created_at"),
                "by": (s.get("created_by") or {}).get("name"),
                "text": (s.get("text") or "").strip(),
            } for s in stories if s.get("resource_subtype") == "comment_added"]
            comments.sort(key=lambda c: c["at"] or "")
        rec = {
            "gid": t["gid"],
            "name": t.get("name", "").strip(),
            "first": field(t, config.FIELDS["first_name"]),
            "last": field(t, config.FIELDS["last_name"]),
            "channel": field(t, config.FIELDS["channel"]),
            "arr": field(t, config.FIELDS["arr"]),
            "onb": field(t, config.FIELDS["onboarding_value"]),
            "stage": stage,
            "modified_at": t.get("modified_at"),
            "notes": clean_description(t.get("notes")),
            "comments": comments[-2:],
        }
        records.append(rec)
        dump.append({
            "gid": rec["gid"], "name": rec["name"], "stage": stage,
            "description_raw": (t.get("notes") or "").strip(),
            "description_clean": rec["notes"],
            "comments": comments,
        })

    buckets = {"open": [], "stalled": [], "won": [], "lost": []}
    for r in records:
        s = r["stage"]
        key = ("open" if s in config.OPEN_STAGES else
               "stalled" if s == "Stalled" else
               "won" if s == "Closed Won" else
               "lost" if s == "Closed Lost" else None)
        if key:
            buckets[key].append(r)

    order = {s: i for i, s in enumerate(config.OPEN_STAGES)}
    buckets["open"].sort(key=lambda d: (order.get(d["stage"], 99), -(d["onb"] or 0)))
    for k in ("stalled", "won", "lost"):
        buckets[k].sort(key=lambda d: -(d["onb"] or 0))
    return buckets, dump


def pull_leads(token: str) -> list:
    tasks = get("/projects/%s/tasks" % config.INBOUND_LEADS_PROJECT, token,
                opt_fields=LEAD_FIELDS)
    out = []
    for t in tasks:
        out.append({
            "business": t.get("name", "").strip(),
            "first": field(t, config.FIELDS["first_name"]),
            "last": field(t, config.FIELDS["last_name"]),
            "channel": field(t, config.FIELDS["channel"]),
            "section": section_of(t),
        })
    return out


def apply_overrides(deals: dict) -> int:
    """deal_notes.json is optional. When present it overrides notes by task GID."""
    path = config.DATA_DIR / "deal_notes.json"
    if not path.exists():
        return 0
    overrides = json.loads(path.read_text(encoding="utf-8"))
    n = 0
    for bucket in deals.values():
        for d in bucket:
            if d["gid"] in overrides:
                d["notes"] = overrides[d["gid"]]
                n += 1
    return n


def main(argv=None):
    p = argparse.ArgumentParser(description="Pull both Asana projects.")
    p.add_argument("--dump", action="store_true",
                   help="also write data/notes_dump.md and notes_dump.json")
    p.add_argument("--no-comments", action="store_true",
                   help="skip the per-task comment fetch (one call per deal)")
    p.add_argument("--out-dir", default=str(config.DATA_DIR))
    a = p.parse_args(argv)

    token = load_token()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # keep the prior lead set so added/qualified this week can be diffed later
    leads_path = out / "lead_data_current.json"
    if leads_path.exists():
        (out / "lead_data_previous.json").write_text(
            leads_path.read_text(encoding="utf-8"), encoding="utf-8")

    deals, dump = pull_deals(token, with_comments=not a.no_comments)
    leads = pull_leads(token)
    overridden = apply_overrides(deals)

    (out / "deal_data_current.json").write_text(
        json.dumps(deals, ensure_ascii=False, indent=1), encoding="utf-8")
    leads_path.write_text(json.dumps(leads, ensure_ascii=False, indent=1), encoding="utf-8")

    pulled_at = datetime.now(timezone.utc).isoformat()
    counts = {k: len(v) for k, v in deals.items()}
    print("pulled %s  deals %s total %d  leads %d  overrides applied %d"
          % (pulled_at, counts, sum(counts.values()), len(leads), overridden))

    if a.dump:
        (out / "notes_dump.json").write_text(
            json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8")
        (out / "notes_dump.md").write_text(render_dump(dump), encoding="utf-8")
        rich = sum(1 for d in dump if d["comments"])
        print("dump: %d deals, %d with comments, %d description only"
              % (len(dump), rich, len(dump) - rich))
    return 0


def render_dump(dump: list) -> str:
    """Human-readable spread: cleaned description and every comment, per deal."""
    lines = ["# Asana notes dump", "",
             "For each deal: the cleaned description, then the comment thread.",
             "This is the raw material the summariser compresses.", ""]
    by_stage = {}
    for d in dump:
        by_stage.setdefault(d["stage"] or "no section", []).append(d)
    for stage in list(config.OPEN_STAGES) + ["Stalled", "Closed Won", "Closed Lost"]:
        if stage not in by_stage:
            continue
        lines += ["", "## %s (%d)" % (stage, len(by_stage[stage])), ""]
        for d in by_stage[stage]:
            lines.append("### %s  `%s`" % (d["name"], d["gid"]))
            lines.append("")
            lines.append("**description (cleaned):** %s" % (d["description_clean"] or "_empty_"))
            if d["comments"]:
                lines.append("")
                lines.append("**comments (%d):**" % len(d["comments"]))
                for c in d["comments"]:
                    when = (c["at"] or "")[:10]
                    lines.append("")
                    lines.append("- _%s, %s_" % (c["by"] or "unknown", when))
                    for ln in c["text"].split("\n"):
                        lines.append("  %s" % ln if ln.strip() else "")
            else:
                lines.append("")
                lines.append("**comments:** none")
            lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
