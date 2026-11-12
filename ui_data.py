"""
Display aggregations for the dashboard.

Every number the UI shows that detectors.py does not return directly is computed here, in small
pure functions with their own tests (tests/test_ui_data.py). app.py only lays these values out.
"""

import re

import pandas as pd

import detectors as d
import theme

PLATFORM_ORDER = ["Google", "Meta"]


# ---------------------------------------------------------------------------
# Identity and lookup
# ---------------------------------------------------------------------------

def finding_id(f):
    """Stable, URL-safe id for a finding: same data -> same id across reruns and reloads."""
    raw = f"{f.issue_type}-{f.account}-{f.campaign}".lower()
    return re.sub(r"[^a-z0-9]+", "-", raw).strip("-")


def severity_of(f):
    return theme.SEVERITY_FOR[f.issue_type]


def find_by_id(findings, issue_id):
    return next((f for f in findings if finding_id(f) == issue_id), None)


# ---------------------------------------------------------------------------
# Workspace header
# ---------------------------------------------------------------------------

def workspace_summary(df):
    platforms = [p for p in PLATFORM_ORDER if p in set(df["platform"])]
    return {
        "today": df["date"].max(),
        "n_accounts": df["account"].nunique(),
        "platforms": platforms,
    }


def export_frame(findings):
    """Findings as a flat table for the CSV export, in triage order."""
    return pd.DataFrame([{
        "severity": theme.SEVERITY[severity_of(f)]["label"],
        "issue": theme.ISSUE_TITLE[f.issue_type],
        "account": f.account,
        "campaign": f.campaign,
        "platform": f.platform,
        "money_at_stake_ils": f.money_at_risk_ils,
        "horizon": f.money_note,
        "evidence": f.evidence,
        "recommended_action": f.action,
    } for f in findings], columns=["severity", "issue", "account", "campaign", "platform",
                                   "money_at_stake_ils", "horizon", "evidence", "recommended_action"])
