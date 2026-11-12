"""
Spendhound AI analyst: code computes, AI explains.

The model only ever sees `facts`: values the detectors and ui_data already computed, pre-formatted
the way the dashboard shows them. Its answer is then checked by verifier.py; any number that isn't
in the facts blocks the answer. Responses are cached on disk, so the same finding is paid for once.

Run a full analysis (all findings + weekly summary) and print the cost:
    python ai_analyst.py
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import anthropic
from dotenv import load_dotenv

import components as c
import theme
import ui_data as u
import verifier

ROOT = Path(__file__).parent

# ---------------------------------------------------------------------------
# Model settings. Each one is a cost/quality decision, so each one says why.
# ---------------------------------------------------------------------------

MODEL = "claude-haiku-5-5"      # small and fast: explaining given facts needs no deep reasoning
EFFORT = "low"                  # least thinking; temperature isn't settable on this model,
                                # so stability comes from low effort + JSON schema + the cache
MAX_TOKENS = 4_000              # ~4x a typical answer: room for thinking, never truncated
TIMEOUT_SECONDS = 60
PROMPT_VERSION = 2              # bump when a prompt or schema changes: old cache entries stop matching

# Haiku 5.5 list prices, USD per million tokens (prompts up to 100K tokens; ours are ~1-3K).
PRICE_INPUT_PER_MTOK = 0.10
PRICE_OUTPUT_PER_MTOK = 0.50    # thinking tokens are billed as output and are included here
CACHE_WRITE_MULTIPLIER = 1.25   # prompt-cache pricing, in case the API reports cached tokens
CACHE_READ_MULTIPLIER = 0.10

CACHE_DIR = ROOT / ".cache" / "ai"


class AIUnavailable(Exception):
    """No usable API key: the dashboard works without AI and says so."""


class AIError(Exception):
    """The API call failed or the answer was unusable (refused, cut off, not JSON)."""


# ---------------------------------------------------------------------------
# Prompts and output schemas
# ---------------------------------------------------------------------------

NUMBER_RULES = """\
Number rules. An automatic checker reads your answer and blocks all of it if one rule is broken:
- Every number, percentage, money amount and date you write must appear in the facts. Copy it \
exactly as written there, for example "₪31,200", "35%", "2026-10-28".
- Never calculate, add up, estimate, round, convert or extrapolate. Not even simple sums.
- Never introduce a new figure: no new time frames ("48 hours", "next quarter"), counts \
("3 new ads"), targets or benchmarks.
- Never write numbers as words ("two", "three", "dozen"). Never number your list items.
- If a point needs a figure that is not in the facts, make it without one ("soon", "a few new \
ads", "within the day")."""

EXPLAIN_SYSTEM = f"""\
You are a senior paid-media analyst at a small ad agency. Spendhound's detectors flagged one \
problem or opportunity in a client's ad account. You receive the computed facts as JSON. \
Explain them for the account manager who has to act today.

{NUMBER_RULES}

Fields:
- root_cause_hypothesis: one to three sentences on the most likely causes consistent with the \
evidence. It is a hypothesis: say "likely" or "may", never claim certainty.
- business_impact: one or two sentences on what this costs or could gain the client. Quote the \
money at stake from the facts.
- next_steps: three or four short imperative steps for the account manager, most urgent first.
- client_email_draft: a short plain-text email to the client. Start with "Hi [Client name]," and \
end with "Best,\\n[Your name]". Calm and jargon-free: what we found, why it matters, what we \
will do about it. No subject line.

Nothing has been done yet: this is a draft written the moment the issue was found, and the \
account manager decides what happens. Write every action as a plan or a recommendation ("we \
will check", "we recommend pausing", "we suggest"). Never say or imply that an action has \
already happened or is happening now: no "we have paused", "we've fixed", "we are pausing it \
now", "we have stopped"."""

EXPLAIN_SCHEMA = {
    "type": "object",
    "properties": {
        "root_cause_hypothesis": {"type": "string"},
        "business_impact": {"type": "string"},
        "next_steps": {"type": "array", "items": {"type": "string"}},
        "client_email_draft": {"type": "string"},
    },
    "required": ["root_cause_hypothesis", "business_impact", "next_steps", "client_email_draft"],
    "additionalProperties": False,
}

WEEKLY_SYSTEM = f"""\
You are a senior paid-media analyst writing the weekly executive summary for the owner of a \
small ad agency. You receive the portfolio totals and every open finding as JSON, all computed \
by Spendhound's detectors.

{NUMBER_RULES}
- The totals are already added up for you. Quote them; never add findings together yourself.

