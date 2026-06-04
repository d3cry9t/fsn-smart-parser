from datetime import datetime

import pandas as pd
import streamlit as st

from pricing_logic import ALL_KEYS, MODE_KEYS, parse_scenarios, clean_anomalies

st.set_page_config(page_title="Pricing Ops Hub", page_icon="🛡️", layout="wide")

# --- Mode metadata --------------------------------------------------------
MODE_LABELS = {
    "BAU":   "BAU · Standard discounts (%)",
    "ASP":   "ASP · Absolute price (₹)",
    "Event": "Event / Sale · Hybrid",
    "Auto":  "Auto-detect",
    "Manual": "Manual",
}
MODE_HELP = {
    "BAU":   "Percentage discounts for normal trading days.",
    "ASP":   "Absolute selling-price values for ASP days.",
    "Event": "Percentage + absolute keys for live campaigns.",
    "Auto":  "Keeps every key; values are routed by magnitude.",
    "Manual": "You choose exactly which keys are written.",
}


def ist_now():
    """Current time anchored to IST, no external dependency required."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Kolkata"))
    except Exception:
        from datetime import timedelta, timezone
        return datetime.now(timezone(timedelta(hours=5, minutes=30)))


# --- Header ---------------------------------------------------------------
st.title("🛡️ Pricing Operations Hub")
st.caption("Turn free-text pricing notes into upload-ready files, and scrub anomaly exports in one click.")

# --- Sidebar: pricing configuration --------------------------------------
with st.sidebar:
    st.header("⚙️ Pricing config")
    mode = st.radio(
        "Operation mode",
        options=list(MODE_LABELS),
        format_func=lambda m: MODE_LABELS[m],
    )
    st.caption(MODE_HELP[mode])

    with st.expander("🔑 Keys to write", expanded=(mode == "Manual")):
        st.caption("Tick the database keys this run should output.")
        defaults = MODE_KEYS[mode]
        selected_keys = [
            k for k in ALL_KEYS
            if st.checkbox(k, value=(k in defaults), key=f"cb_{mode}_{k}")
        ]

tab_price, tab_clean = st.tabs(["🚀 Pricing CSV Generator", "🧹 Anomaly Cleaner"])

# --- Tab 1: pricing -------------------------------------------------------
with tab_price:
    left, right = st.columns([3, 2], gap="large")

    with left:
        st.subheader("Scenario input")
        user_input = st.text_area(
            "Paste FSNs and instructions (one per line):",
            height=340,
            placeholder="SOPFZ2G8DYPZA3TF 34, LT 39\nSPPGM5H6HHUBZQNN LT 60\nABCDEFGH12345678 0 LT 20",
        )
        go = st.button("🚀 Process data", type="primary", use_container_width=True)

    with right:
        with st.expander("📖 How to write a line", expanded=True):
            st.markdown(
                "- `FSN 34` → UT **34%**, LT mirrors UT (**34%**)\n"
                "- `FSN 34, LT 39` → UT **34%**, LT **39%**\n"
                "- `FSN 34, LT +5` → UT **34%**, LT **39%**\n"
                "- `FSN 1200, LT -100` → UT **₹1200**, LT **₹1100**\n"
                "- `FSN 2,279` → **₹2279** (comma ignored)\n"
                "- `FSN LT 60` → only the **LT** key is written\n"
                "- `FSN 0 LT 20` → UT **0%**, LT **20%** (zeros are kept)"
            )
        st.info("FSNs are 16-character codes (A–Z, 0–9). Everything after a code, "
                "up to the next one, is read as its instruction.")

    if go:
        if not user_input.strip():
            st.warning("Paste at least one FSN line first.")
        elif not selected_keys:
            st.warning("Select at least one key in the sidebar.")
        else:
            df = parse_scenarios(user_input, mode, selected_keys)
            if df.empty:
                st.error("No FSNs recognised. FSNs must be 16-character codes (A–Z, 0–9).")
            else:
                st.success(f"Processed {df['fsn'].nunique()} FSN(s) → {len(df)} rows.")
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.download_button(
                    "📥 Download pricing CSV",
                    df.to_csv(index=False).encode("utf-8"),
                    file_name="pricing_upload.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

# --- Tab 2: anomaly cleaner ----------------------------------------------
with tab_clean:
    st.subheader("Anomaly cleaner")
    st.caption('Drops SR_ test rules and MRP ≤ 100 rows, then marks the rest "Not anomaly".')

    up = st.file_uploader("Upload tracking export", type=["xlsx", "csv"])
    if up is not None:
        try:
            raw = pd.read_csv(up) if up.name.lower().endswith(".csv") else pd.read_excel(up)
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not read the file: {e}")
            raw = None

        if raw is not None:
            st.write(f"Loaded **{len(raw)}** rows · **{len(raw.columns)}** columns.")
            if st.button("✨ Run deep clean", type="primary"):
                clean, stats = clean_anomalies(raw)

                c1, c2, c3 = st.columns(3)
                c1.metric("Rows in", stats["input_rows"])
                c2.metric(
                    "Removed",
                    stats["input_rows"] - stats["output_rows"],
                    help=f"SR_ rules: {stats['dropped_sr']} · MRP≤100: {stats['dropped_low_mrp']}",
                )
                c3.metric("Rows out", stats["output_rows"])

                missing = [n for n, c in stats["columns"].items() if c is None]
                if missing:
                    st.warning("Couldn't find a column for: " + ", ".join(missing)
                               + ". Those step(s) were skipped.")

                st.dataframe(clean.head(200), use_container_width=True, hide_index=True)
                fname = f"Anomalies_Cleaned_{ist_now():%d-%m-%Y_%H-%M}.csv"
                st.download_button(
                    "📥 Download cleaned CSV",
                    clean.to_csv(index=False).encode("utf-8"),
                    file_name=fname,
                    mime="text/csv",
                )
