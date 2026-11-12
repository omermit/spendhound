"""
Spendhound triage dashboard. Layout only.

Numbers come from detectors.py (findings) and ui_data.py (display aggregations); HTML comes from
components.py; tokens and copy from theme.py and styles.css. Run:  streamlit run app.py
"""

from pathlib import Path

import streamlit as st

import components as c
import detectors as d
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
