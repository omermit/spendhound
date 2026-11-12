"""
Evidence charts for the detail panel. Context series are grey; only the anomalous segment gets the
severity color, with a tinted band and a direct annotation. Values come from detectors.py.

Each builder returns (figure, legend, window_label); the legend is drawn in HTML above the chart.
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import detectors as d
import theme

HEIGHT = 190
HALF_DAY = pd.Timedelta(hours=12)


def _sev(f):
    return theme.SEVERITY[theme.SEVERITY_FOR[f.issue_type]]


def _layout(fig, **kw):
    fig.update_layout(template=theme.PLOTLY_TEMPLATE, height=HEIGHT, **kw)
    fig.update_xaxes(tickformat="%d %b", nticks=5)
    # The template styles only the first y-axis; apply to secondary axes too, or labels get clipped.
    fig.update_yaxes(automargin=True, tickfont=dict(size=11, color=theme.INK_3, family=theme.PLOT_FONT))
    return fig


def _band(fig, x0, x1, sev, text):
    fig.add_vrect(x0=x0, x1=x1, fillcolor=sev["tint"], opacity=1, line_width=0, layer="below")
    fig.add_annotation(x=x0, y=1, xref="x", yref="paper", text=text, showarrow=False,
                       xanchor="right", yanchor="top", xshift=-6,
                       font=dict(size=11, color=sev["text"], family=theme.PLOT_FONT),
                       bgcolor="rgba(255,255,255,0.85)", borderpad=2)


def _last(rows, today, days):
    return rows[rows["date"] > today - pd.Timedelta(days=days)]


def chart_tracking(df, f):
    sev, m = _sev(f), f.metrics
    today = df["date"].max()
    rows = _last(d.daily_series(df, f.account, f.campaign), today, 21)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_bar(x=rows["date"], y=rows["clicks"], name="Clicks", marker_color=theme.CONTEXT_BAR)
    fig.add_scatter(x=rows["date"], y=rows["conversions"], name="Conversions", mode="lines",
                    line=dict(color=theme.CONTEXT_LINE, width=1.75), secondary_y=True)
    gap = rows[rows["date"] >= m["break_start"] - pd.Timedelta(days=1)]
    fig.add_scatter(x=gap["date"], y=gap["conversions"], name="Conversions (gap)", mode="lines+markers",
                    line=dict(color=sev["solid"], width=2),
                    marker=dict(size=6, color="#fff", line=dict(color=sev["solid"], width=1.5)),
                    secondary_y=True, hoverinfo="skip")
    _band(fig, m["break_start"] - HALF_DAY, today + HALF_DAY, sev,
          f"Tracking gap · {m['zero_days']} days →")
    fig.update_yaxes(rangemode="tozero", secondary_y=False)
    fig.update_yaxes(rangemode="tozero", showgrid=False, tickformat=",d", secondary_y=True)
    legend = [("Clicks (left)", "blk", theme.CONTEXT_BAR), ("Conversions (right)", "line", theme.CONTEXT_LINE)]
    return _layout(fig), legend, "last 21 days"


def chart_burner(df, f):
    sev, m = _sev(f), f.metrics
    today = df["date"].max()
    rows = _last(d.daily_series(df, f.account, f.campaign), today, 30)
    window = _last(rows, today, d.BURNER_WINDOW_DAYS)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_bar(x=rows["date"], y=rows["cost"], name="Spend (₪)", marker_color=theme.CONTEXT_BAR)
    fig.add_scatter(x=rows["date"], y=rows["conversions"], name="Conversions", mode="lines",
                    line=dict(color=theme.CONTEXT_LINE, width=1.75), secondary_y=True)
    fig.add_scatter(x=window["date"], y=window["conversions"], name="Conversions (window)",
                    mode="lines", line=dict(color=sev["solid"], width=2), secondary_y=True,
                    hoverinfo="skip")
    n = m["conversions"]
    _band(fig, window["date"].iloc[0] - HALF_DAY, today + HALF_DAY, sev,
          f"₪{m['spend']:,.0f} · {n} conversion{'s' if n != 1 else ''} →")
    fig.update_yaxes(rangemode="tozero", tickprefix="₪", secondary_y=False)
    fig.update_yaxes(range=[0, 5], dtick=1, showgrid=False, secondary_y=True)
    legend = [("Spend (left)", "blk", theme.CONTEXT_BAR), ("Conversions (right)", "line", theme.CONTEXT_LINE)]
    return _layout(fig), legend, "last 30 days"


def chart_overpacing(df, f):
    sev, m = _sev(f), f.metrics
    actual, projected = d.pacing_series(df, f.account, f.campaign)
    fig = go.Figure()
    fig.add_scatter(x=actual["date"], y=actual["cumulative"], name="Spent so far", mode="lines",
                    line=dict(color=theme.CONTEXT_LINE, width=2))
    fig.add_scatter(x=projected["date"], y=projected["cumulative"], name="Projected", mode="lines",
                    line=dict(color=sev["solid"], width=2, dash="dash"))
    fig.add_hline(y=m["budget"], line=dict(color=theme.INK_4, width=1.25, dash="dot"),
                  annotation_text=f"Budget ₪{m['budget']:,.0f}", annotation_position="top left",
                  annotation_font=dict(size=11, color=theme.INK_3))
    _band(fig, projected["date"].iloc[0], projected["date"].iloc[-1] + HALF_DAY, sev,
          f"+₪{f.money_at_risk_ils:,.0f} over budget →")
    fig.update_yaxes(rangemode="tozero", tickprefix="₪")
    legend = [("Spent so far", "line", theme.CONTEXT_LINE), ("Projected", "dash", sev["solid"]),
              ("Monthly budget", "dash", theme.INK_4)]
    return _layout(fig), legend, "this month"


def chart_fatigue(df, f):
    sev, m = _sev(f), f.metrics
    today = df["date"].max()
    rows = _last(d.daily_series(df, f.account, f.campaign), today, 35)
    fig = go.Figure()
    fig.add_scatter(x=rows["date"], y=rows["ctr"], name="Daily CTR", mode="lines",
                    line=dict(color=theme.CONTEXT_LINE, width=1.5))
    fig.add_scatter(x=m["trend_dates"], y=m["trend_values"], name="Trend", mode="lines",
                    line=dict(color=sev["solid"], width=2.5), hoverinfo="skip")
    _band(fig, m["trend_dates"][0] - HALF_DAY, today + HALF_DAY, sev,
          f"CTR −{m['decline']:.0%} in {d.FATIGUE_WINDOW_DAYS} days →")
    fig.update_yaxes(tickformat=".1%", rangemode="tozero")
    legend = [("Daily CTR", "line", theme.CONTEXT_LINE), ("Trend", "line", sev["solid"])]
    return _layout(fig), legend, "last 35 days"


def chart_winner(df, f):
    sev, m = _sev(f), f.metrics
    s = d.campaign_summary(df[df["account"] == f.account], days=d.WINNER_WINDOW_DAYS).sort_values("roas")
    colors = [sev["solid"] if c == f.campaign else theme.CONTEXT_BAR for c in s["campaign"]]
    fig = go.Figure(go.Bar(x=s["roas"], y=s["campaign"], orientation="h", marker_color=colors,
                           text=[f"{r:.1f}" for r in s["roas"]], textposition="outside",
                           textfont=dict(size=11, color=theme.INK_2),
                           hovertemplate="%{y}: ROAS %{x:.2f}<extra></extra>"))
    fig.add_vline(x=m["others_roas"], line=dict(color=theme.CONTEXT_LINE, width=1.25, dash="dot"),
                  annotation_text=f"Rest of account {m['others_roas']:.1f}",
                  annotation_position="top right", annotation_font=dict(size=11, color=theme.INK_2))
    fig = _layout(fig, hovermode="closest", margin=dict(l=16, r=28, t=22, b=4))
    fig.update_xaxes(range=[0, s["roas"].max() * 1.25], tickformat="", nticks=5,
                     showgrid=True, gridcolor=theme.GRID)
    fig.update_yaxes(showgrid=False, tickfont=dict(family=theme.PLOT_MONO, size=10, color=theme.INK_3))
    legend = [("This campaign", "blk", sev["solid"]), ("Other campaigns", "blk", theme.CONTEXT_BAR)]
    return fig, legend, f"ROAS, last {d.WINNER_WINDOW_DAYS} days"


BUILDERS = {
    "broken_tracking": chart_tracking,
    "zero_conversion_burner": chart_burner,
    "overpacing": chart_overpacing,
    "creative_fatigue": chart_fatigue,
    "underfunded_winner": chart_winner,
}


def evidence_chart(df, f):
    return BUILDERS[f.issue_type](df, f)
