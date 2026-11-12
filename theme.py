"""
Spendhound design tokens, severity lookup, static UI copy and the Plotly chart template.

Design only: no business math lives here (rule #1 in CLAUDE.md). Visual reference: design_v2.html.
CSS lives in styles.css and uses the same values as the tokens below.
"""

import plotly.graph_objects as go
import plotly.io as pio

import detectors as d

# ---------------------------------------------------------------------------
# Color tokens
# ---------------------------------------------------------------------------

BG = "#F4F5F7"
SURFACE = "#FFFFFF"
SURFACE_2 = "#F9FAFB"
BORDER = "#E3E6EB"
BORDER_STRONG = "#CDD2DA"
GRID = "#EDEFF3"

INK = "#16202E"
INK_2 = "#4A5568"
INK_3 = "#7A8496"
INK_4 = "#A3ABB8"

BRAND = "#14213D"
ACTION = "#1D5FD6"
ACTION_HOVER = "#174EB3"
ACTION_TINT = "#EAF1FD"

# Chart context series: everything that is "normal" is grey; only the anomaly gets color.
CONTEXT_BAR = "#CDD3DD"
CONTEXT_LINE = "#1F2A44"
SPARK_LINE = "#5B6475"

FONT = '"IBM Plex Sans", -apple-system, "Segoe UI", Roboto, sans-serif'
MONO = '"IBM Plex Mono", ui-monospace, Menlo, monospace'

# ---------------------------------------------------------------------------
# Severity: fixed lookup by issue type. Shape + label + color, never color alone.
# ---------------------------------------------------------------------------

CRITICAL, WARNING, OPPORTUNITY = "critical", "warning", "opportunity"

SEVERITY_FOR = {
    "broken_tracking": CRITICAL,
    "zero_conversion_burner": CRITICAL,
    "overpacing": WARNING,
    "creative_fatigue": WARNING,
    "underfunded_winner": OPPORTUNITY,
}

SEVERITY_ORDER = [CRITICAL, WARNING, OPPORTUNITY]

SEVERITY = {
    CRITICAL: dict(label="Critical", css="crit", text="#B42318", tint="#FEF0EF",
                   line="#F6C9C5", solid="#D1342F", solid_2="#E8625E",
                   icon='<path d="M5 0.8 9.4 8.8H0.6Z" fill="currentColor"/>'),
    WARNING: dict(label="Warning", css="warn", text="#9A4A00", tint="#FFF5E6",
                  line="#F7D9AE", solid="#D97706", solid_2="#F0A94A",
                  icon='<rect x="1.5" y="1.5" width="7" height="7" transform="rotate(45 5 5)" '
                       'fill="currentColor"/>'),
    OPPORTUNITY: dict(label="Opportunity", css="opp", text="#11663A", tint="#ECF8F0",
                      line="#BFE5CD", solid="#15803D", solid_2="#4FA36B",
                      icon='<circle cx="5" cy="5" r="4" fill="currentColor"/>'),
}

# ---------------------------------------------------------------------------
# Static copy per issue type. Words only; every number comes from detectors.py or ui_data.py.
# ---------------------------------------------------------------------------

WORKSPACE = "Northwind Media"

ISSUE_TITLE = {
    "broken_tracking": "Broken tracking",
    "zero_conversion_burner": "Zero-conversion spend",
    "overpacing": "Budget overpacing",
    "creative_fatigue": "Creative fatigue",
    "underfunded_winner": "Underfunded winner",
}

# Short time-horizon note under the amount in the triage table.
HORIZON_SHORT = {
    "broken_tracking": "gap + next 7 days",
    "zero_conversion_burner": "next 30 days",
    "overpacing": "overspend this month",
    "creative_fatigue": "next 30 days",
    "underfunded_winner": "upside / month",
}

# Longer note next to the big number in the detail panel.
HORIZON_LONG = {
    "broken_tracking": "spent blind so far plus the next 7 days",
    "zero_conversion_burner": "if spend continues for 30 days",
    "overpacing": "projected overspend this month",
    "creative_fatigue": "lost to lower CTR over the next 30 days",
    "underfunded_winner": "potential net gain per month",
}

