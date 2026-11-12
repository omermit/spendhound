"""
The verifier is the moat: an AI response that contains a number we didn't compute must be blocked.
"""

import pandas as pd
import pytest

import verifier as v

FACTS = {
    "campaign": "Meta_Video_Prospecting",
    "money_at_risk_ils": 31200,
    "evidence": "CTR fell 35% over 21 days (2.31% -> 1.50%), a steady decline (R² = 0.84).",
    "ctr_start": 0.023148,
    "decline": 0.3456,
    "daily_spend": 1532.41,
    "break_start": pd.Timestamp("2026-10-28"),
}


# ---------- extraction ----------

@pytest.mark.parametrize("text, raw, value", [
    ("lost ₪1,234 so far", "1,234", 1234),
    ("about 12.5% lower", "12.5%", 0.125),
    ("ROAS of 4.2x", "4.2x", 4.2),
    ("roughly 1.2k per day", "1.2k", 1200),
    ("a ₪3M account", "3M", 3_000_000),
    ("down -35%", "35%", 0.35),
    ("in three days", "three", 3),
    ("Q4 results", "4", 4),
])
def test_extract_finds_every_number_form(text, raw, value):
    tokens, _ = v.extract(text)
    assert [t.raw for t in tokens] == [raw]
    assert any(abs(c - value) < 1e-9 for c in tokens[0].candidates)


def test_extract_reads_iso_dates_as_whole_dates():
    tokens, dates = v.extract("Tracking broke on 2026-10-28.")
    assert dates == ["2026-10-28"] and tokens == []


def test_sentence_punctuation_is_not_a_decimal():
    tokens, _ = v.extract("We spent ₪1,234. Then 5, then 6.")
    assert [t.raw for t in tokens] == ["1,234", "5", "6"]


def test_one_is_not_counted_as_a_number_word():
    assert v.extract("this one is the priority")[0] == []


# ---------- verification ----------

def test_numbers_quoted_from_the_facts_pass():
    text = ("CTR fell 35% (2.31% -> 1.50%), so ₪31,200 is at stake. "
            "That is ₪1,532 a day. R² = 0.84. The gap started 2026-10-28.")
    result = v.verify(text, FACTS)
    assert result.ok, result.unknown
    assert result.checked == 7    # 35%, 2.31%, 1.50%, 31,200, 1,532, 0.84 and the date


def test_display_rounding_of_a_computed_value_passes():
    # 0.3456 shown as 34.6%, 1532.41 shown as ₪1,532: we computed these, they're only formatted.
    assert v.verify("34.6% fewer clicks at ₪1,532/day", FACTS).ok


def test_the_model_rounding_on_its_own_is_blocked():
    result = v.verify("about ₪31k at stake", FACTS)
    assert not result.ok and result.unknown == ["31k"]


def test_a_number_from_a_campaign_name_is_allowed():
    facts = {"campaign": "Search_2026_Brand"}
    assert v.verify("Search_2026_Brand needs attention in 2026", facts).ok


def test_unknown_date_is_blocked():
    result = v.verify("It broke on 2026-10-27.", FACTS)
    assert result.unknown == ["2026-10-27"]


def test_spelled_out_numbers_are_checked():
    assert v.verify("over the next three weeks", FACTS).unknown == ["three"]


def test_nested_json_output_is_checked_field_by_field():
    output = {"business_impact": "₪31,200 at stake",
              "next_steps": ["Rotate creative", "Check again in 48 hours"]}
    result = v.verify(output, FACTS)
    assert result.unknown == ["48"]


def test_text_without_numbers_passes():
    result = v.verify("Rotate in fresh creative.", FACTS)
    assert result.ok and result.checked == 0


# ---------- the fake hallucinating response ----------

HALLUCINATED = {
    "root_cause_hypothesis": "The audience has seen these ads about 9 times each, so CTR fell 35%.",
    "business_impact": "If nothing changes you'll lose ₪48,000 next month, a 22% drop in leads.",
    "next_steps": ["Launch 3 new creatives", "Rotate creative weekly"],
    "client_email_draft": "Hi, CTR fell from 2.31% to 1.50%. We expect ₪48,000 in waste by 2026-12-01.",
}


def test_fake_hallucinating_response_is_blocked():
    result = v.verify(HALLUCINATED, FACTS)
    assert not result.ok
    # Every invented figure is named (once each); the real ones (35%, 2.31%, 1.50%) are not.
    assert result.unknown == ["9", "48,000", "22%", "3", "2026-12-01"]
