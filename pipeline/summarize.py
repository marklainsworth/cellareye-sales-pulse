"""Summarise each deal's Asana prose into one tight line for the brief.

Sits between the pull and the render, which is the only place a model belongs
in this pipeline. pull_asana.py stays deterministic REST; render.py stays pure
and offline. This step writes a `note_summary` field that render.py reads.

Guarantees, in priority order:

  1. NEVER INVENT. The model only compresses prose a human already wrote. It is
     fed one deal at a time, so it cannot blend two deals together, and it never
     sees a metric, a total, or another deal's text.
  2. DEGRADE, DO NOT DIE. If the model call fails or times out, that deal falls
     back to deterministic truncation. A missing summary is survivable; a wrong
     one is not.
  3. STABLE WEEK TO WEEK. Summaries are cached on the deal's content, so an
     untouched deal keeps last week's wording instead of being re-summarised
     into something subtly different.

    python -m pipeline.summarize            # fill in what is missing or stale
    python -m pipeline.summarize --limit 5  # try a handful first
    python -m pipeline.summarize --force    # ignore the cache
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

CACHE = config.DATA_DIR / "note_summaries.json"
TIMEOUT = 120
WORKERS = 4          # isolation is per call, this only cuts wall time
THIN_DESCRIPTION = 60

PROMPT = """You compress sales-deal notes into one short line for a weekly brief.

You are given ONE deal. Two sources:
  DESCRIPTION - who the business is: size, type, background.
  COMMENTS    - where the deal is: latest movement, current state, next step.

Write ONE line, at most 30 words, in this shape:
  <who they are> · <where it is at>

Rules:
  - Use ONLY facts present below. Invent nothing. Add no adjectives of your own.
  - If there are no comments, describe who they are and end with the most useful
    detail from the description. Do not speculate about deal state.
  - If the description is thin, lead with what the comments establish.
  - Keep numbers exactly as written (4 outlets, ~12k bottles, $7-8K/mo).
  - No em dashes. Use commas, periods, parentheses, or the middle dot separator.
  - No preamble, no quotes, no trailing period. Output the line and nothing else.
"""


def cache_key(deal: dict) -> str:
    """Content hash: description plus the identity of the latest comment."""
    latest = deal.get("comments") or []
    marker = latest[-1].get("at", "") if latest else ""
    raw = "%s|%s|%s" % (deal.get("notes", ""), marker, len(latest))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def fallback(deal: dict) -> str:
    """Deterministic. Used when the model is unavailable, never as a silent default."""
    desc = (deal.get("notes") or "").strip()
    comments = deal.get("comments") or []
    who = re.split(r"(?<=[.!?])\s+", desc)[0][:110].strip() if desc else ""
    where = ""
    if comments:
        text = " ".join((comments[-1].get("text") or "").split())
        where = re.split(r"(?<=[.!?])\s+", text)[0][:110].strip()
    parts = [p for p in (who, where) if p]
    return " · ".join(parts) if parts else "no notes recorded"


def needs_enrichment(deal: dict) -> bool:
    """Thin on both sides. The brief says so rather than papering over it."""
    return (not (deal.get("comments") or [])
            and len((deal.get("notes") or "").strip()) < THIN_DESCRIPTION)


def summarise_one(deal: dict) -> tuple[str, bool]:
    """Returns (line, used_model)."""
    desc = (deal.get("notes") or "").strip()
    comments = deal.get("comments") or []
    if not desc and not comments:
        return "no notes recorded", False

    body = ["DEAL: %s" % deal.get("name", ""), "", "DESCRIPTION:", desc or "(none)", ""]
    if comments:
        body.append("COMMENTS (oldest first, use the most recent for deal state):")
        for c in comments:
            body.append("--- %s, %s ---" % (c.get("by") or "unknown", (c.get("at") or "")[:10]))
            body.append((c.get("text") or "").strip())
    else:
        body.append("COMMENTS: (none)")

    try:
        r = subprocess.run(
            ["claude", "-p", PROMPT, "--output-format", "text"],
            input="\n".join(body), capture_output=True, text=True, timeout=TIMEOUT)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return fallback(deal), False
    if r.returncode != 0:
        return fallback(deal), False

    line = " ".join(r.stdout.strip().split())
    if line.startswith("```"):
        line = line.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    line = line.strip().strip('"').rstrip(".")
    line = re.sub(r"\s*—\s*", " - ", line)
    if not line or len(line) > 400:
        return fallback(deal), False
    return line, True


def main(argv=None):
    p = argparse.ArgumentParser(description="Summarise deal notes for the brief.")
    p.add_argument("--limit", type=int, help="only summarise this many deals")
    p.add_argument("--force", action="store_true", help="ignore the cache")
    p.add_argument("--deals", default=str(config.DATA_DIR / "deal_data_current.json"))
    p.add_argument("--dry-run", action="store_true", help="print, do not write")
    a = p.parse_args(argv)

    path = Path(a.deals)
    data = json.loads(path.read_text(encoding="utf-8"))
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() and not a.force else {}

    every = [d for bucket in data.values() for d in bucket]
    todo, reused = [], 0
    for d in every:
        key = cache_key(d)
        hit = cache.get(d["gid"])
        if hit and hit.get("key") == key:
            d["note_summary"] = hit["summary"]
            reused += 1
        else:
            todo.append(d)
    if a.limit:
        todo = todo[:a.limit]

    modelled = 0
    if todo:
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for deal, (line, used) in zip(todo, pool.map(summarise_one, todo)):
                deal["note_summary"] = line
                modelled += int(used)
                cache[deal["gid"]] = {"key": cache_key(deal), "summary": line}

    for d in every:
        d["needs_enrichment"] = needs_enrichment(d)
    thin = sum(1 for d in every if d["needs_enrichment"])
    print("summarised %d (%d via model, %d fell back), reused %d from cache, %d need enrichment"
          % (len(todo), modelled, len(todo) - modelled, reused, thin))

    if a.dry_run:
        for d in todo:
            print("\n  %s [%s]\n    %s" % (d["name"], d["stage"], d.get("note_summary")))
        return 0

    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
