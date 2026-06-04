from datetime import datetime

import re
import pandas as pd
import streamlit as st

# =========================================================================
#  DATA LOGIC  (pure)
# =========================================================================
PERC_KEYS = ("UT_disc_percent_cat", "mrp_disc_percent", "UT_disc_percent", "LT_disc_percent")
ASP_KEYS = ("custom_15", "custom_14", "UT_absolute", "LT_absolute")

ALL_KEYS = (
    "UT_disc_percent_cat", "mrp_disc_percent", "UT_disc_percent", "LT_disc_percent",
    "custom_15", "custom_14", "UT_absolute", "LT_absolute",
)

MODE_KEYS = {
    "BAU":   ["UT_disc_percent_cat", "UT_disc_percent", "LT_disc_percent"],
    "ASP":   ["custom_14", "UT_absolute", "LT_absolute"],
    "Event": ["mrp_disc_percent", "UT_disc_percent", "LT_disc_percent",
              "custom_15", "UT_absolute", "LT_absolute"],
    "Auto":  list(ALL_KEYS),
    "Manual": list(ALL_KEYS),
}

_NUM = r"-?\d+(?:\.\d+)?"
_OUT_COLS = ["fsn", "key", "value", "expiry"]


def _value_kind(value):
    if value is None:
        return None
    return "perc" if 0 <= value <= 100 else "asp"


def parse_scenarios(raw_text, mode, selected_keys):
    """Translate free-text pricing notes into upload rows."""
    if not selected_keys:
        return pd.DataFrame(columns=_OUT_COLS)

    blocks = re.split(r"([A-Z0-9]{16})", raw_text)
    if len(blocks) < 2:
        return pd.DataFrame(columns=_OUT_COLS)

    rows = []
    for i in range(1, len(blocks), 2):
        fsn = blocks[i].strip()
        context = blocks[i + 1].upper() if i + 1 < len(blocks) else ""

        # "2,279" is one number (2279); drop commas only between two digits.
        context = re.sub(r"(?<=\d),(?=\d)", "", context)

        is_event = (mode == "Event") or any(w in context for w in ("SALE", "EVENT", "LIVE"))

        lt_abs = None
        lt_rel = None
        lt_span = None

        m_abs = re.search(r"\bLT\s*(\d+(?:\.\d+)?)\b", context)
        if m_abs:
            lt_abs = float(m_abs.group(1))
            lt_span = m_abs.group(0)
        else:
            m_signed = re.search(r"(?:LT\s*)?([+\-]\s*\d+(?:\.\d+)?)", context)
            m_plus = re.search(r"\bPLUS\s*(\d+(?:\.\d+)?)", context)
            m_minus = re.search(r"\bMINUS\s*(\d+(?:\.\d+)?)", context)
            if m_signed:
                lt_rel = float(re.sub(r"\s+", "", m_signed.group(1)))
                lt_span = m_signed.group(0)
            elif m_plus:
                lt_rel = float(m_plus.group(1))
                lt_span = m_plus.group(0)
            elif m_minus:
                lt_rel = -float(m_minus.group(1))
                lt_span = m_minus.group(0)

        base_text = context.replace(lt_span, " ", 1) if lt_span else context
        base_perc = None
        base_asp = None
        for tok in re.findall(_NUM, base_text):
            num = float(tok)
            if 0 <= num <= 100:          # 0 is a valid percentage
                base_perc = num
            elif num > 100 or num < 0:
                base_asp = num

        if lt_abs is not None:
            lt_kind = _value_kind(lt_abs)
        elif lt_rel is not None:
            if base_perc is not None and base_asp is None:
                lt_kind = "perc"
            elif base_asp is not None and base_perc is None:
                lt_kind = "asp"
            else:
                lt_kind = "perc" if abs(lt_rel) < 100 else "asp"
        else:
            lt_kind = None

        for key in selected_keys:
            is_perc = key in PERC_KEYS
            is_asp = key in ASP_KEYS
            is_lt = key.startswith("LT")
            kind = "perc" if is_perc else ("asp" if is_asp else None)
            base = base_perc if is_perc else (base_asp if is_asp else None)

            if mode != "Manual":
                if is_event and key in ("UT_disc_percent_cat", "custom_14"):
                    continue
                if not is_event and key in ("mrp_disc_percent", "custom_15"):
                    continue

            val = None
            if is_lt:
                if lt_abs is not None and lt_kind == kind:
                    val = lt_abs
                elif lt_rel is not None and lt_kind == kind and base is not None:
                    val = base + lt_rel
                elif base is not None:
                    val = base
            else:
                if base is not None:
                    val = base

            if val is not None:
                rows.append({"fsn": fsn, "key": key, "value": val, "expiry": ""})

    return pd.DataFrame(rows, columns=_OUT_COLS)


