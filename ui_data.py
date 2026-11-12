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


def severity_counts(findings):
    counts = {s: 0 for s in theme.SEVERITY_ORDER}
    for f in findings:
        counts[severity_of(f)] += 1
    return counts


# ---------------------------------------------------------------------------
# KPI strip
# ---------------------------------------------------------------------------

KPI_SPEND_DAYS = 30   # "Spend, last 30 days" and the "% of spend at risk" denominator


def kpis(df, findings):
    """All numbers for the KPI strip. "At risk" sums risk findings only; upside is kept separate."""
    risk = [f for f in findings if f.kind == "risk"]
    upside = [f for f in findings if f.kind == "opportunity"]
    spend = float(d.campaign_summary(df, days=KPI_SPEND_DAYS)["cost"].sum())
    at_risk = float(sum(f.money_at_risk_ils for f in risk))

    by_severity = {s: 0.0 for s in (theme.CRITICAL, theme.WARNING)}
    for f in risk:
        by_severity[severity_of(f)] += f.money_at_risk_ils

    # One bar segment per risk finding, critical first, each biggest-first.
    ordered = sorted(risk, key=lambda f: (theme.SEVERITY_ORDER.index(severity_of(f)),
                                          -f.money_at_risk_ils))
    segments = [{"severity": severity_of(f), "amount": f.money_at_risk_ils,
                 "share": f.money_at_risk_ils / at_risk} for f in ordered] if at_risk else []

    return {
        "spend_30d": spend,
        "at_risk": at_risk,
        "at_risk_by_severity": by_severity,
        "at_risk_segments": segments,
        "pct_spend_at_risk": at_risk / spend if spend else 0.0,
        "upside": float(sum(f.money_at_risk_ils for f in upside)),
        "n_upside": len(upside),
        "n_open": len(findings),
        "severity_counts": severity_counts(findings),
        "accounts_affected": len({f.account for f in findings}),
        "n_accounts": df["account"].nunique(),
    }


# ---------------------------------------------------------------------------
# Triage table
# ---------------------------------------------------------------------------

SPARK_DAYS = 14

# What the 14-day sparkline plots for each issue type, and whether its last point is the anomaly.
SPARK_METRIC = {
    "broken_tracking": ("conversions", True),
    "zero_conversion_burner": ("cost", False),
    "overpacing": ("cumulative_cost", True),
    "creative_fatigue": ("ctr", True),
    "underfunded_winner": ("roas", False),
}


def filter_findings(findings, severity="all", account=None, platform=None, query="", hidden=()):
    q = (query or "").strip().lower()
    return [f for f in findings
            if (severity in (None, "all") or severity_of(f) == severity)
            and (account in (None, "All accounts") or f.account == account)
            and (platform in (None, "All") or f.platform == platform)
            and (not q or q in f.campaign.lower() or q in f.account.lower()
                 or q in theme.ISSUE_TITLE[f.issue_type].lower())
            and finding_id(f) not in hidden]


def signal_line(f):
    """One-line evidence for the table, built only from numbers the detector returned."""
    m = f.metrics
    if f.issue_type == "broken_tracking":
        return (f"0 conversions for {m['zero_days']} days · clicks at "
                f"{m['click_ratio']:.0%} of normal")
    if f.issue_type == "zero_conversion_burner":
        n = m["conversions"]
        return (f"₪{m['spend']:,.0f} spent in {d.BURNER_WINDOW_DAYS} days · "
                f"{n} conversion{'s' if n != 1 else ''}")
    if f.issue_type == "overpacing":
        return (f"Projected ₪{m['projected']:,.0f} vs ₪{m['budget']:,.0f} monthly budget "
                f"({m['projected'] / m['budget'] - 1:+.0%})")
    if f.issue_type == "creative_fatigue":
        return (f"CTR down {m['decline']:.0%} over {d.FATIGUE_WINDOW_DAYS} days "
                f"({m['ctr_start']:.2%} → {m['ctr_end']:.2%})")
    if f.issue_type == "underfunded_winner":
        return (f"ROAS {m['roas']:.1f} vs {m['others_roas']:.1f} rest of account · "
                f"budget-capped {m['capped_share']:.0%} of the last {d.WINNER_CAP_DAYS} days")
    return f.evidence


def spark_series(df, f, days=SPARK_DAYS):
    """The last `days` daily values of the metric that shows this issue best."""
    metric, _ = SPARK_METRIC[f.issue_type]
    rows = d.daily_series(df, f.account, f.campaign).tail(days)
    if metric == "cumulative_cost":
        return rows["cost"].cumsum().tolist()
    return rows[metric].tolist()


# ---------------------------------------------------------------------------
# Review state carried in the URL (comma-separated finding ids)
# ---------------------------------------------------------------------------

def parse_ids(value):
    return [i for i in (value or "").split(",") if i]


def toggle_id(ids, issue_id):
    return [i for i in ids if i != issue_id] if issue_id in ids else [*ids, issue_id]


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
