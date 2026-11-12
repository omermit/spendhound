"""
HTML builders for the dashboard. Rendering only: values arrive already computed
(from detectors.py or ui_data.py) and are only formatted here.
"""

import base64
from html import escape

import theme


def svg_img(svg, w, h, alt=""):
    """st.html sanitizes inline <svg>, so SVGs are embedded as data-URI images instead."""
    if 'xmlns=' not in svg:
        svg = svg.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
    data = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return (f'<img src="data:image/svg+xml;base64,{data}" width="{w}" height="{h}" '
            f'alt="{escape(alt)}" style="display:block">')

CHEVRON = svg_img('<svg width="10" height="10" viewBox="0 0 10 10"><path d="M2.5 4 5 6.5 7.5 4" '
           'stroke="#7A8496" stroke-width="1.4" fill="none"/></svg>', 10, 10)
LOGO = svg_img('<svg width="14" height="14" viewBox="0 0 14 14"><path d="M2 10.5 5.2 6.8 7.6 9 12 3.5" '
        'stroke="#fff" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>', 14, 14)


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


def kpi_strip(k):
    sev = theme.SEVERITY
    # Alternate two shades within a severity so adjacent findings stay distinguishable.
    seen, spans = {}, []
    for s in k["at_risk_segments"]:
        n = seen.get(s["severity"], 0)
        seen[s["severity"]] = n + 1
        color = sev[s["severity"]]["solid" if n % 2 == 0 else "solid_2"]
        spans.append(f'<span style="width:{s["share"] * 100:.2f}%;background:{color}" '
                     f'title="{sev[s["severity"]]["label"]} {ils(s["amount"])}"></span>')
    legend = "".join(
        f'<span><i style="background:{sev[s]["solid"]}"></i>{sev[s]["label"]} {ils(v)}</span>'
        for s, v in k["at_risk_by_severity"].items())
    counts = k["severity_counts"]
    breakdown = " · ".join(f"{counts[s]} {sev[s]['label'].lower()}" for s in theme.SEVERITY_ORDER)
    n_up = k["n_upside"]
    return f"""
<section class="kpis">
  <div class="kpi"><div class="l">Money at risk</div>
    <div class="v{' crit' if k['at_risk'] else ''}">{ils(k['at_risk'])}</div>
    <div class="bar">{''.join(spans)}</div>
    <div class="legend">{legend}</div></div>
  <div class="kpi"><div class="l">Spend, last 30 days</div><div class="v">{ils(k['spend_30d'])}</div>
    <div class="d"><span class="bad">{pct(k['pct_spend_at_risk'])}</span> of spend is at risk</div></div>
  <div class="kpi"><div class="l">Upside found</div><div class="v">{ils(k['upside'])}</div>
    <div class="d">{n_up} underfunded campaign{'s' if n_up != 1 else ''} · <span class="good">per month</span></div></div>
  <div class="kpi"><div class="l">Open issues</div><div class="v">{k['n_open']}</div>
    <div class="d">{breakdown}</div></div>
  <div class="kpi"><div class="l">Accounts affected</div>
    <div class="v">{k['accounts_affected']} <small>/ {k['n_accounts']}</small></div>
    <div class="d">Accounts with at least one issue</div></div>
</section>"""


def status_chip(severity):
    s = theme.SEVERITY[severity]
    icon = svg_img(f'<svg width="10" height="10" viewBox="0 0 10 10">'
                   f'{s["icon"].replace("currentColor", s["solid"])}</svg>', 10, 10)
    return f'<span class="status {s["css"]}">{icon}{s["label"]}</span>'


def plat_mark(platform):
    css, letter = ("meta", "M") if platform == "Meta" else ("goog", "G")
    return f'<span class="plat {css}" title="{escape(platform)}">{letter}</span>'


def sparkline(values, highlight_last, color, w=80, h=24, pad=2):
    """Inline SVG polyline; values are scaled to the box (drawing only, not data math)."""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    step = (w - 2) / max(len(values) - 1, 1)
    pts = [(1 + i * step, pad + (h - 2 * pad) * (1 - (v - lo) / span)) for i, v in enumerate(values)]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    dot = (f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="2.2" fill="{color}"/>'
           if highlight_last else "")
    return svg_img(f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
                   f'<polyline points="{poly}" fill="none" stroke="{theme.SPARK_LINE}" stroke-width="1.5" '
                   f'stroke-linejoin="round" stroke-linecap="round"/>{dot}</svg>', w, h)


