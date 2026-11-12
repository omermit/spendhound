# Spendhound 🐕

AI watchdog for small ad agencies: scans client ad accounts (Google Ads, Meta) and flags wasted
spend, sorted by how much money is at stake.

Sprint 1 runs on synthetic data with 5 planted problems: a zero-conversion burner, broken tracking,
budget overpacing, creative fatigue and an underfunded high-ROAS campaign.

## Run it (Windows)

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Test it

```
pytest
```

Each detector must find its planted campaign and raise zero false alarms, on several random seeds
and on a fully healthy dataset.

## Project layout

| File | What it does |
|---|---|
| `generate_data.py` | Builds `data/ad_data.csv` (3 accounts x 4 campaigns x 60 days) |
| `detectors.py` | One function per problem; all numbers are computed here |
| `app.py` | Streamlit triage dashboard (display only) |
| `tests/` | pytest suite |
| `CLAUDE.md` | Product brief and engineering rules |
