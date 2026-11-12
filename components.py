"""
HTML builders for the dashboard. Rendering only: values arrive already computed
(from detectors.py or ui_data.py) and are only formatted here.
"""

from html import escape

import theme

CHEVRON = ('<svg width="10" height="10" viewBox="0 0 10 10"><path d="M2.5 4 5 6.5 7.5 4" '
           'stroke="#7A8496" stroke-width="1.4" fill="none"/></svg>')
LOGO = ('<svg width="14" height="14" viewBox="0 0 14 14"><path d="M2 10.5 5.2 6.8 7.6 9 12 3.5" '
        'stroke="#fff" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def ils(x, sign=False):
    return f"{'+' if sign else ''}₪{x:,.0f}"


def pct(x, digits=1):
    return f"{x:.{digits}%}"


def date_iso(ts):
    return f"{ts:%Y-%m-%d}"


def appbar(n_issues, today):
    return f"""
<header class="appbar">
  <div class="logo"><span class="mark">{LOGO}</span>Spendhound</div>
  <div class="ws">{escape(theme.WORKSPACE)} {CHEVRON}</div>
  <nav class="nav">
    <span class="on">Triage<span class="cnt">{n_issues}</span></span>
    <span>Accounts</span><span>Checks</span><span>Reports</span>
  </nav>
  <div class="right"><span class="sync"><i></i>Data as of {date_iso(today)}</span></div>
</header>"""


def page_header(summary):
    n = summary["n_accounts"]
    platforms = ", ".join("Google Ads" if p == "Google" else p for p in summary["platforms"])
    return f"""
<div class="ph">
  <div class="crumb">{escape(theme.WORKSPACE)} · {n} client account{'s' if n != 1 else ''} · {platforms}</div>
  <h1>Triage</h1>
  <div class="sub">Issues ranked by money at stake. Every figure is computed from account data, not estimated by AI.</div>
</div>"""