def _find_col(df, needle):
    needle = needle.lower()
    for c in df.columns:
        if needle in str(c).lower():
            return c
    return None


def clean_anomalies(df):
    """Drop SR_ test rules + MRP<=100 rows, then force status to 'Not anomaly'."""
    out = df.copy()
    stats = {"input_rows": len(out)}

    rule_col = _find_col(out, "rule id")
    mrp_col = _find_col(out, "mrp")
    flag_col = _find_col(out, "anomaly")

    if rule_col is not None:
        mask = out[rule_col].astype(str).str.startswith("SR_")
        stats["dropped_sr"] = int(mask.sum())
        out = out[~mask]
    else:
        stats["dropped_sr"] = 0

    if mrp_col is not None:
        mrp_num = pd.to_numeric(out[mrp_col], errors="coerce")
        mask = (mrp_num <= 100).fillna(False)
        stats["dropped_low_mrp"] = int(mask.sum())
        out = out[~mask]
    else:
        stats["dropped_low_mrp"] = 0

    if flag_col is not None:
        out[flag_col] = "Not anomaly"

    out = out.reset_index(drop=True)
    stats["output_rows"] = len(out)
    stats["columns"] = {"rule": rule_col, "mrp": mrp_col, "flag": flag_col}
    return out, stats


def ist_now():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Kolkata"))
    except Exception:
        from datetime import timedelta, timezone
        return datetime.now(timezone(timedelta(hours=5, minutes=30)))


# =========================================================================
#  UI
# =========================================================================
st.set_page_config(page_title="Pricing Ops Hub", page_icon="🛡️", layout="wide")

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
    "Auto":  "Keeps every key; values routed by magnitude.",
    "Manual": "You choose exactly which keys are written.",
}

