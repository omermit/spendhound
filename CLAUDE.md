# Spendhound

AI watchdog for small ad agencies. It scans client ad accounts (Google Ads, Meta) and flags
wasted spend, so an account manager knows which fire to put out first.

## Sprint 2 (current)

Goal: AI analyst layer. Code computes, AI explains; AI never produces a number the detectors
didn't compute.

Definition of done:
- AI analysis shows for all 5 issues
- the verifier catches a fake hallucination
- all tests pass without network
- the estimated cost per full run is printed in the terminal (`python ai_analyst.py`)

## Sprint 1 (done)

Goal: a Streamlit triage dashboard that finds planted problems in synthetic data, with tests, on GitHub.

Definition of done:
- All 5 planted problems detected, 0 false alarms
- `pytest` passes
- `streamlit run app.py` works

The 5 problems: zero-conversion burner, broken tracking, budget overpacing,
creative fatigue, underfunded high-ROAS campaign.

## Backlog

- Sprint 2: detectors should return first_seen date so we can show days open.

## Architecture

| File | Responsibility |
|---|---|
| `generate_data.py` | Synthetic data. `generate(seed, plant_problems)`; writes `data/ad_data.csv` |
| `detectors.py` | One pure function per problem. ALL numbers are computed here |
| `ai_analyst.py` | Claude calls (Haiku 5.5, low effort, JSON schema). Input = `finding_facts()` only. Disk cache + cost ledger |
| `verifier.py` | Every number in AI text must match a computed fact, or the text is blocked |
| `app.py` | Streamlit UI. Displays findings; does no business math |
| `tests/` | pytest. Planted data → exactly 5 findings; clean data → 0 findings |

Each finding has: `account, campaign, platform, issue_type, evidence, money_at_risk_ils`
(plus `kind`: "risk" or "opportunity").

## Rules

1. **Code computes all numbers. AI never does math.** Any number shown to a user comes from
   a tested Python function. A future AI layer may explain or prioritise findings in words,
   but must only quote numbers it was given, never calculate, estimate or round them itself.
2. Every detector threshold is a named constant at the top of `detectors.py`, with a comment saying why.
3. A new detector needs a test for "finds it" and for "no false alarm on clean data" before merge.
4. Money is ILS (₪). Dates are ISO (`YYYY-MM-DD`). "Today" = the last date in the data.
5. Never commit secrets, `.env`, `.cache/` or `.venv/`. Dependencies are pinned in `requirements.txt`.
6. Small, focused commits with messages that explain why.

## Commands (Windows)

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python generate_data.py
pytest
streamlit run app.py
python ai_analyst.py      # needs ANTHROPIC_API_KEY in .env; prints the cost
```

If the verifier blocks real AI text, tighten the prompt in `ai_analyst.py` (and bump
`PROMPT_VERSION`). Do not loosen the verifier.
