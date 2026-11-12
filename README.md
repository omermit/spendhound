# Spendhound 🐕

AI watchdog for small ad agencies: scans client ad accounts (Google Ads, Meta) and flags wasted
spend, sorted by how much money is at stake.

Sprint 1 runs on synthetic data with 5 planted problems: a zero-conversion burner, broken tracking,
budget overpacing, creative fatigue and an underfunded high-ROAS campaign.

Sprint 2 adds an AI analyst. **Code computes, AI explains:** Claude (Haiku 5.5) gets only the numbers
the detectors computed and writes a root-cause hypothesis, business impact, next steps and a client
email per issue, plus a weekly summary. `verifier.py` checks every number in the AI text against the
computed values and blocks the text if it finds one that isn't there.

## Run it (Windows)

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

### AI analysis (optional)

The dashboard works without AI. To turn it on, copy `.env.example` to `.env` and paste your
Anthropic API key after `ANTHROPIC_API_KEY=`. `.env` is gitignored, so the key never reaches GitHub.

To run every finding plus the weekly summary and print the cost:

```
python ai_analyst.py
```

A fresh run costs well under one US cent. Answers are cached in `.cache/ai/`, so a rerun on
unchanged data is free. Delete that folder to force fresh answers.

## Test it

```
pytest
```

Each detector must find its planted campaign and raise zero false alarms, on several random seeds
and on a fully healthy dataset. The AI tests use a fake API client and the real one is blocked, so
`pytest` needs no key or network and costs nothing.

## Project layout

| File | What it does |
|---|---|
| `generate_data.py` | Builds `data/ad_data.csv` (3 accounts x 4 campaigns x 60 days) |
| `detectors.py` | One function per problem; all numbers are computed here |
| `ai_analyst.py` | Sends computed facts to Claude, caches answers on disk, tracks cost |
| `verifier.py` | Blocks any AI text that contains a number the detectors didn't compute |
| `app.py` | Streamlit triage dashboard (display only) |
| `tests/` | pytest suite |
| `CLAUDE.md` | Product brief and engineering rules |
