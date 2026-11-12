"""
ui_data.py: every number the dashboard shows that detectors.py doesn't return directly.
Checked on planted data (known 5 findings) and clean data (0 findings).
"""

import pytest

import detectors as d
import theme
import ui_data as u
from generate_data import generate


@pytest.fixture(scope="module")
def planted():
    df = generate(seed=7, plant_problems=True)
    return df, d.run_all(df)


@pytest.fixture(scope="module")
def clean():
    df = generate(seed=7, plant_problems=False)
    return df, d.run_all(df)


# --- identity ---

def test_finding_ids_are_unique_stable_and_url_safe(planted):
    df, findings = planted
    ids = [u.finding_id(f) for f in findings]
    assert len(set(ids)) == len(ids)
    assert ids == [u.finding_id(f) for f in d.run_all(df)]
    assert all(i.replace("-", "").isalnum() for i in ids)
    assert u.find_by_id(findings, ids[2]) is findings[2]
    assert u.find_by_id(findings, "nope") is None


def test_every_issue_type_has_a_severity_and_copy():
    for issue_type in d.ISSUE_INFO:
        assert theme.SEVERITY_FOR[issue_type] in theme.SEVERITY
        assert theme.ISSUE_TITLE[issue_type] and theme.NEXT_STEPS[issue_type]
        assert theme.rule_lines(issue_type)


# --- KPI strip ---

def test_kpis_add_up(planted):
    df, findings = planted
    k = u.kpis(df, findings)
    risk = [f for f in findings if f.kind == "risk"]
    assert k["at_risk"] == sum(f.money_at_risk_ils for f in risk)
    assert sum(k["at_risk_by_severity"].values()) == k["at_risk"]
    assert k["spend_30d"] == pytest.approx(d.campaign_summary(df, days=30)["cost"].sum())
    assert k["pct_spend_at_risk"] == pytest.approx(k["at_risk"] / k["spend_30d"])
    assert k["upside"] == sum(f.money_at_risk_ils for f in findings if f.kind == "opportunity")
    assert k["n_open"] == 5 and k["n_upside"] == 1
    assert k["severity_counts"] == {"critical": 2, "warning": 2, "opportunity": 1}
    assert k["accounts_affected"] == 3 and k["n_accounts"] == 3


def test_kpi_bar_segments_cover_the_whole_bar_critical_first(planted):
    df, findings = planted
    segs = u.kpis(df, findings)["at_risk_segments"]
    assert sum(s["share"] for s in segs) == pytest.approx(1.0)
    order = [theme.SEVERITY_ORDER.index(s["severity"]) for s in segs]
    assert order == sorted(order)


def test_kpis_on_clean_data_are_zero(clean):
    df, findings = clean
    k = u.kpis(df, findings)
    assert findings == []
    assert k["at_risk"] == 0 and k["upside"] == 0 and k["pct_spend_at_risk"] == 0
    assert k["at_risk_segments"] == [] and k["accounts_affected"] == 0
    assert k["spend_30d"] > 0


# --- export ---

def test_export_has_one_row_per_finding_in_triage_order(planted):
    _, findings = planted
    out = u.export_frame(findings)
    assert len(out) == len(findings)
    assert list(out["money_at_stake_ils"]) == [f.money_at_risk_ils for f in findings]
