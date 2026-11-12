"""
Spendhound triage dashboard.

Display only: every number comes from detectors.py (rule #1 in CLAUDE.md).
Run:  streamlit run app.py
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import detectors as d
from generate_data import OUTPUT_FILE, generate

RED, GREEN, INDIGO, SLATE, AMBER = "#E5484D", "#12A594", "#4F46E5", "#94A3B8", "#F59E0B"

st.set_page_config(page_title="Spendhound", page_icon="🐕", layout="wide")

st.markdown("""
<style>
.block-container { padding-top: 2rem; max-width: 1280px; }
h1 { font-weight: 800 !important; letter-spacing: -0.03em; margin-bottom: 0 !important; }
[data-testid="stMetric"] { background: var(--secondary-background-color); border-radius: 14px; padding: 16px 20px; }
[data-testid="stMetricValue"] { font-weight: 700; font-size: 1.7rem; }
[data-testid="stMetricValue"] > div { overflow: visible; }
.pill { display:inline-block; padding:3px 10px; border-radius:999px; font-size:.78rem; font-weight:600; }
.pill.risk { background:rgba(229,72,77,.12); color:#C62A2F; }
.pill.opportunity { background:rgba(18,165,148,.12); color:#0D8574; }
.rank { color:#94A3B8; font-weight:700; margin-right:6px; }
.camp { font-size:1.15rem; font-weight:700; margin:10px 0 0 0; }
.meta { color:#64748B; font-size:.86rem; }
.money { font-size:1.9rem; font-weight:800; margin:12px 0 0 0; letter-spacing:-0.02em; }
.money.risk { color:#C62A2F; } .money.opportunity { color:#0D8574; }
.note { color:#64748B; font-size:.8rem; margin-bottom:10px; }
.evidence { font-size:.92rem; line-height:1.5; }
.action { font-size:.88rem; margin-top:10px; padding:8px 12px; border-radius:8px;
          background:var(--secondary-background-color); }
</style>
""", unsafe_allow_html=True)


# ---------- data ----------

@st.cache_data
def load(path: str):
    if not Path(path).exists():          # fresh clone without data: create it
        df = generate()
        Path(path).parent.mkdir(exist_ok=True)
        df.to_csv(path, index=False, date_format="%Y-%m-%d")
    df = d.load_data(path)
    return df, d.run_all(df)


df, all_findings = load(str(OUTPUT_FILE))
accounts = sorted(df["account"].unique())
today = df["date"].max()

with st.sidebar:
    st.markdown("### 🐕 Spendhound")
    st.caption("AI watchdog for ad agencies")
    choice = st.selectbox("Client account", ["All accounts"] + accounts)
    st.divider()
    st.caption(f"Data: synthetic sample · {df['date'].min():%d %b} – {today:%d %b %Y}")
    st.caption(f"{df['account'].nunique()} accounts · {df['campaign'].nunique()} campaigns · Google + Meta")
    with st.expander("How issues are detected"):
        st.markdown(
            f"- **Burner**: ≥ ₪{d.BURNER_MIN_SPEND:,} spend and ≤ {d.BURNER_MAX_CONVERSIONS} conversion "
            f"in {d.BURNER_WINDOW_DAYS} days\n"
            f"- **Tracking**: ≥ {d.TRACKING_MIN_ZERO_DAYS} days of 0 conversions while clicks stay normal\n"
            f"- **Overpacing**: projected month spend > {d.OVERPACE_TOLERANCE:.0%} of budget\n"
            f"- **Fatigue**: CTR trend down ≥ {d.FATIGUE_MIN_DECLINE:.0%} over {d.FATIGUE_WINDOW_DAYS} days\n"
            f"- **Winner**: ROAS ≥ {d.WINNER_MIN_ROAS:g} and ≥ {d.WINNER_MIN_ROAS_MULTIPLE:g}× the account, "
            f"capped by budget"
        )

if choice == "All accounts":
    view_df, findings = df, all_findings
else:
    view_df = df[df["account"] == choice]
    findings = [f for f in all_findings if f.account == choice]


# ---------- header + KPIs ----------

st.title("Spend triage")
st.caption(f"As of {today:%A, %d %B %Y} · {choice}")
st.write("")

summary = d.campaign_summary(view_df, days=30)
at_risk = sum(f.money_at_risk_ils for f in findings if f.kind == "risk")
upside = sum(f.money_at_risk_ils for f in findings if f.kind == "opportunity")
affected = len({f.account for f in findings})
n_accounts = view_df["account"].nunique()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Spend · 30 days", f"₪{summary['cost'].sum():,.0f}", border=True)
k2.metric("Money at risk", f"₪{at_risk:,.0f}", border=True,
          help="Sum of all risk findings. Each card states its own time horizon.")
k3.metric("Upside found", f"₪{upside:,.0f}", border=True,
          help="Estimated monthly net gain from scaling underfunded winners.")
k4.metric("Issues found", f"{len(findings)}", border=True,
          help="Number of findings in the selected accounts.")
st.caption(f"Issues affect {affected} of {n_accounts} account{'s' if n_accounts != 1 else ''}.")
st.write("")


# ---------- evidence charts (one builder per issue type) ----------

def base_layout(fig, height=280):
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=30, b=10), template="plotly_white",
        font=dict(family="Inter, sans-serif", size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        hovermode="x unified", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(showgrid=False)
    return fig


def last_n(rows, days=30):
    return rows[rows["date"] > today - pd.Timedelta(days=days)]


def chart_burner(f):
    rows = last_n(d.daily_series(df, f.account, f.campaign))
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_bar(x=rows["date"], y=rows["cost"], name="Spend (₪)", marker_color=SLATE)
    fig.add_scatter(x=rows["date"], y=rows["conversions"], name="Conversions",
                    line=dict(color=RED, width=3), secondary_y=True)
    fig.update_yaxes(title_text="₪", secondary_y=False)
    fig.update_yaxes(title_text="Conversions", range=[0, 5], dtick=1, tickmode="linear",
                     secondary_y=True, showgrid=False)
    return base_layout(fig)


def chart_tracking(f):
    rows = last_n(d.daily_series(df, f.account, f.campaign))
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_scatter(x=rows["date"], y=rows["clicks"], name="Clicks", line=dict(color=SLATE, width=2))
    fig.add_scatter(x=rows["date"], y=rows["conversions"], name="Conversions",
                    line=dict(color=RED, width=3), secondary_y=True)
    fig.add_vrect(x0=f.metrics["break_start"] - pd.Timedelta(hours=12), x1=today + pd.Timedelta(hours=12),
                  fillcolor=RED, opacity=0.08, line_width=0,
                  annotation_text="conversions stop →", annotation_position="top left",
                  annotation_xanchor="right", annotation_font_color=RED)
    fig.update_yaxes(title_text="Clicks", rangemode="tozero", secondary_y=False)
    fig.update_yaxes(title_text="Conversions", rangemode="tozero", dtick=5, tickmode="linear",
                     secondary_y=True, showgrid=False)
    return base_layout(fig)


def chart_overpacing(f):
    actual, projected = d.pacing_series(df, f.account, f.campaign)
    fig = go.Figure()
    fig.add_scatter(x=actual["date"], y=actual["cumulative"], name="Spent so far",
                    line=dict(color=INDIGO, width=3))
    fig.add_scatter(x=projected["date"], y=projected["cumulative"], name="Projected",
                    line=dict(color=RED, width=3, dash="dash"))
    fig.add_hline(y=f.metrics["budget"], line=dict(color=GREEN, width=2, dash="dot"),
                  annotation_text=f"Monthly budget ₪{f.metrics['budget']:,.0f}",
                  annotation_position="top left")
    fig.update_yaxes(title_text="Cumulative spend (₪)", rangemode="tozero")
    return base_layout(fig)


def chart_fatigue(f):
    rows = last_n(d.daily_series(df, f.account, f.campaign), days=35)
    fig = go.Figure()
    fig.add_scatter(x=rows["date"], y=rows["ctr"], name="Daily CTR", mode="lines+markers",
                    line=dict(color=SLATE, width=1.5), marker=dict(size=5))
    fig.add_scatter(x=f.metrics["trend_dates"], y=f.metrics["trend_values"], name="Trend",
                    line=dict(color=AMBER, width=4))
    fig.update_yaxes(title_text="CTR", tickformat=".1%", rangemode="tozero")
    return base_layout(fig)


def chart_winner(f):
    s = d.campaign_summary(df[df["account"] == f.account], days=d.WINNER_WINDOW_DAYS)
    s = s.sort_values("roas")
    colors = [GREEN if c == f.campaign else SLATE for c in s["campaign"]]
    fig = go.Figure(go.Bar(x=s["roas"], y=s["campaign"], orientation="h", marker_color=colors,
                           text=[f"{r:.1f}" for r in s["roas"]], textposition="outside",
                           hovertemplate="%{y}: ROAS %{x:.2f}<extra></extra>"))
    fig.add_vline(x=f.metrics["others_roas"], line=dict(color=INDIGO, dash="dot"),
                  annotation_text="rest of account", annotation_position="top")
    fig.update_xaxes(title_text="ROAS · last 30 days", range=[0, s["roas"].max() * 1.2])
    fig = base_layout(fig)
    fig.update_layout(hovermode="closest", showlegend=False)
    return fig


CHARTS = {
    "zero_conversion_burner": chart_burner,
    "broken_tracking": chart_tracking,
    "overpacing": chart_overpacing,
    "creative_fatigue": chart_fatigue,
    "underfunded_winner": chart_winner,
}


# ---------- triage list ----------

st.subheader("Triage queue")
st.caption("Sorted by money at stake, biggest first.")

if not findings:
    st.success("All clear: no issues detected for this account.")

for rank, f in enumerate(findings, start=1):
    with st.container(border=True):
        left, right = st.columns([2, 3], gap="large")
        with left:
            st.markdown(
                f'<span class="rank">#{rank}</span><span class="pill {f.kind}">{f.label}</span>'
                f'<div class="camp">{f.campaign}</div>'
                f'<div class="meta">{f.account} · {f.platform}</div>'
                f'<div class="money {f.kind}">₪{f.money_at_risk_ils:,.0f}</div>'
                f'<div class="note">{f.money_note}</div>'
                f'<div class="evidence">{f.evidence}</div>'
                f'<div class="action">→ {f.action}</div>',
                unsafe_allow_html=True,
            )
        with right:
            st.plotly_chart(CHARTS[f.issue_type](f), width="stretch",
                            config={"displayModeBar": False}, key=f"chart-{rank}")
