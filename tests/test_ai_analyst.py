"""
ai_analyst.py with a fake API client (see conftest.py: the real one is blocked).

FakeClient answers like a well-behaved model: it only quotes values from the facts it was sent.
HallucinatingClient invents figures; the verifier must block every one of its answers.
"""

import json
from types import SimpleNamespace

import pytest

import ai_analyst as a
import detectors as d
from generate_data import generate

USAGE = {"input_tokens": 1_000, "output_tokens": 800}


def _response(content, stop_reason="end_turn", usage=USAGE):
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""),
                 SimpleNamespace(type="text", text=json.dumps(content, ensure_ascii=False))],
        stop_reason=stop_reason,
        usage=SimpleNamespace(**usage),
    )


class FakeClient:
    """Records every request and answers with text built only from the facts."""

    def __init__(self):
        self.requests = []
        self.messages = SimpleNamespace(create=self.create)

    def answer(self, facts):
        if "totals" in facts:
            t = facts["totals"]
            top = facts["findings"][0]
            return {"headline": f"{t['money_at_risk']} is at risk across the portfolio.",
                    "overview": f"{t['open_findings']} findings, {t['upside_per_month']} of upside.",
                    "connections": [f"{top['account']} needs attention first."],
                    "priorities": [f"{f['issue']} on {f['campaign']}" for f in facts["findings"]]}
        return {"root_cause_hypothesis": f"Likely cause, given: {facts['evidence']}",
                "business_impact": f"{facts['money_at_stake']} for {facts['account']}.",
                "next_steps": facts["standard_next_steps"],
                "client_email_draft": f"Hi [Client name],\n{facts['evidence']}\nBest,\n[Your name]"}

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return _response(self.answer(json.loads(kwargs["messages"][0]["content"])))


class HallucinatingClient(FakeClient):
    def answer(self, facts):
        good = super().answer(facts)
        key = "overview" if "totals" in facts else "business_impact"
        good[key] += " Expect roughly ₪48,000 more in waste over the next 6 weeks."
        return good


@pytest.fixture(scope="module")
def findings():
    return d.run_all(generate(seed=7, plant_problems=True))


# ---------- the request ----------

def test_request_uses_small_model_low_effort_and_json_schema(findings):
    client = FakeClient()
    a.explain_issue(findings[0], client)
    req = client.requests[0]
    assert req["model"] == "claude-haiku-5-5"
    assert req["output_config"]["effort"] == "low"
    assert req["output_config"]["format"] == {"type": "json_schema", "schema": a.EXPLAIN_SCHEMA}
    assert "temperature" not in req       # rejected by this model; see EFFORT in ai_analyst.py


def test_model_input_is_only_the_structured_facts(findings):
    client = FakeClient()
    a.explain_issue(findings[0], client)
    sent = json.loads(client.requests[0]["messages"][0]["content"])
    assert sent == json.loads(json.dumps(a.finding_facts(findings[0]), ensure_ascii=False))
    assert len(client.requests[0]["messages"]) == 1


def test_explain_issue_returns_the_four_fields(findings):
    out = a.explain_issue(findings[0], FakeClient())
    assert set(out) == {"root_cause_hypothesis", "business_impact", "next_steps", "client_email_draft"}
    assert isinstance(out["next_steps"], list)


# ---------- definition of done: all 5 explained and verified; hallucination blocked ----------

def test_all_five_findings_get_a_verified_analysis(findings):
    assert len(findings) == 5
    client = FakeClient()
    results = [a.analyse_issue(f, client) for f in findings]
    assert all(r.verified for r in results), [r.verification.unknown for r in results]
    assert {f.issue_type for f in findings} == set(d.ISSUE_INFO)


def test_weekly_summary_is_verified(findings):
    result = a.analyse_week(findings, FakeClient())
    assert result.verified, result.verification.unknown
    assert set(result.content) == {"headline", "overview", "connections", "priorities"}


def test_hallucinated_numbers_are_blocked_for_every_finding(findings):
    client = HallucinatingClient()
    for f in findings:
        result = a.analyse_issue(f, client)
        assert not result.verified
        # (The invented "6 weeks" is only caught where no fact contains a 6: broken tracking
        # really did have 6 zero days. The checker matches values, not their meaning.)
        assert "48,000" in result.verification.unknown


def test_hallucinated_weekly_summary_is_blocked(findings):
    result = a.analyse_week(findings, HallucinatingClient())
    assert not result.verified and "48,000" in result.verification.unknown


def test_weekly_facts_give_the_model_totals_so_it_never_adds(findings):
    facts = a.weekly_facts(findings)
    assert facts["totals"]["open_findings"] == 5
    assert len(facts["findings"]) == 5


# ---------- disk cache ----------

def test_same_finding_is_paid_for_once(findings, tmp_path):
    client = FakeClient()
    first = a.explain_issue(findings[0], client, cache_dir=tmp_path)
    second = a.explain_issue(findings[0], client, cache_dir=tmp_path)
    assert first == second and len(client.requests) == 1
    assert [cached for *_, cached in a.LEDGER.calls] == [False, True]


def test_cache_key_changes_with_facts_and_prompt_version(findings, monkeypatch):
    facts = a.finding_facts(findings[0])
    key = a.cache_key(a.EXPLAIN_SYSTEM, a.EXPLAIN_SCHEMA, facts)
    assert key == a.cache_key(a.EXPLAIN_SYSTEM, a.EXPLAIN_SCHEMA, dict(facts))
    assert key != a.cache_key(a.EXPLAIN_SYSTEM, a.EXPLAIN_SCHEMA, a.finding_facts(findings[1]))
    monkeypatch.setattr(a, "PROMPT_VERSION", a.PROMPT_VERSION + 1)
    assert key != a.cache_key(a.EXPLAIN_SYSTEM, a.EXPLAIN_SCHEMA, facts)


def test_unusable_answers_are_not_cached(findings, tmp_path):
    class CutOff(FakeClient):
        def create(self, **kwargs):
            self.requests.append(kwargs)
            return _response({}, stop_reason="max_tokens")

    client = CutOff()
    for _ in range(2):
        with pytest.raises(a.AIError):
            a.explain_issue(findings[0], client, cache_dir=tmp_path)
    assert len(client.requests) == 2 and not list(tmp_path.iterdir())


# ---------- cost ----------

def test_cost_uses_haiku_prices():
    # 1,000 in x $0.10/M + 800 out x $0.50/M = $0.0001 + $0.0004
    assert a.cost_usd(USAGE) == pytest.approx(0.0005)


def test_full_run_prints_cost_and_cached_rerun_is_free(findings, tmp_path, capsys):
    client = FakeClient()
    a.run_full_analysis(findings, client, cache_dir=tmp_path)
    first = capsys.readouterr().out
    assert first.count("Verified") == 6
    assert "AI cost this run: $0.0030 (6 API calls, 0 from cache)" in first

    a.LEDGER.calls.clear()
    a.run_full_analysis(findings, client, cache_dir=tmp_path)
    second = capsys.readouterr().out
    assert "AI cost this run: $0.0000 (0 API calls, 6 from cache) | same run uncached: $0.0030" in second
    assert len(client.requests) == 6


# ---------- no key, no network ----------

def test_without_a_key_the_ai_is_unavailable_not_crashing(findings):
    with pytest.raises(a.AIUnavailable):
        a.explain_issue(findings[0])
