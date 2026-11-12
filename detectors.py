"""
Spendhound detectors.

One pure function per problem: DataFrame in -> list[Finding] out. No I/O, no UI, no randomness,
so every number here is reproducible and covered by tests (rule #1 in CLAUDE.md).

Expected columns: date, account, platform, campaign, monthly_budget,
                  cost, impressions, clicks, conversions, revenue
"""

import calendar
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Thresholds. Each one is a product decision, so each one says why.
# ---------------------------------------------------------------------------

# Zero-conversion burner
BURNER_WINDOW_DAYS = 14         # two full weeks smooths out day-of-week swings
BURNER_MIN_SPEND = 2_000        # below this the waste is too small to interrupt anyone
BURNER_MAX_CONVERSIONS = 1      # "approximately zero": one lucky sale doesn't make it healthy

# Broken tracking
TRACKING_MIN_ZERO_DAYS = 3      # one or two zero days can be noise; three in a row is a signal
TRACKING_BASELINE_DAYS = 14
TRACKING_MIN_BASELINE_CONV = 2  # only campaigns that normally convert daily can "go silent"
TRACKING_CLICK_BAND = (0.7, 1.3)  # traffic within +/-30% of normal => buyers still arrive
TRACKING_PROJECTION_DAYS = 7    # assume someone notices within a week

# Overpacing
OVERPACE_RUN_RATE_DAYS = 7
OVERPACE_TOLERANCE = 1.10       # flag if projected month spend > 110% of budget
OVERPACE_MIN_DAYS_ELAPSED = 3   # too early in the month to project reliably

# Creative fatigue
FATIGUE_WINDOW_DAYS = 21        # "2+ weeks" of steady decline
FATIGUE_MIN_DECLINE = 0.30      # trend line loses >= 30% of its starting CTR
FATIGUE_MIN_R2 = 0.60           # the decline must be consistent, not one bad day
FATIGUE_SPEND_RUN_RATE_DAYS = 7

# Underfunded winner
WINNER_WINDOW_DAYS = 30
WINNER_MIN_ROAS = 4.0
WINNER_MIN_ROAS_MULTIPLE = 2.0  # vs. the rest of the same account
WINNER_CAP_DAYS = 14
WINNER_CAP_SHARE = 0.95         # spend >= 95% of daily budget counts as "hitting the cap"
WINNER_MIN_CAPPED_DAY_SHARE = 0.80
WINNER_SCALE_EFFICIENCY = 0.5   # conservative: extra budget earns half the current ROAS

PROJECTION_DAYS = 30            # "money at risk" horizons are per 30 days unless stated

ISSUE_INFO = {
    "zero_conversion_burner": {
        "label": "Burning spend, no conversions", "kind": "risk",
        "money_note": "spend at risk over the next 30 days",
        "action": "Pause or cut budget, then audit targeting, landing page and offer.",
    },
    "broken_tracking": {
        "label": "Tracking looks broken", "kind": "risk",
        "money_note": "spent blind so far + next 7 days",
        "action": "Check the conversion tag/pixel and recent site deploys before changing bids.",
    },
    "overpacing": {
        "label": "Budget overpacing", "kind": "risk",
        "money_note": "projected overspend this month",
        "action": "Lower the daily budget or check for an accidental budget/bid change.",
    },
    "creative_fatigue": {
        "label": "Creative fatigue", "kind": "risk",
        "money_note": "spend lost to lower CTR, next 30 days",
        "action": "Rotate in fresh creative; the audience has stopped responding to these ads.",
    },
    "underfunded_winner": {
        "label": "Underfunded winner", "kind": "opportunity",
        "money_note": "potential net gain per month",
        "action": "Raise the budget gradually (e.g. +30%/week) while watching ROAS.",
    },
}


@dataclass
class Finding:
    account: str
    campaign: str
    platform: str
    issue_type: str
    evidence: str
    money_at_risk_ils: float
    metrics: dict = field(default_factory=dict)   # raw numbers behind the evidence (for charts/tests)

    @property
    def label(self):
        return ISSUE_INFO[self.issue_type]["label"]

    @property
    def kind(self):
        return ISSUE_INFO[self.issue_type]["kind"]

    @property
    def action(self):
        return ISSUE_INFO[self.issue_type]["action"]

    @property
    def money_note(self):
        return ISSUE_INFO[self.issue_type]["money_note"]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _today(df):
    return df["date"].max()


def _last_days(df, days):
    return df[df["date"] > _today(df) - pd.Timedelta(days=days)]


def _campaigns(df):
    """Yields (account, campaign, platform, rows sorted by date) for every campaign."""
    for (account, campaign), rows in df.groupby(["account", "campaign"], sort=True):
        yield account, campaign, rows["platform"].iloc[0], rows.sort_values("date")


