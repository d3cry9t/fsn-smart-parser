from datetime import datetime
import streamlit as st
import pandas as pd
import io
import re

# --- LOGIC: CSV GENERATOR ---
def parse_advanced_scenarios(raw_text, mode, selected_keys):
    if not selected_keys:
        return pd.DataFrame()

    # Split by FSN (16 char alphanumeric)
    blocks = re.split(r'([A-Z0-9]{16})', raw_text)
    if len(blocks) < 2:
        return pd.DataFrame()

    data_rows = []
    for i in range(1, len(blocks), 2):
        fsn = blocks[i].strip()
        context = blocks[i+1].upper() if i+1 < len(blocks) else ""
        
        # --- Value Extraction Logic ---
        # 1. Percentage Extraction (Looking for % or context)
        perc_match = re.search(r'(?<!ASP)\b(\d+(?:\.\d+)?)\s*%', context)
        # 2. ASP Extraction (Looking for ASP or large numbers without %)
        asp_match = re.search(r'(?:ASP|RS\.?)\s*(\d+(?:\.\d+)?)', context)
        
        # Fallback for simple "UT 34" format based on mode
        fallback_match = re.search(r'\b(\d+(?:\.\d+)?)\b', context)
        
        # Determine Base Values
        base_perc = float(perc_match.group(1)) if perc_match else (float(fallback_match.group(1)) if (fallback_match and mode != "ASP") else 0.0)
        base_asp = float(asp_match.group(1)) if asp_match else (float(fallback_match.group(1)) if (fallback_match and mode == "ASP") else 0.0)

        # LT Logic (Supports + logic for both types)
        lt_plus = re.search(r'(?:LT\s*)?(?:\+|\bPLUS\b)\s*(\d+)', context)
        add_val = float(lt_plus.group(1)) if lt_plus else 0.0

        for key in selected_keys:
            val = 0.0
            # Assign values based on key naming conventions
            if any(x in key for x in ['percent', 'disc']):
                val = (base_perc + add_val) if "LT" in key else base_perc
            elif any(x in key for x in ['absolute', 'custom']):
                val = (base_asp + add_val) if "LT" in key else base_asp
            
            data_rows.append({"fsn": fsn, "key": key, "value": val, "expiry": ""})

    return pd.DataFrame(data_rows)

# --- LOGIC: ANOMALY CLEANER (Unchanged) ---
def clean_anomalies(df):
    df.columns = [str(c).strip() for c in df.columns]
    req_map = {"Rule id": "Rule id", "MRP": "MRP", "Anomaly/Not anomaly": "Anomaly/Not anomaly"}
    missing = [v for k, v in req_map.items() if v not in df.columns]
    if missing: return None, f"Missing columns: {missing}"

    initial_count = len(df)
    df['MRP'] = pd.to_numeric(df['MRP'], errors='coerce')
    mask = ((~df['Rule id'].astype(str).str.startswith('SR_', na=False)) & (df['MRP'] > 100))
    clean_df = df[mask].copy()
    clean_df['Anomaly/Not anomaly'] = "Not anomaly"
    return clean_df, initial_count - len(clean_df)

# --- STREAMLIT UI ---
st.set_page_config(page_title="Ops Hub", layout="wide")
st.title("🛡️ Pricing Operations Hub")

tab1, tab2 = st.tabs(["🚀 Pricing CSV Generator", "🧹 Anomaly Cleaner"])

with tab1:
    col1, col2 = st.columns([3, 1])
    
    with col2:
        st.subheader("Config")
        # Added new modes here
        mode = st.radio("Mode:", ["Percentage", "ASP", "Event ASP", "Full Custom", "Auto-Detect"])
        
        key_map = {
            "Percentage": ['UT_disc_percent_cat', 'UT_disc_percent', 'LT_disc_percent'],
            "ASP": ['custom_14', 'UT_absolute', 'LT_absolute'],
            "Event ASP": ['custom_15', 'UT_absolute', 'LT_absolute'],
            "Full Custom": ['custom_14', 'custom_15', 'UT_disc_percent', 'LT_disc_percent'],
            "Auto-Detect": ['UT_disc_percent', 'LT_disc_percent', 'custom_14', 'UT_absolute']
        }
        
        st.write("**Keys to Include:**")
        selected_keys = [k for k in key_map[mode] if st.checkbox(k, value=True, key=f"cb_{k}")]
        generate_btn = st.button("Generate Pricing CSV", type="primary")

    with col1:
        st.markdown("""
        **Input Format Examples:**
        *   **Standard:** `FSN123... UT 30, LT 35`
        *   **Auto-Detect:** `FSN123... 30%, ASP 500` (Will fill both discount and ASP keys)
        """)
        user_input = st.text_area("Paste Scenarios here:", height=400)

    if generate_btn and user_input:
        res_df = parse_advanced_scenarios(user_input, mode, selected_keys)
        if not res_df.empty:
            st.success(f"Processed {len(res_df.fsn.unique())} FSNs")
            st.dataframe(res_df, use_container_width=True)
            st.download_button("📥 Download CSV", res_df.to_csv(index=False).encode('utf-8'), "pricing_upload.csv", "text/csv")

# --- TAB 2: ANOMALY CLEANER ---
with tab2:
    st.header("Anomalies Data Clearance")
    up_file = st.file_uploader("Upload file", type=["csv", "xlsx"], key="anomaly_up")
    if up_file:
        if st.button("Clean", type="primary"):
            input_df = pd.read_csv(up_file) if up_file.name.endswith('.csv') else pd.read_excel(up_file)
            cleaned_df, result = clean_anomalies(input_df)
            if cleaned_df is not None:
                st.success(f"Cleaning Complete! {result} rows removed.")
                timestamp = datetime.now().strftime("%d-%m-%Y_%H-%M")
                st.download_button(f"📥 Download Cleaned File", cleaned_df.to_csv(index=False).encode('utf-8'), f"Cleaned_{timestamp}.csv", "text/csv")