Fields:
- headline: one sentence, the single most important thing this week.
- overview: two to four sentences on the state of the portfolio, quoting the totals.
- connections: how findings relate to each other, for example several issues on the same \
account, or one account where budget could move from a losing campaign to a winning one. One \
string per connection. Empty if nothing is related.
- priorities: what to do first, most urgent first, naming account and campaign. Three to five items."""

WEEKLY_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "overview": {"type": "string"},
        "connections": {"type": "array", "items": {"type": "string"}},
        "priorities": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["headline", "overview", "connections", "priorities"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Facts: the only input the model gets, and the only numbers it may quote
# ---------------------------------------------------------------------------

def finding_facts(f):
    """One finding as the dashboard shows it: computed values, formatted, nothing new."""
    facts = {
        "account": f.account,
        "campaign": f.campaign,
        "platform": "Google Ads" if f.platform == "Google" else "Meta Ads",
        "issue": theme.ISSUE_TITLE[f.issue_type],
        "kind": f.kind,
        "evidence": f.evidence,
        "money_at_stake": f"{c.ils(f.money_at_risk_ils)} ({theme.HORIZON_LONG[f.issue_type]})",
        "money_breakdown": {label: c.fmt(v, kind) for label, v, kind in u.money_breakdown(f)},
        "key_numbers": {label: c.fmt(v, kind) for label, v, kind, _ in u.key_numbers(f)},
        "why_flagged": theme.rule_lines(f.issue_type),
        "standard_next_steps": [text for text, _ in theme.NEXT_STEPS[f.issue_type]],
    }
    if "break_start" in f.metrics:
        facts["tracking_gap_started"] = c.date_iso(f.metrics["break_start"])
    return facts


def weekly_facts(findings):
    t = u.portfolio_totals(findings)
    return {
        "totals": {
            "money_at_risk": c.ils(t["at_risk"]),
            "upside_per_month": c.ils(t["upside"]),
            "open_findings": t["n_open"],
            "accounts_with_findings": t["n_accounts"],
        },
        "by_account": [{
            "account": a["account"],
            "findings": a["n_findings"],
            "money_at_risk": c.ils(a["at_risk"]),
            "upside_per_month": c.ils(a["upside"]),
        } for a in t["accounts"]],
        "findings": [{
            "severity": theme.SEVERITY[u.severity_of(f)]["label"],
            "issue": theme.ISSUE_TITLE[f.issue_type],
            "account": f.account,
            "campaign": f.campaign,
            "money_at_stake": f"{c.ils(f.money_at_risk_ils)} ({theme.HORIZON_LONG[f.issue_type]})",
            "evidence": f.evidence,
        } for f in findings],
    }


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------

def cost_usd(usage):
    """USD cost of one call from its token usage (a dict of the API's usage fields)."""
    input_equiv = (usage.get("input_tokens", 0)
                   + usage.get("cache_creation_input_tokens", 0) * CACHE_WRITE_MULTIPLIER
                   + usage.get("cache_read_input_tokens", 0) * CACHE_READ_MULTIPLIER)
    return (input_equiv * PRICE_INPUT_PER_MTOK + usage.get("output_tokens", 0) * PRICE_OUTPUT_PER_MTOK) / 1e6


@dataclass
class CostLedger:
    """Every AI call in this process. Cached calls cost nothing now but remember what they cost."""
    calls: list = field(default_factory=list)       # (name, usage dict, cached bool)

    def add(self, name, usage, cached):
        self.calls.append((name, usage, cached))

    @property
    def paid_usd(self):
        return sum(cost_usd(us) for _, us, cached in self.calls if not cached)

    @property
    def fresh_run_usd(self):
        return sum(cost_usd(us) for _, us, _ in self.calls)

    def report(self):
        n_paid = sum(1 for *_, cached in self.calls if not cached)
        tokens_in = sum(us.get("input_tokens", 0) for _, us, _ in self.calls)
        tokens_out = sum(us.get("output_tokens", 0) for _, us, _ in self.calls)
        return (f"AI cost this run: ${self.paid_usd:.4f} ({n_paid} API call{'s' if n_paid != 1 else ''}, "
                f"{len(self.calls) - n_paid} from cache) | same run uncached: ${self.fresh_run_usd:.4f} "
                f"({tokens_in:,} input + {tokens_out:,} output tokens, {MODEL})")


LEDGER = CostLedger()


# ---------------------------------------------------------------------------
# API call with disk cache
# ---------------------------------------------------------------------------

def get_client():
    load_dotenv(ROOT / ".env")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise AIUnavailable("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key.")
    return anthropic.Anthropic(timeout=TIMEOUT_SECONDS)


def cache_key(system, schema, facts):
    payload = json.dumps({"model": MODEL, "effort": EFFORT, "prompt_version": PROMPT_VERSION,
                          "system": system, "schema": schema, "facts": facts},
                         sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _call(name, system, schema, facts, client=None, cache_dir=None):
    """Structured call: cached answer if we have one, else ask the model. Returns the parsed JSON."""
    cache_dir = Path(cache_dir or CACHE_DIR)
    path = cache_dir / f"{cache_key(system, schema, facts)}.json"
    if path.exists():
        hit = json.loads(path.read_text(encoding="utf-8"))
        LEDGER.add(name, hit["usage"], cached=True)
        return hit["content"]

    client = client or get_client()
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": json.dumps(facts, ensure_ascii=False, indent=1)}],
            output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": schema}},
        )
    except anthropic.AuthenticationError as e:
        raise AIUnavailable("The API key was rejected. Check ANTHROPIC_API_KEY in .env.") from e
    except anthropic.RateLimitError as e:
        raise AIError("Rate limited by the API. Try again in a minute.") from e
    except anthropic.APIStatusError as e:
        raise AIError(f"API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise AIError("Could not reach the API. Check the network connection.") from e

    usage = {k: getattr(response.usage, k, 0) or 0 for k in
             ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}
    LEDGER.add(name, usage, cached=False)    # paid for even if unusable below
    print(f"[ai] {name}: ${cost_usd(usage):.4f} ({usage['input_tokens']:,} in + "
          f"{usage['output_tokens']:,} out tokens) | paid so far ${LEDGER.paid_usd:.4f}", flush=True)

    if response.stop_reason == "refusal":
        raise AIError("The model declined to answer.")
    if response.stop_reason == "max_tokens":
        raise AIError("The answer was cut off (max_tokens).")
    text = next((b.text for b in response.content if b.type == "text"), None)
    try:
        content = json.loads(text)
    except (TypeError, json.JSONDecodeError) as e:
        raise AIError("The answer was not valid JSON.") from e

    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": MODEL, "content": content, "usage": usage},
                               ensure_ascii=False, indent=1), encoding="utf-8")
    return content


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def explain_issue(finding, client=None, cache_dir=None):
    """{root_cause_hypothesis, business_impact, next_steps, client_email_draft} for one finding.
    Unverified: use analyse_issue() to get it together with the verifier's verdict."""
    return _call(f"explain {u.finding_id(finding)}", EXPLAIN_SYSTEM, EXPLAIN_SCHEMA,
                 finding_facts(finding), client, cache_dir)