def _ils(x):
    return f"₪{x:,.0f}"


def campaign_summary(df, days=30):
    """Per-campaign totals and ratios over the last `days` days."""
    recent = _last_days(df, days)
    s = (recent.groupby(["account", "campaign", "platform"], as_index=False)
         [["cost", "impressions", "clicks", "conversions", "revenue"]].sum())
    s["ctr"] = s["clicks"] / s["impressions"]
    s["cpa"] = s["cost"] / s["conversions"].replace(0, np.nan)
    s["roas"] = s["revenue"] / s["cost"]
    return s


def daily_series(df, account, campaign):
    """Daily rows for one campaign, with CTR and ROAS added."""
    rows = df[(df["account"] == account) & (df["campaign"] == campaign)].sort_values("date").copy()
    rows["ctr"] = rows["clicks"] / rows["impressions"]
    rows["roas"] = rows["revenue"] / rows["cost"]
    return rows


def pacing_series(df, account, campaign):
    """Month-to-date cumulative spend, plus the straight-line projection to month end."""
    rows = daily_series(df, account, campaign)
    today = _today(df)
    month_start = today.replace(day=1)
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    mtd = rows[rows["date"] >= month_start].copy()
    mtd["cumulative"] = mtd["cost"].cumsum()

    run_rate = rows.tail(OVERPACE_RUN_RATE_DAYS)["cost"].mean()
    future_dates = pd.date_range(today, month_start + pd.Timedelta(days=days_in_month - 1))
    projected = pd.DataFrame({
        "date": future_dates,
        "cumulative": mtd["cumulative"].iloc[-1] + run_rate * np.arange(len(future_dates)),
    })
    return mtd[["date", "cumulative"]], projected


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

def detect_zero_conversion_burners(df):
    findings = []
    recent = _last_days(df, BURNER_WINDOW_DAYS)
    for account, campaign, platform, rows in _campaigns(recent):
        spend, conversions = rows["cost"].sum(), int(rows["conversions"].sum())
        if spend >= BURNER_MIN_SPEND and conversions <= BURNER_MAX_CONVERSIONS:
            daily = spend / len(rows)
            findings.append(Finding(
                account, campaign, platform, "zero_conversion_burner",
                evidence=(f"Spent {_ils(spend)} in the last {BURNER_WINDOW_DAYS} days "
                          f"with {conversions} conversion{'s' if conversions != 1 else ''}."),
                money_at_risk_ils=round(daily * PROJECTION_DAYS),
                metrics={"spend": spend, "conversions": conversions, "daily_spend": daily},
            ))
    return findings


def detect_broken_tracking(df):
    findings = []
    for account, campaign, platform, rows in _campaigns(df):
        conv = rows["conversions"].to_numpy()
        streak = 0
        while streak < len(conv) and conv[-1 - streak] == 0:
            streak += 1
        if streak < TRACKING_MIN_ZERO_DAYS:
            continue

        broken = rows.tail(streak)
        baseline = rows.iloc[:-streak].tail(TRACKING_BASELINE_DAYS)
        if len(baseline) < TRACKING_BASELINE_DAYS // 2:
            continue   # never had a "normal" period (e.g. a campaign that never converted)

        base_conv = baseline["conversions"].mean()
        click_ratio = broken["clicks"].mean() / baseline["clicks"].mean()
        low, high = TRACKING_CLICK_BAND
        if base_conv >= TRACKING_MIN_BASELINE_CONV and low <= click_ratio <= high:
            blind_spend = broken["cost"].sum()
            findings.append(Finding(
                account, campaign, platform, "broken_tracking",
                evidence=(f"0 conversions for the last {streak} days (normally {base_conv:.1f}/day), "
                          f"while clicks held at {click_ratio:.0%} of normal. "
                          f"{_ils(blind_spend)} has been spent without measurement."),
                money_at_risk_ils=round(blind_spend + broken["cost"].mean() * TRACKING_PROJECTION_DAYS),
                metrics={"zero_days": streak, "break_start": broken["date"].iloc[0],
                         "baseline_conversions": base_conv, "click_ratio": click_ratio,
                         "blind_spend": blind_spend},
            ))
    return findings


