from datetime import datetime

import streamlit as st

import re
import pandas as pd

# --- Database keys, grouped by the kind of value they carry --------------
PERC_KEYS = ("UT_disc_percent_cat", "mrp_disc_percent", "UT_disc_percent", "LT_disc_percent")
ASP_KEYS = ("custom_15", "custom_14", "UT_absolute", "LT_absolute")

ALL_KEYS = (
    "UT_disc_percent_cat", "mrp_disc_percent", "UT_disc_percent", "LT_disc_percent",
    "custom_15", "custom_14", "UT_absolute", "LT_absolute",
)

# Which keys each mode pre-selects.
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
    """A number in 0..100 is a percentage; anything else is an absolute price."""
    if value is None:
        return None
    return "perc" if 0 <= value <= 100 else "asp"


def parse_scenarios(raw_text, mode, selected_keys):
    """Translate free-text pricing notes into upload rows.

    mode is one of: BAU, ASP, Event, Auto, Manual.
    Returns a DataFrame with columns fsn / key / value / expiry.
    """
    if not selected_keys:
        return pd.DataFrame(columns=_OUT_COLS)

    blocks = re.split(r"([A-Z0-9]{16})", raw_text)
    if len(blocks) < 2:
        return pd.DataFrame(columns=_OUT_COLS)

    rows = []
    for i in range(1, len(blocks), 2):
        fsn = blocks[i].strip()
        context = blocks[i + 1].upper() if i + 1 < len(blocks) else ""

        # FIX 2: "2,279" is one number (2279). Drop commas only when they sit
        # *between two digits*, so the separator in "40, LT 35" stays intact.
        context = re.sub(r"(?<=\d),(?=\d)", "", context)

        is_event = (mode == "Event") or any(w in context for w in ("SALE", "EVENT", "LIVE"))

        # ---- Detect the LT instruction ---------------------------------
        lt_abs = None    # "LT 60"        -> set lower tier to 60
        lt_rel = None    # "LT +5"/"-100" -> shift lower tier by the delta
        lt_span = None   # the text we consumed, removed before reading the base

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

        # ---- Read the base (upper-tier) numbers ------------------------
        base_text = context.replace(lt_span, " ", 1) if lt_span else context
        base_perc = None
        base_asp = None
        for tok in re.findall(_NUM, base_text):
            num = float(tok)
            if 0 <= num <= 100:          # FIX 1: 0 is a valid percentage
                base_perc = num
            elif num > 100 or num < 0:
                base_asp = num

        # Which tier does the LT instruction belong to?
        #  - absolute "LT 60": by magnitude (0..100 -> %, else ₹)
        #  - relative "LT +5/-100": attach to whichever base exists; if that is
        #    ambiguous (hybrid) fall back to magnitude (a >=100 shift is ₹).
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

        # ---- Emit the selected keys ------------------------------------
        for key in selected_keys:
            is_perc = key in PERC_KEYS
            is_asp = key in ASP_KEYS
            is_lt = key.startswith("LT")
            kind = "perc" if is_perc else ("asp" if is_asp else None)
            base = base_perc if is_perc else (base_asp if is_asp else None)

            # mode-aware swaps: cat<->mrp and custom_14<->custom_15
            if mode != "Manual":
                if is_event and key in ("UT_disc_percent_cat", "custom_14"):
                    continue
                if not is_event and key in ("mrp_disc_percent", "custom_15"):
                    continue

            val = None
            if is_lt:
                # FIX 3: an explicit LT can stand on its own, with no base.
                if lt_abs is not None and lt_kind == kind:
                    val = lt_abs                       # explicit "LT 60"
                elif lt_rel is not None and lt_kind == kind and base is not None:
                    val = base + lt_rel                # relative shift
                elif base is not None:
                    val = base                         # default: LT mirrors UT
            else:
                if base is not None:
                    val = base

            if val is not None:
                rows.append({"fsn": fsn, "key": key, "value": val, "expiry": ""})

    return pd.DataFrame(rows, columns=_OUT_COLS)


# --- Anomaly cleaner ------------------------------------------------------
def _find_col(df, needle):
    needle = needle.lower()
    for c in df.columns:
        if needle in str(c).lower():
            return c
    return None


def clean_anomalies(df):
    """Apply the 3-step cleanse described in the manual.

    1) drop rows whose Rule id starts with "SR_"
    2) drop rows whose MRP <= 100
    3) force the remaining Anomaly status field to "Not anomaly"

    Returns (clean_df, stats).
    """
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


# ====================  STREAMLIT UI  ====================
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