NEXT_STEPS = {
    "broken_tracking": [
        ("Open the platform's conversion settings and confirm the conversion event fired in the last 24 hours.", ""),
        ("Check that the thank-you page still loads the tag or pixel.", "Site deploys are the usual cause."),
        ("Hold bid and budget changes until conversions are recorded again.", ""),
    ],
    "zero_conversion_burner": [
        ("Pause the campaign or cut its daily budget.", ""),
        ("Audit targeting, landing page and offer before restarting.", ""),
        ("Move the freed budget to a campaign that converts.", ""),
    ],
    "overpacing": [
        ("Lower the daily budget so the month lands on plan.", ""),
        ("Check the change history for an accidental budget or bid change.", ""),
        ("Confirm with the client whether the extra spend was approved.", ""),
    ],
    "creative_fatigue": [
        ("Rotate in fresh creative for this audience.", ""),
        ("Pause the lowest-CTR ads in the ad set.", ""),
        ("Consider widening the audience to reduce frequency.", ""),
    ],
    "underfunded_winner": [
        ("Raise the budget gradually, for example 30% per week.", ""),
        ("Watch ROAS after each increase and stop if it drops.", ""),
        ("Fund the increase from the account's weakest campaign.", ""),
    ],
}


def rule_lines(issue_type):
    """The detector's rule in plain words, using the named thresholds from detectors.py."""
    low, high = d.TRACKING_CLICK_BAND
    rules = {
        "broken_tracking": [
            f"conversions == 0 for ≥ {d.TRACKING_MIN_ZERO_DAYS} consecutive days",
            f"AND clicks between {low:.0%} and {high:.0%} of the {d.TRACKING_BASELINE_DAYS}-day baseline",
            f"AND baseline ≥ {d.TRACKING_MIN_BASELINE_CONV} conversions per day",
        ],
        "zero_conversion_burner": [
            f"spend ≥ ₪{d.BURNER_MIN_SPEND:,} in the last {d.BURNER_WINDOW_DAYS} days",
            f"AND conversions ≤ {d.BURNER_MAX_CONVERSIONS} in the same window",
        ],
        "overpacing": [
            "projected month spend > "
            f"{d.OVERPACE_TOLERANCE:.0%} of monthly budget",
            f"projection = month-to-date + {d.OVERPACE_RUN_RATE_DAYS}-day run rate x days left",
            f"only from day {d.OVERPACE_MIN_DAYS_ELAPSED} of the month",
        ],
        "creative_fatigue": [
            f"CTR trend over {d.FATIGUE_WINDOW_DAYS} days down ≥ {d.FATIGUE_MIN_DECLINE:.0%}",
            f"AND trend fit R² ≥ {d.FATIGUE_MIN_R2:.2f}",
        ],
        "underfunded_winner": [
            f"ROAS ({d.WINNER_WINDOW_DAYS}d) ≥ {d.WINNER_MIN_ROAS:g}",
            f"AND ≥ {d.WINNER_MIN_ROAS_MULTIPLE:g}x the rest of the account",
            f"AND spend ≥ {d.WINNER_CAP_SHARE:.0%} of daily cap on ≥ "
            f"{d.WINNER_MIN_CAPPED_DAY_SHARE:.0%} of the last {d.WINNER_CAP_DAYS} days",
        ],
    }
    return rules[issue_type]


# ---------------------------------------------------------------------------
# Plotly template: white, horizontal gridlines only, no legend box, light hover labels.
# ---------------------------------------------------------------------------

_axis = dict(
    showgrid=False, zeroline=False, showline=False, ticks="",
    tickfont=dict(size=11, color=INK_3, family=FONT), title=dict(text=""),
)

pio.templates["spendhound"] = go.layout.Template(layout=dict(
    font=dict(family=FONT, size=11, color=INK_3),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    colorway=[CONTEXT_LINE, CONTEXT_BAR],
    showlegend=False,
    margin=dict(l=4, r=4, t=8, b=4),
    hovermode="x unified",
    hoverlabel=dict(bgcolor=SURFACE, bordercolor=BORDER, font=dict(family=FONT, size=12, color=INK)),
    xaxis=_axis,
    yaxis={**_axis, "showgrid": True, "gridcolor": GRID, "gridwidth": 1},
    bargap=0.3,
))

PLOTLY_TEMPLATE = "spendhound"
PLOTLY_CONFIG = {"displayModeBar": False}