def detect_overpacing(df):
    findings = []
    today = _today(df)
    month_start = today.replace(day=1)
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    days_elapsed = today.day
    days_left = days_in_month - days_elapsed
    if days_elapsed < OVERPACE_MIN_DAYS_ELAPSED:
        return findings

    for account, campaign, platform, rows in _campaigns(df):
        budget = rows["monthly_budget"].iloc[-1]
        mtd = rows[rows["date"] >= month_start]["cost"].sum()
        run_rate = rows.tail(OVERPACE_RUN_RATE_DAYS)["cost"].mean()
        projected = mtd + run_rate * days_left
        if projected <= budget * OVERPACE_TOLERANCE:
            continue

        remaining = budget - mtd
        runs_out = today + pd.Timedelta(days=max(0, math.ceil(remaining / run_rate)))
        findings.append(Finding(
            account, campaign, platform, "overpacing",
            evidence=(f"On track to spend {_ils(projected)} this month vs. a {_ils(budget)} budget "
                      f"({projected / budget:.0%}). At {_ils(run_rate)}/day the budget runs out "
                      f"around {runs_out:%d %b}, {(month_start + pd.Timedelta(days=days_in_month - 1) - runs_out).days} days early."),
            money_at_risk_ils=round(projected - budget),
            metrics={"budget": budget, "mtd_spend": mtd, "run_rate": run_rate,
                     "projected": projected, "runs_out": runs_out},
        ))
    return findings


def detect_creative_fatigue(df):
    findings = []
    recent = _last_days(df, FATIGUE_WINDOW_DAYS)
    for account, campaign, platform, rows in _campaigns(recent):
        ctr = (rows["clicks"] / rows["impressions"]).to_numpy()
        x = np.arange(len(ctr))
        slope, intercept = np.polyfit(x, ctr, 1)
        fitted = intercept + slope * x
        start, end = fitted[0], fitted[-1]
        decline = 1 - end / start
        r2 = 1 - ((ctr - fitted) ** 2).sum() / ((ctr - ctr.mean()) ** 2).sum()

        if decline >= FATIGUE_MIN_DECLINE and r2 >= FATIGUE_MIN_R2:
            daily_spend = rows.tail(FATIGUE_SPEND_RUN_RATE_DAYS)["cost"].mean()
            findings.append(Finding(
                account, campaign, platform, "creative_fatigue",
                evidence=(f"CTR fell {decline:.0%} over {len(ctr)} days ({start:.2%} -> {end:.2%}), "
                          f"a steady decline (R² = {r2:.2f}). The same budget now buys "
                          f"{decline:.0%} fewer clicks."),
                money_at_risk_ils=round(daily_spend * PROJECTION_DAYS * decline),
                metrics={"ctr_start": start, "ctr_end": end, "decline": decline, "r2": r2,
                         "trend_dates": rows["date"].tolist(), "trend_values": fitted.tolist()},
            ))
    return findings


def detect_underfunded_winners(df):
    findings = []
    summary = campaign_summary(df, WINNER_WINDOW_DAYS)
    capped_window = _last_days(df, WINNER_CAP_DAYS)

    for _, row in summary.iterrows():
        others = summary[(summary["account"] == row["account"]) & (summary["campaign"] != row["campaign"])]
        others_roas = others["revenue"].sum() / others["cost"].sum()
        if row["roas"] < WINNER_MIN_ROAS or row["roas"] < WINNER_MIN_ROAS_MULTIPLE * others_roas:
            continue

        days = capped_window[(capped_window["account"] == row["account"])
                             & (capped_window["campaign"] == row["campaign"])]
        daily_cap = days["monthly_budget"] / days["date"].dt.days_in_month
        capped_share = (days["cost"] >= WINNER_CAP_SHARE * daily_cap).mean()
        if capped_share < WINNER_MIN_CAPPED_DAY_SHARE:
            continue   # great ROAS but not budget-limited: more budget wouldn't get spent

        cap = daily_cap.iloc[-1]
        extra_spend = cap * PROJECTION_DAYS            # i.e. double the budget
        net_gain = extra_spend * (row["roas"] * WINNER_SCALE_EFFICIENCY - 1)
        findings.append(Finding(
            row["account"], row["campaign"], row["platform"], "underfunded_winner",
            evidence=(f"ROAS {row['roas']:.1f} vs. {others_roas:.1f} for the rest of the account, "
                      f"yet it hit its {_ils(cap)}/day budget cap on {capped_share:.0%} of the last "
                      f"{WINNER_CAP_DAYS} days. Doubling the budget could net ~{_ils(net_gain)}/month "
                      f"(assuming extra spend earns only half the current ROAS)."),
            money_at_risk_ils=round(net_gain),
            metrics={"roas": row["roas"], "others_roas": others_roas,
                     "daily_cap": cap, "capped_share": capped_share},
        ))
    return findings


DETECTORS = [
    detect_zero_conversion_burners,
    detect_broken_tracking,
    detect_overpacing,
    detect_creative_fatigue,
    detect_underfunded_winners,
]


def run_all(df):
    """Runs every detector; returns findings sorted by money at risk, highest first."""
    findings = [f for detector in DETECTORS for f in detector(df)]
    return sorted(findings, key=lambda f: f.money_at_risk_ils, reverse=True)


def load_data(path):
    return pd.read_csv(path, parse_dates=["date"])
