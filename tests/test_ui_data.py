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


# --- triage table ---

def test_filters_narrow_by_severity_account_platform_search_and_hidden(planted):
    _, findings = planted
    assert u.filter_findings(findings) == findings
    crit = u.filter_findings(findings, severity="critical")
    assert len(crit) == 2 and all(u.severity_of(f) == "critical" for f in crit)
    one = findings[0]
    assert one in u.filter_findings(findings, account=one.account, platform=one.platform)
    assert u.filter_findings(findings, query=one.campaign.upper()) == [one]
    assert u.filter_findings(findings, query="no such campaign") == []
    assert one not in u.filter_findings(findings, hidden={u.finding_id(one)})


def test_signal_line_quotes_detector_numbers(planted):
    _, findings = planted
    for f in findings:
        line = u.signal_line(f)
        assert line and "\n" not in line
    [over] = [f for f in findings if f.issue_type == "overpacing"]
    m = over.metrics
    assert f"{m['projected'] / m['budget'] - 1:+.0%}" in u.signal_line(over)


def test_spark_series_is_14_days_and_cumulative_for_overpacing(planted):
    df, findings = planted
    for f in findings:
        assert len(u.spark_series(df, f)) == u.SPARK_DAYS
    [over] = [f for f in findings if f.issue_type == "overpacing"]
    s = u.spark_series(df, over)
    assert s == sorted(s)           # cumulative spend never goes down


def test_review_ids_round_trip():
    assert u.parse_ids("") == [] and u.parse_ids(None) == []
    assert u.parse_ids("a,b") == ["a", "b"]
    assert u.toggle_id(["a"], "b") == ["a", "b"]
    assert u.toggle_id(["a", "b"], "a") == ["b"]


# --- detail panel ---

def test_money_breakdown_ends_with_the_detector_total(planted):
    _, findings = planted
    for f in findings:
        rows = u.money_breakdown(f)
        assert rows[-1][1:] == (f.money_at_risk_ils, "ils")
        assert all(fmt in {"ils", "pct0", "pct2"} for _, _, fmt in rows)


def test_tracking_breakdown_parts_sum_to_total(planted):
    _, findings = planted
    [f] = [f for f in findings if f.issue_type == "broken_tracking"]
    gap, projection, total = (v for _, v, _ in u.money_breakdown(f))
    assert gap == f.metrics["blind_spend"]
    assert gap + projection == pytest.approx(total)


def test_key_numbers_flag_exactly_one_anomaly(planted):
    _, findings = planted
    for f in findings:
        rows = u.key_numbers(f)
        assert sum(1 for *_, hl in rows if hl) == 1


def test_client_summary_quotes_the_detector(planted):
    _, findings = planted
    for f in findings:
        text = u.client_summary(f)
        assert f.evidence in text and f"₪{f.money_at_risk_ils:,.0f}" in text


# --- accounts table ---

def test_account_rows_add_up_to_the_kpis(planted):
    df, findings = planted
    rows = u.account_rows(df, findings)
    k = u.kpis(df, findings)
    assert len(rows) == k["n_accounts"]
    assert sum(r["spend"] for r in rows) == pytest.approx(k["spend_30d"])
    assert sum(r["at_risk"] for r in rows) == pytest.approx(k["at_risk"])
    assert sum(sum(r["counts"].values()) for r in rows) == len(findings)
    assert [r["at_risk"] for r in rows] == sorted((r["at_risk"] for r in rows), reverse=True)
    for r in rows:
        assert r["share"] == pytest.approx(r["at_risk"] / r["spend"])
        assert 0 <= r["bar_fill"] <= 1


def test_account_rows_on_clean_data_have_no_risk(clean):
    df, findings = clean
    for r in u.account_rows(df, findings):
        assert r["at_risk"] == 0 and r["bar_severity"] is None
        assert sum(r["counts"].values()) == 0


# --- AI weekly summary totals ---

def test_portfolio_totals_match_the_kpis(planted):
    df, findings = planted
    t, k = u.portfolio_totals(findings), u.kpis(df, findings)
    assert t["at_risk"] == k["at_risk"] and t["upside"] == k["upside"]
    assert t["n_open"] == k["n_open"] == 5
    assert t["n_accounts"] == k["accounts_affected"]
    assert sum(a["n_findings"] for a in t["accounts"]) == 5
    assert sum(a["at_risk"] for a in t["accounts"]) == t["at_risk"]
    assert [a["at_risk"] for a in t["accounts"]] == sorted((a["at_risk"] for a in t["accounts"]), reverse=True)


def test_portfolio_totals_on_clean_data_are_empty(clean):
    _, findings = clean
    assert u.portfolio_totals(findings) == {"at_risk": 0.0, "upside": 0.0, "n_open": 0,
                                            "n_accounts": 0, "accounts": []}


# --- copy button: AI text must stay data inside the script ---

def test_copy_button_cannot_be_broken_out_of_by_ai_text():
    import components as c
    evil = 'Hi</script><script>alert("x")</script> & <b>'
    html = c.copy_button_html(evil)
    script = html.split("<script>", 1)[1]
    assert script.count("</script>") == 1          # only our own closing tag
    assert "<b>" not in html and "alert(\"x\")</script>" not in html
