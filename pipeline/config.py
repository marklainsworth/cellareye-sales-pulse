"""Static configuration for the Sales Pulse pipeline.

Asana GIDs verified live 2026-07-24. Taxonomy and thresholds follow
docs/data_definitions.md, which is canonical over SALES_PULSE_BUILD_SPEC.md
where the two disagree (see docs/build_decisions.md).
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = REPO_ROOT / "templates" / "sales_pulse.html"
DATA_DIR = REPO_ROOT / "data"
BRIEFS_DIR = REPO_ROOT / "briefs"


def version() -> str:
    """Single version line for the whole pipeline. See VERSION at the repo root."""
    return (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()


# --- Asana projects ----------------------------------------------------------

SALES_PIPELINE_PROJECT = "1214587430477572"
INBOUND_LEADS_PROJECT = "1216056878497593"

SECTIONS = {
    "Cold": "1214587157612922",
    "Warm": "1214587157150176",
    "Qualified": "1214601903352407",
    "Demo": "1214587431234795",
    "Proposal": "1214587336363810",
    "Stalled": "1214588235873011",
    "Closed Won": "1214587336732857",
    "Closed Lost": "1214587364624571",
}

LEAD_SECTIONS = {
    "Ready To Email": "1216056878497594",
    "Linkedin Outreach": "1216607644993202",
}

FIELDS = {
    "channel": "1214587337205105",
    "first_name": "1214587337205112",
    "last_name": "1214587337205114",
    "email": "1214587337205116",
    "phone": "1214587337205118",
    "cellar_size": "1214587337205126",
    "clients": "1214587637337214",
    "arr": "1214587637337216",
    "onboarding_path": "1214587637337218",
    "onboarding_value": "1214587637337223",
    "website": "1214586791774168",
    "business_name": "1216016965299619",
}

# Verified live 2026-08-23 against the project's custom_field_settings.
CHANNEL_OPTION_GIDS = {
    "Sommelier Managed": "1214587337205106",
    "Reserve-Client Direct": "1214587337205107",
    "Cellar Builder": "1214587337205108",
    "Hospitality": "1214587337205109",
    "Retailer-Partner": "1214588439226165",
    "Wine Storage": "1214588235873023",
    "Sommelier Program": "1216016965299601",
    "Direct to Consumer": "1214587337205110",
}

# --- Taxonomy ----------------------------------------------------------------

# Display order for the Target Accounts cards. All 8 always render, zeros included.
CHANNELS = [
    "Sommelier Program",
    "Hospitality",
    "Sommelier Managed",
    "Retailer-Partner",
    "Wine Storage",
    "Cellar Builder",
    "Reserve-Client Direct",
    "Direct to Consumer",
]

CHANNEL_SHORT_NAMES = {
    "Sommelier Program": "Somm Program",
    "Hospitality": "Hospitality",
    "Sommelier Managed": "Somm Managed",
    "Retailer-Partner": "Retailer",
    "Wine Storage": "Wine Storage",
    "Cellar Builder": "Cellar Builder",
    "Reserve-Client Direct": "Reserve Direct",
    "Direct to Consumer": "DTC",
}

OPEN_STAGES = ["Cold", "Warm", "Qualified", "Demo", "Proposal"]
FUNNEL_STAGES = OPEN_STAGES + ["Stalled", "Closed Won", "Closed Lost"]

# Template placeholder suffix for each funnel stage: stage_<key>_count / _fill
STAGE_KEYS = {
    "Cold": "cold", "Warm": "warm", "Qualified": "qualified", "Demo": "demo",
    "Proposal": "proposal", "Stalled": "stalled",
    "Closed Won": "won", "Closed Lost": "lost",
}

# --- Rules -------------------------------------------------------------------

# Days of inactivity before a deal is flagged. docs/data_definitions.md is canonical.
ATTENTION_THRESHOLDS = {
    "Cold": 14, "Warm": 14, "Qualified": 7, "Demo": 10, "Proposal": 14, "Stalled": 21,
}
ATTENTION_CAP = 8
ATTENTION_SORT_ORDER = ["Stalled", "Proposal", "Demo", "Qualified", "Warm", "Cold"]

# Data quality tiers, share of deals with the value assigned.
DQ_TIERS = [(80, "positive"), (50, "warning"), (0, "error")]

COMPANY_STAGE_LABEL = "This Week's Pulse"  # fixed banner label
MDA_PENDING = "Commentary pending."

# --- Slack -------------------------------------------------------------------

SLACK_CHANNEL = None  # set before wiring notifications

# --- Known data defects ------------------------------------------------------

# Joshua Plack exists twice. Verified live 2026-08-23: both tasks now sit in Demo
# (they were in Qualified on 7/24). Until they are merged in Asana this inflates
# whichever stage holds them by one, and it is called out in data_quality_summary.
DUPLICATE_TASKS = {
    "Joshua Plack": [
        ("1214588513835040", "Drink with Me"),
        ("1215968666300621", "Plack, Joshua \u2014 Drink With Me"),
    ],
}
