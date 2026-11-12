"""
Spendhound triage dashboard. Layout only.

Numbers come from detectors.py (findings) and ui_data.py (display aggregations); HTML comes from
components.py; tokens and copy from theme.py and styles.css. Run:  streamlit run app.py

Selection, filters and review state live in the URL (?issue=...&reviewed=...), because clicking a
row in the HTML table is a link and starts a fresh Streamlit session.
"""

from pathlib import Path
from urllib.parse import urlencode

import streamlit as st

import charts as ch
import components as c
import detectors as d
import theme
import ui_data as u
from generate_data import OUTPUT_FILE, generate

ROOT = Path(__file__).parent

st.set_page_config(page_title="Spendhound · Triage", layout="wide", initial_sidebar_state="collapsed")
st.html(ROOT / "styles.css")


@st.cache_data
def load(path: str):
    if not Path(path).exists():          # fresh clone without data: create it
        df = generate()
        Path(path).parent.mkdir(exist_ok=True)
        df.to_csv(path, index=False, date_format="%Y-%m-%d")
    df = d.load_data(path)
    return df, d.run_all(df)


df, findings = load(str(OUTPUT_FILE))
summary = u.workspace_summary(df)
accounts = sorted(df["account"].unique())

# ---------- URL state -> widget defaults (first run of each session only) ----------
qp = st.query_params
DEFAULTS = {"f_sev": "all", "f_account": "All accounts", "f_platform": "All", "f_query": ""}
for key, default in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = qp.get(key[2:], default)
if st.session_state.f_sev not in ["all", *theme.SEVERITY_ORDER]:
    st.session_state.f_sev = "all"
if st.session_state.f_account not in ["All accounts", *accounts]:
    st.session_state.f_account = "All accounts"
if st.session_state.f_platform not in ["All", *summary["platforms"]]:
    st.session_state.f_platform = "All"
reviewed = u.parse_ids(qp.get("reviewed"))
snoozed = u.parse_ids(qp.get("snoozed"))

# ---------- App bar + page header ----------
st.html(c.appbar(len(findings), summary["today"]))

with st.container(key="page_header", horizontal=True, vertical_alignment="bottom"):
    st.html(c.page_header(summary), width="stretch")
    with st.container(horizontal=True, horizontal_alignment="right", width="content", gap="small"):
        st.download_button("Export CSV", u.export_frame(findings).to_csv(index=False).encode("utf-8"),
                           file_name=f"spendhound-triage-{c.date_iso(summary['today'])}.csv",
                           mime="text/csv", key="export")
        if st.button("Re-run checks", type="primary", key="rerun"):
            st.cache_data.clear()
            st.rerun()

# ---------- KPI strip ----------
st.html(c.kpi_strip(u.kpis(df, findings)))

# ---------- Triage: toolbar + table (left) and detail panel (right) ----------
left, right = st.columns([3, 1], gap="small")

with left:
    with st.container(key="left"):
        with st.container(key="triage"):
            # Counts on the severity filter reflect the other filters, so they match the table.
            base = u.filter_findings(findings, account=st.session_state.f_account,
                                     platform=st.session_state.f_platform,
                                     query=st.session_state.f_query, hidden=set(snoozed))
            counts = u.severity_counts(base)
            with st.container(key="toolbar", horizontal=True, vertical_alignment="center"):
                st.segmented_control(
                    "Severity", ["all", *theme.SEVERITY_ORDER], key="f_sev",
                    format_func=lambda s: f"All :gray[**{len(base)}**]" if s == "all"
                    else f"{theme.SEVERITY[s]['label']} :gray[**{counts[s]}**]",
                    label_visibility="collapsed")
                st.selectbox("Account", ["All accounts", *accounts], key="f_account",
                             format_func=lambda a: f"Account: {a}", label_visibility="collapsed")
                st.selectbox("Platform", ["All", *summary["platforms"]], key="f_platform",
                             format_func=lambda p: f"Platform: {p}", label_visibility="collapsed")
                st.text_input("Search", key="f_query", placeholder="Search campaigns",
                              label_visibility="collapsed")

            state = {"sev": st.session_state.f_sev or "all", "account": st.session_state.f_account,
                     "platform": st.session_state.f_platform, "query": st.session_state.f_query}
            visible = [f for f in base if state["sev"] == "all" or u.severity_of(f) == state["sev"]]

            ids = [u.finding_id(f) for f in findings]
            selected_id = qp.get("issue") if qp.get("issue") in ids else (
                u.finding_id(visible[0]) if visible else None)

            def url_params(issue_id):
                p = {k: v for k, v in state.items() if v != DEFAULTS["f_" + k]}
                if issue_id:
                    p["issue"] = issue_id
                if reviewed:
                    p["reviewed"] = ",".join(reviewed)
                if snoozed:
                    p["snoozed"] = ",".join(snoozed)
                return p

            st.query_params.from_dict(url_params(selected_id))

            rows = [{
                "finding": f, "severity": u.severity_of(f), "signal": u.signal_line(f),
                "spark": u.spark_series(df, f), "highlight": u.SPARK_METRIC[f.issue_type][1],
                "href": "?" + urlencode(url_params(u.finding_id(f))),
                "selected": u.finding_id(f) == selected_id, "reviewed": u.finding_id(f) in reviewed,
            } for f in visible]
            st.html(c.triage_table(rows, len(findings), len(snoozed)))

        with st.container(key="accounts"):
            st.html(c.accounts_table(u.account_rows(df, findings)))

def set_review_state(param, ids):
    """Persist reviewed/snoozed ids in the URL so they survive row clicks (page reloads)."""
    if ids:
        st.query_params[param] = ",".join(ids)
    elif param in st.query_params:
        del st.query_params[param]


with right:
    with st.container(key="detail"):
        f = u.find_by_id(findings, selected_id) if selected_id else None
        if f is None:
            st.html(c.detail_empty())
        else:
            sev, fid = u.severity_of(f), selected_id
            note = "Snoozed for 7 days" if fid in snoozed else ("Reviewed" if fid in reviewed else "")
            st.html(c.detail_top(f, sev, u.money_breakdown(f), note))
            fig, legend, window = ch.evidence_chart(df, f)
            st.html(c.chart_heading(legend, window))
            st.plotly_chart(fig, config=theme.PLOTLY_CONFIG, key=f"chart-{fid}")
            st.html(c.detail_bottom(f, sev, u.key_numbers(f), theme.rule_lines(f.issue_type),
                                    theme.NEXT_STEPS[f.issue_type]))
            with st.container(key="dfoot", horizontal=True):
                if st.button("Undo review" if fid in reviewed else "Mark reviewed",
                             type="primary", key="b_review"):
                    set_review_state("reviewed", u.toggle_id(reviewed, fid))
                    st.rerun()
                if st.button("Unsnooze" if fid in snoozed else "Snooze 7d", key="b_snooze"):
                    set_review_state("snoozed", u.toggle_id(snoozed, fid))
                    st.rerun()
                if st.button("Copy for client", type="tertiary", key="b_client"):
                    st.session_state.show_client = not st.session_state.get("show_client", False)
            if st.session_state.get("show_client"):
                with st.container(key="client_text"):
                    st.html('<div class="note-line">Use the copy icon to copy this note.</div>')
                    st.code(u.client_summary(f), language=None, wrap_lines=True)
