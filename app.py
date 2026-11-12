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
                    format_func=lambda s: f"All {len(base)}" if s == "all"
                    else f"{theme.SEVERITY[s]['label']} {counts[s]}",
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

with right:
    with st.container(key="detail"):
        st.html('<div class="sec">Detail panel</div>')