st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

      html, body, [class*="css"], .stMarkdown, .stTextArea, .stRadio, button, input, textarea {
          font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      }

      #MainMenu, footer {visibility: hidden;}
      [data-testid="stToolbar"] {visibility: hidden;}

      .block-container {padding-top: 2.2rem; max-width: 1180px;}

      .app-header {border-bottom: 1px solid #e8eaf0; padding-bottom: 0.9rem; margin-bottom: 1.6rem;}
      .app-header h1 {font-size: 1.6rem; font-weight: 700; color: #11131a; margin: 0; letter-spacing: -0.01em;}
      .app-header p {font-size: 0.92rem; color: #6b7280; margin: 0.28rem 0 0 0;}

      .stTabs [data-baseweb="tab-list"] {gap: 0.4rem;}
      .stTabs [data-baseweb="tab"] {font-weight: 600; font-size: 0.92rem; padding: 0.5rem 0.2rem;}

      [data-testid="stMetric"] {background: #f7f8fb; border: 1px solid #eceef3; border-radius: 12px; padding: 0.9rem 1rem;}
      [data-testid="stMetricLabel"] {color: #6b7280; font-weight: 500;}

      .stButton > button, .stDownloadButton > button {border-radius: 10px; font-weight: 600; border: 1px solid #d7dae3; transition: all .15s ease;}
      .stButton > button[kind="primary"] {background: #4f46e5; border-color: #4f46e5;}
      .stButton > button[kind="primary"]:hover {background: #4338ca; border-color: #4338ca;}

      .stTextArea textarea {border-radius: 10px; font-family: 'SFMono-Regular', Menlo, monospace; font-size: 0.88rem;}

      section[data-testid="stSidebar"] {background: #fafbfc; border-right: 1px solid #eef0f4;}
      section[data-testid="stSidebar"] h2 {font-size: 1.05rem; font-weight: 700;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="app-header">
      <h1>Pricing Operations Hub</h1>
      <p>Compile free-text pricing notes into upload-ready files, and scrub anomaly exports in one pass.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Pricing config")
    mode = st.radio(
        "Operation mode",
        options=list(MODE_LABELS),
        format_func=lambda m: MODE_LABELS[m],
    )
    st.caption(MODE_HELP[mode])
    st.divider()

    with st.expander("Keys to write", expanded=(mode == "Manual")):
        defaults = MODE_KEYS[mode]
        selected_keys = [
            k for k in ALL_KEYS
            if st.checkbox(k, value=(k in defaults), key=f"cb_{mode}_{k}")
        ]

tab_price, tab_clean = st.tabs(["Pricing CSV Generator", "Anomaly Cleaner"])

with tab_price:
    user_input = st.text_area(
        "Scenario input",
        height=300,
        placeholder="SOPFZ2G8DYPZA3TF 34, LT 39\nSPPGM5H6HHUBZQNN LT 60\nABCDEFGH12345678 0 LT 20",
        help="Each FSN is a 16-character code (A-Z, 0-9). Text up to the next code is its instruction.",
    )
    go = st.button("Process data", type="primary")

    if go:
        if not user_input.strip():
            st.warning("Paste at least one FSN line first.")
        elif not selected_keys:
            st.warning("Select at least one key in the sidebar.")
        else:
            df = parse_scenarios(user_input, mode, selected_keys)
            if df.empty:
                st.error("No FSNs recognised - codes must be 16 characters (A-Z, 0-9).")
            else:
                st.success(f"Processed {df['fsn'].nunique()} FSN(s) -> {len(df)} rows.")
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.download_button(
                    "Download pricing CSV",
                    df.to_csv(index=False).encode("utf-8"),
                    file_name="pricing_upload.csv",
                    mime="text/csv",
                )

with tab_clean:
    st.caption('Drops SR_ test rules and MRP <= 100 rows, then marks the rest "Not anomaly".')
    up = st.file_uploader("Upload tracking export", type=["xlsx", "csv"])

    if up is not None:
        try:
            raw = pd.read_csv(up) if up.name.lower().endswith(".csv") else pd.read_excel(up)
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not read the file: {e}")
            raw = None

        if raw is not None:
            st.write(f"Loaded **{len(raw)}** rows / **{len(raw.columns)}** columns.")
            if st.button("Run deep clean", type="primary"):
                clean, stats = clean_anomalies(raw)

                c1, c2, c3 = st.columns(3)
                c1.metric("Rows in", stats["input_rows"])
                c2.metric(
                    "Removed",
                    stats["input_rows"] - stats["output_rows"],
                    help=f"SR_ rules: {stats['dropped_sr']} / MRP<=100: {stats['dropped_low_mrp']}",
                )
                c3.metric("Rows out", stats["output_rows"])

                missing = [n for n, c in stats["columns"].items() if c is None]
                if missing:
                    st.warning("Couldn't find a column for: " + ", ".join(missing)
                               + ". Those step(s) were skipped.")

                st.dataframe(clean.head(200), use_container_width=True, hide_index=True)
                st.download_button(
                    "Download cleaned CSV",
                    clean.to_csv(index=False).encode("utf-8"),
                    file_name=f"Anomalies_Cleaned_{ist_now():%d-%m-%Y_%H-%M}.csv",
                    mime="text/csv",
                )
