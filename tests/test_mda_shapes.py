"""The MD&A arrives in two shapes and both must parse.

It is always text by the time it reaches the pipeline, but Mark either types it
or speaks a voice note that transcribes into the chat. Those produce very
different text, and the parser was built for only the first, which is why the
Priorities section failed to render five times running.

  typed        each priority on its own line, "1." or "2)" at line start
  transcribed  run-together sentences, markers mid-line, first item often
               unnumbered, no colons, sometimes no line breaks at all

Run:  python3 tests/test_mda_shapes.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import render  # noqa: E402

TYPED = [
    ("colons, line-start 1.",
     "Pipeline held steady.\n\n1. Send Bottles pricing: the QR module is the hook.\n"
     "2. Fill Pausa ARR: closed with empty fields.\n3. Start lead outreach: zero conversions.", 3),
    ("paren style 1)",
     "Quiet week.\n1) Close Addison\n2) Merge the Plack duplicate\n3) Value Retailer-Partner", 3),
    ("no colons",
     "Two proposals out.\n1. Deliver the Pausa proposal Monday\n2. Finish the Somm pages\n"
     "3. Begin lead outreach", 3),
    ("blank lines between items",
     "Steady.\n\n1. First thing\n\n2. Second thing\n\n3. Third thing", 3),
    ("only two items",
     "Short week.\n1. Ship the pricing\n2. Merge the duplicate", 2),
]

TRANSCRIBED = [
    ("the real 2026-08-23 dictation",
     "This week was busy we got the contract signed by Pausa San Mateo. We also demoed a "
     "restaurant group in Puerto Rico.\nThe priorities were the following week will be doing a "
     "training audit with Pausa Monday. 2.)\nMark will finish Somm pages by Wednesday. 3.) One "
     "ne Somm page is published, Mark and Danielle will begin Lead outreach in full ", 3),
    ("markers inline starting at 1",
     "Good week Pausa signed. Priorities are 1.) send Bottles the pricing 2.) fill in Pausa ARR "
     "3.) start outreach on the lead list", 3),
    ("no cue phrase, markers mid-line",
     "Pausa signed and Bottles demoed well. 1. Send Bottles pricing 2. Fill in Pausa ARR "
     "3. Start lead outreach", 3),
    ("my priorities this week are, first unnumbered",
     "Solid week. My priorities this week are get the Pausa audit done Monday 2) finish the "
     "Somm pages 3) start outreach", 3),
    ("our priorities are",
     "Good week. Our priorities are ship pricing 2) merge the duplicate 3) begin outreach", 3),
    ("priorities colon",
     "Steady. Priorities: send the pricing 2) fill the ARR 3) start outreach", 3),
    ("no line breaks at all",
     "Busy week Pausa signed. The priorities are finish the audit Monday 2.) publish the Somm "
     "page 3.) begin outreach in full", 3),
]

# Numbers appear in ordinary commentary. None of these is a list.
PROSE = [
    ("plain prose", "Just a quiet week, nothing major moved."),
    ("money and percentages", "We closed 2 deals worth $2.5K and saw 3.5 percent growth."),
    ("versions and dates", "Shipped v1.2 on 8/23 and v1.3 is next, roughly 2.5 weeks out."),
    ("a single stray number", "The 2. quarter was slower than expected."),
    ("blank", ""),
]


def main():
    failures = []
    for label, cases in (("TYPED", TYPED), ("DICTATED THEN TRANSCRIBED", TRANSCRIBED)):
        print("=== %s ===" % label)
        for name, text, want in cases:
            banner, prios = render.split_mda(text)
            ok = len(prios) == want and bool(banner)
            print("  %s %-44s priorities=%d want=%d" % ("ok  " if ok else "FAIL", name, len(prios), want))
            if not ok:
                failures.append(name)
        print()

    print("=== MUST STAY PROSE ===")
    for name, text in PROSE:
        banner, prios = render.split_mda(text)
        ok = len(prios) == 0
        print("  %s %-44s priorities=%d" % ("ok  " if ok else "FAIL", name, len(prios)))
        if not ok:
            failures.append(name)
    print()

    if failures:
        print("FAIL: %d shape(s) misparsed: %s" % (len(failures), ", ".join(failures)))
        return 1
    print("PASS: both input shapes parse, and prose with numbers in it does not.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