def weekly_summary(findings, client=None, cache_dir=None):
    """{headline, overview, connections, priorities} across all accounts. Unverified."""
    return _call("weekly summary", WEEKLY_SYSTEM, WEEKLY_SCHEMA, weekly_facts(findings), client, cache_dir)


@dataclass
class Analysis:
    content: dict
    verification: verifier.Verification

    @property
    def verified(self):
        return self.verification.ok


def analyse_issue(finding, client=None, cache_dir=None):
    content = explain_issue(finding, client, cache_dir)
    return Analysis(content, verifier.verify(content, finding_facts(finding)))


def analyse_week(findings, client=None, cache_dir=None):
    content = weekly_summary(findings, client, cache_dir)
    return Analysis(content, verifier.verify(content, weekly_facts(findings)))


def run_full_analysis(findings, client=None, cache_dir=None):
    """Every finding plus the weekly summary; prints one line each and the cost report."""
    client = client or get_client()
    for f in findings:
        a = analyse_issue(f, client, cache_dir)
        status = "Verified" if a.verified else f"BLOCKED, unverified numbers: {', '.join(a.verification.unknown)}"
        print(f"  {theme.ISSUE_TITLE[f.issue_type]:<24} {f.campaign:<28} {status}")
    week = analyse_week(findings, client, cache_dir)
    print(f"  {'Weekly summary':<53} "
          f"{'Verified' if week.verified else 'BLOCKED: ' + ', '.join(week.verification.unknown)}")
    print(LEDGER.report())


if __name__ == "__main__":
    import sys

    import detectors as d

    sys.stdout.reconfigure(encoding="utf-8")     # Windows consoles default to cp1252: no ₪
    from generate_data import OUTPUT_FILE, generate

    if not Path(OUTPUT_FILE).exists():
        Path(OUTPUT_FILE).parent.mkdir(exist_ok=True)
        generate().to_csv(OUTPUT_FILE, index=False, date_format="%Y-%m-%d")
    try:
        run_full_analysis(d.run_all(d.load_data(OUTPUT_FILE)))
    except AIUnavailable as e:
        sys.exit(f"AI unavailable: {e}")
