"""
Synthetic ad-account data for Spendhound.

3 fictional agency clients x 4 campaigns (Google + Meta) x 60 days, with 5 planted problems.
`generate(seed, plant_problems=False)` produces the same accounts with every campaign healthy;
the tests use that to prove the detectors raise zero false alarms.

Run:  python generate_data.py      -> writes data/ad_data.csv
"""

import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

END_DATE = date(2026, 11, 12)          # "today": November is a month in progress
DAYS = 60
OUTPUT_FILE = Path(__file__).parent / "data" / "ad_data.csv"

# Healthy campaigns get a monthly budget with 5% headroom over their normal daily spend.
BUDGET_HEADROOM = 1.05

# --- How each planted problem is simulated ---
BURNER_CVR = 0.00005            # practically no one converts
TRACKING_BROKEN_DAYS = 6        # last N days: conversions recorded as 0, traffic unchanged
OVERPACE_MULTIPLIER = 1.6       # spend jumps 60% from the 1st of the current month
FATIGUE_DAYS = 24               # CTR decays over the last N days...
FATIGUE_CTR_DROP = 0.55         # ...losing 55% of its starting value
WINNER_CVR = 0.027              # converts ~2x better than its healthy version

# Each campaign: daily_budget (ILS), cpm (ILS per 1,000 impressions), ctr, cvr (click -> purchase),
# aov (average order value, ILS). `problem` is only applied when plant_problems=True.
ACCOUNTS = {
    "Olive & Thyme Bistro": [
        dict(campaign="Google_Search_Reservations", platform="Google",
             daily_budget=400, cpm=90, ctr=0.060, cvr=0.030, aov=150, problem="broken_tracking"),
        dict(campaign="Google_PMax_GiftCards", platform="Google",
             daily_budget=300, cpm=15, ctr=0.012, cvr=0.025, aov=140),
        dict(campaign="Meta_Lookalike_Diners", platform="Meta",
             daily_budget=350, cpm=30, ctr=0.012, cvr=0.040, aov=120),
        dict(campaign="Meta_Retargeting_Menu", platform="Meta",
             daily_budget=200, cpm=40, ctr=0.018, cvr=0.050, aov=110),
    ],
    "Nordwood Furniture": [
        dict(campaign="Google_Search_Sofas", platform="Google",
             daily_budget=900, cpm=110, ctr=0.050, cvr=0.0075, aov=850),
        dict(campaign="Google_Shopping_Catalog", platform="Google",
             daily_budget=1000, cpm=20, ctr=0.012, cvr=0.006, aov=850),
        dict(campaign="Meta_Advantage_Catalog", platform="Meta",
             daily_budget=800, cpm=25, ctr=0.015, cvr=0.0075, aov=700, problem="creative_fatigue"),
        dict(campaign="Meta_Video_Prospecting", platform="Meta",
             daily_budget=700, cpm=12, ctr=0.008, cvr=0.006, aov=800, problem="zero_conversion_burner"),
    ],
    "PeakForm Fitness": [
        dict(campaign="Google_Search_Memberships", platform="Google",
             daily_budget=250, cpm=100, ctr=0.080, cvr=0.013, aov=330, problem="underfunded_winner"),
        dict(campaign="Google_Display_Remarketing", platform="Google",
             daily_budget=300, cpm=8, ctr=0.005, cvr=0.020, aov=250),
        dict(campaign="Meta_Leads_FreeTrial", platform="Meta",
             daily_budget=600, cpm=28, ctr=0.012, cvr=0.035, aov=200, problem="overpacing"),
        dict(campaign="Meta_Reels_Awareness", platform="Meta",
             daily_budget=450, cpm=10, ctr=0.007, cvr=0.012, aov=250),
    ],
}

# Single source of truth for "what did we plant where" - the tests import this.
PLANTED_PROBLEMS = {
    c["problem"]: (account, c["campaign"])
    for account, campaigns in ACCOUNTS.items()
    for c in campaigns if "problem" in c
}


def _monthly_budget(c, plant):
    if plant and c.get("problem") == "underfunded_winner":
        return c["daily_budget"] * 30          # no headroom: the budget cap is what holds it back
    return round(c["daily_budget"] * 30 * BUDGET_HEADROOM, -2)


def _simulate_day(c, day_index, current_date, rng, plant):
    problem = c.get("problem") if plant else None

    spend = c["daily_budget"] * rng.uniform(0.88, 1.12)
    if problem == "underfunded_winner":
        spend = c["daily_budget"] * rng.uniform(0.97, 1.00)   # pinned at the cap every day
    if problem == "overpacing" and current_date >= END_DATE.replace(day=1):
        spend *= OVERPACE_MULTIPLIER

    ctr = c["ctr"]
    fatigue_start = DAYS - FATIGUE_DAYS
    if problem == "creative_fatigue" and day_index >= fatigue_start:
        ctr *= 1 - FATIGUE_CTR_DROP * (day_index - fatigue_start) / FATIGUE_DAYS

    cvr = c["cvr"]
    if problem == "zero_conversion_burner":
        cvr = BURNER_CVR
    elif problem == "underfunded_winner":
        cvr = WINNER_CVR

    impressions = spend / (c["cpm"] * rng.uniform(0.92, 1.08)) * 1000
    clicks = impressions * ctr * rng.uniform(0.88, 1.12)
    conversions = round(clicks * cvr * rng.uniform(0.8, 1.2))
    if problem == "broken_tracking" and day_index >= DAYS - TRACKING_BROKEN_DAYS:
        conversions = 0                        # the pixel broke: sales still happen, we just can't see them
    revenue = conversions * c["aov"] * rng.uniform(0.9, 1.1)

    return dict(cost=round(spend, 2), impressions=round(impressions), clicks=round(clicks),
                conversions=conversions, revenue=round(revenue, 2))


def generate(seed=7, plant_problems=True):
    """Returns a DataFrame with one row per campaign per day."""
    rng = random.Random(seed)   # fixed seed -> same data every run (reproducible tests)
    start = END_DATE - timedelta(days=DAYS - 1)
    rows = []
    for day_index in range(DAYS):
        current_date = start + timedelta(days=day_index)
        for account, campaigns in ACCOUNTS.items():
            for c in campaigns:
                rows.append({
                    "date": current_date.isoformat(),
                    "account": account,
                    "platform": c["platform"],
                    "campaign": c["campaign"],
                    "monthly_budget": _monthly_budget(c, plant_problems),
                    **_simulate_day(c, day_index, current_date, rng, plant_problems),
                })
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


def main():
    df = generate()
    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False, date_format="%Y-%m-%d")
    print(f"Wrote {len(df)} rows to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
