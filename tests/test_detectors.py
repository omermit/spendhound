"""
Definition of done for Sprint 1, as code:
  - every detector finds its planted problem (right account, right campaign)
  - zero false alarms, on planted data AND on data where every campaign is healthy
Each test runs on several random seeds, so a pass can't be a lucky coincidence of one dataset.
"""

import pytest

import detectors as d
from generate_data import PLANTED_PROBLEMS, generate

SEEDS = [7, 42, 2026]

DETECTOR_FOR = {
    "zero_conversion_burner": d.detect_zero_conversion_burners,
    "broken_tracking": d.detect_broken_tracking,
    "overpacing": d.detect_overpacing,
    "creative_fatigue": d.detect_creative_fatigue,
    "underfunded_winner": d.detect_underfunded_winners,
}


@pytest.fixture(scope="module", params=SEEDS)
def planted(request):
    return generate(seed=request.param, plant_problems=True)


@pytest.fixture(scope="module", params=SEEDS)
def clean(request):
    return generate(seed=request.param, plant_problems=False)


def test_every_planted_problem_has_a_detector():
    assert set(PLANTED_PROBLEMS) == set(DETECTOR_FOR) == set(d.ISSUE_INFO)


@pytest.mark.parametrize("issue_type", DETECTOR_FOR)
def test_detector_finds_exactly_its_planted_campaign(planted, issue_type):
    findings = DETECTOR_FOR[issue_type](planted)
    found = [(f.account, f.campaign) for f in findings]
    assert found == [PLANTED_PROBLEMS[issue_type]], f"{issue_type}: expected only the planted campaign"


@pytest.mark.parametrize("issue_type", DETECTOR_FOR)
def test_detector_is_silent_on_healthy_data(clean, issue_type):
    assert DETECTOR_FOR[issue_type](clean) == []


def test_run_all_finds_five_problems_and_nothing_else(planted):
    found = {(f.issue_type, f.account, f.campaign) for f in d.run_all(planted)}
    expected = {(issue, *where) for issue, where in PLANTED_PROBLEMS.items()}
    assert found == expected


def test_findings_are_complete_and_sorted_by_money(planted):
    findings = d.run_all(planted)
    for f in findings:
        assert f.account and f.campaign and f.platform in {"Google", "Meta"}
        assert f.evidence.strip()
        assert f.money_at_risk_ils > 0
        assert f.kind in {"risk", "opportunity"}
    amounts = [f.money_at_risk_ils for f in findings]
    assert amounts == sorted(amounts, reverse=True)


# --- A few hand-checkable cases: thresholds behave as documented ---

def test_burner_respects_minimum_spend():
    df = generate(seed=7)
    burner = df["campaign"] == PLANTED_PROBLEMS["zero_conversion_burner"][1]
    df.loc[burner, "cost"] = 100          # 14 days x ₪100 = ₪1,400 < ₪2,000 threshold
    assert d.detect_zero_conversion_burners(df) == []


def test_overpacing_money_equals_projected_minus_budget():
    df = generate(seed=7)
    [f] = d.detect_overpacing(df)
    m = f.metrics
    assert f.money_at_risk_ils == round(m["projected"] - m["budget"])
    assert m["projected"] > m["budget"] * d.OVERPACE_TOLERANCE


def test_tracking_needs_normal_clicks():
    """If clicks collapse too, it's a traffic problem, not a tracking problem."""
    df = generate(seed=7)
    account, campaign = PLANTED_PROBLEMS["broken_tracking"]
    rows = df[(df["campaign"] == campaign)].sort_values("date").tail(6).index
    df.loc[rows, "clicks"] = 1
    assert d.detect_broken_tracking(df) == []