def triage_table(rows, n_total, n_hidden):
    """rows: dicts with finding, severity, signal, spark, highlight, href, selected, reviewed."""
    body = []
    for r in rows:
        f, sev = r["finding"], r["severity"]
        a = f'<a class="rowlink" href="{escape(r["href"])}">'
        up = f.kind == "opportunity"
        cls = " ".join(x for x in ("selected" if r["selected"] else "",
                                   "reviewed" if r["reviewed"] else "") if x)
        tag = '<span class="tag">Reviewed</span>' if r["reviewed"] else ""
        body.append(f"""<tr class="{cls}">
  <td>{a}{status_chip(sev)}</a></td>
  <td>{a}<div class="t1">{escape(theme.ISSUE_TITLE[f.issue_type])}{tag}</div>
      <div class="t2 sig">{escape(r['signal'])}</div></a></td>
  <td>{a}<div class="t1 mono-ish">{escape(f.campaign)}</div>
      <div class="t2">{plat_mark(f.platform)}{escape(f.account)}</div></a></td>
  <td>{a}{sparkline(r['spark'], r['highlight'], theme.SEVERITY[sev]['solid'])}</a></td>
  <td class="num muted">{a}—</a></td>
  <td class="num">{a}<div class="amt{' up' if up else ''}">{ils(f.money_at_risk_ils, sign=up)}</div>
      <div class="t2 r">{escape(theme.HORIZON_SHORT[f.issue_type])}</div></a></td>
</tr>""")
    if not rows:
        body.append('<tr><td colspan="6" class="empty">No issues match these filters.</td></tr>')
    n = len(rows)
    hidden = f" · {n_hidden} snoozed, hidden" if n_hidden else ""
    shown = f"{n} of {n_total} issues" if n != n_total else f"{n} issue{'s' if n != 1 else ''}"
    return f"""
<table class="tbl triage">
  <colgroup><col style="width:128px"><col><col style="width:220px"><col style="width:104px">
    <col style="width:56px"><col style="width:150px"></colgroup>
  <thead><tr><th>Severity</th><th>Issue and signal</th><th>Campaign and account</th>
    <th>14-day trend</th><th class="num">Open</th><th class="num sorted">At stake ↓</th></tr></thead>
  <tbody>{''.join(body)}</tbody>
</table>
<div class="tfoot"><span>{shown}{hidden} · sorted by money at stake</span>
  <span>Thresholds are listed under “Why this was flagged”</span></div>"""


def fmt(value, kind):
    return {
        "ils": lambda v: ils(v),
        "pct0": lambda v: f"{v:.0%}",
        "pct2": lambda v: f"{v:.2%}",
        "num1": lambda v: f"{v:.1f}",
        "num2": lambda v: f"{v:.2f}",
        "int": lambda v: f"{int(v):,}",
        "date": lambda v: date_iso(v),
    }[kind](value)


def detail_top(f, severity, breakdown, status_note=""):
    s = theme.SEVERITY[severity]
    platform = "Google Ads" if f.platform == "Google" else "Meta Ads"
    rows = []
    for i, (label, value, kind) in enumerate(breakdown):
        cls = ' class="sum"' if i == len(breakdown) - 1 else ""
        rows.append(f"<span{cls}>{escape(label)}</span><b{cls}>{fmt(value, kind)}</b>")
    note = f'<span class="tag">{escape(status_note)}</span>' if status_note else ""
    up = f.kind == "opportunity"
    return f"""
<div class="dh">
  <div>{status_chip(severity)}{note}</div>
  <h2>{escape(theme.ISSUE_TITLE[f.issue_type])} on {escape(f.campaign)}</h2>
  <div class="meta">{plat_mark(f.platform)}{escape(f.account)} · {platform}</div>
</div>
<div class="sec">
  <h3>{'Upside' if up else 'Money at stake'} <span>ILS</span></h3>
  <div class="stake"><span class="big {s['css']}">{ils(f.money_at_risk_ils, sign=up)}</span>
    <span class="hz">{escape(theme.HORIZON_LONG[f.issue_type])}</span></div>
  <div class="kv">{''.join(rows)}</div>
</div>"""


def chart_heading(legend, window):
    items = []
    for label, kind, color in legend:
        if kind == "blk":
            items.append(f'<span><i class="blk" style="background:{color}"></i>{escape(label)}</span>')
        elif kind == "dash":
            items.append(f'<span><i class="dash" style="border-color:{color}"></i>{escape(label)}</span>')
        else:
            items.append(f'<span><i style="background:{color}"></i>{escape(label)}</span>')
    return (f'<div class="sec chart-top"><h3>Evidence <span>{escape(window)}</span></h3>'
            f'<div class="clegend">{"".join(items)}</div></div>')


def detail_bottom(f, severity, numbers, rules, steps):
    css = theme.SEVERITY[severity]["css"]
    kv = "".join(f'<span>{escape(label)}</span><b class="{css if hl else ""}">{fmt(v, kind)}</b>'
                 for label, v, kind, hl in numbers)
    rule = "<br>".join(escape(line) for line in rules)
    items = "".join(f"<li>{escape(text)}{' <span>' + escape(note) + '</span>' if note else ''}</li>"
                    for text, note in steps)
    return f"""
<div class="sec chart-bottom"><div class="kv" style="margin-top:4px">{kv}</div></div>
<div class="sec"><h3>Why this was flagged</h3><div class="rule">{rule}</div></div>
<div class="sec"><h3>Recommended next steps</h3><ol class="steps">{items}</ol></div>"""


def detail_empty():
    return ('<div class="sec"><h3>No issue selected</h3>'
            '<div class="muted">Select a row in the triage table to see its evidence.</div></div>')


def page_header(summary):
    n = summary["n_accounts"]
    platforms = ", ".join("Google Ads" if p == "Google" else p for p in summary["platforms"])
    return f"""
<div class="ph">
  <div class="crumb">{escape(theme.WORKSPACE)} · {n} client account{'s' if n != 1 else ''} · {platforms}</div>
  <h1>Triage</h1>
  <div class="sub">Issues ranked by money at stake. Every figure is computed from account data, not estimated by AI.</div>
</div>"""
