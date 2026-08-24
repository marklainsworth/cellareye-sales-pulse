"""Assert the failure paths exit non-zero.

Four times in one evening a failure path posted a correct message to Slack and
then returned 0, telling the scheduler everything was fine. The last one was a
`raise` that silently failed to apply: the exception class was there, the
handler was there, nothing threw. Slack looked perfect.

Under launchd the exit code is the only signal. These tests assert it directly,
so an edit that unwires a raise is caught here rather than by someone happening
to watch a terminal.

Run:  python3 tests/test_exit_codes.py
"""
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

import checks        # noqa: E402
import config        # noqa: E402
import gate_runner   # noqa: E402
import publish       # noqa: E402
import slack_gate as sg  # noqa: E402

FAKE_ENV = {"SLACK_BOT_TOKEN": "x", "SLACK_CHANNEL_ID": "C0", "SLACK_USER_ID": "U0"}


class Harness:
    """Stands in for Slack and the filesystem so only the exit path is under test."""

    def __init__(self, template: str, state: dict):
        self.template = template
        self.state = state
        self.posted = []
        # inside the repo: do_render logs out.relative_to(REPO_ROOT), which
        # raises for a path outside it and would mask the real exit path
        self.tmp = tempfile.TemporaryDirectory(dir=str(ROOT))
        self._saved = {}

    def __enter__(self):
        tpl = Path(self.tmp.name) / "template.html"
        tpl.write_text(self.template, encoding="utf-8")
        self._saved = {
            "TEMPLATE": config.TEMPLATE, "BRIEFS_DIR": config.BRIEFS_DIR,
            "load_env": sg.load_env, "next_reply": sg.next_reply,
            "consume": sg.consume, "notify": sg.notify,
            "read_state": sg.read_state, "write_state": sg.write_state,
            "clear_state": sg.clear_state, "commit_and_push": publish.commit_and_push,
            "fetch_live": publish.fetch_live, "MIRROR_TIMEOUT": publish.MIRROR_TIMEOUT,
        }
        config.TEMPLATE = tpl
        config.BRIEFS_DIR = Path(self.tmp.name)
        sg.load_env = lambda: FAKE_ENV
        sg.next_reply = lambda env, st: {"ts": "9", "text": "some commentary"}
        sg.consume = lambda st, m: None
        sg.notify = lambda env, st, text: self.posted.append(text)
        sg.read_state = lambda: dict(self.state)
        sg.write_state = lambda st: None
        sg.clear_state = lambda: None
        publish.commit_and_push = lambda brief, d, c: "abc1234"
        publish.MIRROR_TIMEOUT = 1
        return self

    def __exit__(self, *a):
        config.TEMPLATE = self._saved["TEMPLATE"]
        config.BRIEFS_DIR = self._saved["BRIEFS_DIR"]
        sg.load_env = self._saved["load_env"]
        sg.next_reply = self._saved["next_reply"]
        sg.consume = self._saved["consume"]
        sg.notify = self._saved["notify"]
        sg.read_state = self._saved["read_state"]
        sg.write_state = self._saved["write_state"]
        sg.clear_state = self._saved["clear_state"]
        publish.commit_and_push = self._saved["commit_and_push"]
        publish.fetch_live = self._saved["fetch_live"]
        publish.MIRROR_TIMEOUT = self._saved["MIRROR_TIMEOUT"]
        self.tmp.cleanup()


def base_state(**over):
    st = {"gate_ts": "1", "step": sg.ASK_MDA, "opened_at": 9e9,
          "render_date": "2026-08-23", "test": False, "allow_any_day": True,
          "pulled_at": "16:19 PT", "consumed": []}
    st.update(over)
    return st


def clean_template():
    return config.REPO_ROOT.joinpath("templates/sales_pulse.html").read_text(encoding="utf-8")


def contaminated_template():
    lines = clean_template().split("\n")
    i = next(n for n, l in enumerate(lines) if l.startswith("@media (max-width: 720px)"))
    lines.insert(i + 2, "```")
    return "\n".join(lines)


def run_case(name, template, live_html, expect):
    with Harness(template, base_state()) as h:
        publish.fetch_live = lambda url, timeout=20: live_html
        rc = gate_runner.main([])
        ok = rc == expect
        print("  %s  %-34s exit=%s expected=%s" % ("ok  " if ok else "FAIL", name, rc, expect))
        last = h.posted[-1] if h.posted else ""
        if last:
            print("       slack said: %s" % last.split("\n")[0][:64])
        # a failure that lands in the generic handler is not the path under test
        if expect == 1 and "hit an error and stopped" in last:
            print("       FAIL: reached the generic handler, not the intended one")
            ok = False
        return ok


def main():
    print("exit-code assertions\n")
    results = []

    # 1. contaminated stylesheet must abort before writing, and exit non-zero
    results.append(run_case("contaminated stylesheet",
                            contaminated_template(), "irrelevant", 1))

    # 2. stale live URL must fail verification, and exit non-zero
    stale = "<html>Generated 20:15 PT · 51 deals tracked</html>"
    results.append(run_case("stale live URL", clean_template(), stale, 1))

    # 3. control: a healthy run must exit 0, so the two above cannot pass by accident
    good = "<html><!-- pulled 16:19 PT --></html>"
    results.append(run_case("healthy run (control)", clean_template(), good, 0))

    # 4. the raise that silently failed to apply, asserted at the source
    import inspect
    src = inspect.getsource(gate_runner.do_render)
    raises = "raise ChecksFailed" in src
    print("  %s  do_render raises ChecksFailed" % ("ok  " if raises else "FAIL"))
    results.append(raises)

    print()
    if all(results):
        print("PASS: every failure path exits non-zero, and the healthy path does not.")
        return 0
    print("FAIL: a failure path is not signalling to the scheduler.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
