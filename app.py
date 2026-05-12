from datetime import datetime
import streamlit as st
import pandas as pd
import re

# --- LOGIC: CSV GENERATOR ---
def parse_advanced_scenarios(raw_text, mode, selected_keys, is_sale_live):
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
        
        # 1. Extraction Logic
        perc_match = re.search(r'\b(\d+(?:\.\d+)?)\s*%', context)
        asp_match = re.search(r'(?:ASP|RS\.?|PRICE)\s*(\d+(?:\.\d+)?)', context)
        
        # Fallback if no symbols are used (based on mode)
        fallback = re.search(r'\b(\d+(?:\.\d+)?)\b', context)
        
        base_perc = float(perc_match.group(1)) if perc_match else (float(fallback.group(1)) if (fallback and "ASP" not in mode and "BAU" in mode) else 0.0)
        base_asp = float(asp_match.group(1)) if asp_match else (float(fallback.group(1)) if (fallback and "ASP" in mode) else 0.0)

        # LT Plus logic (+5 etc)
        lt_plus = re.search(r'(?:\+|\bPLUS\b)\s*(\d+)', context)
        add_val = float(lt_plus.group(1)) if lt_plus else 0.0

        for key in selected_keys:
            val = 0.0
            # Logic for Discount keys
            if any(x in key for x in ['percent', 'disc']):
                if base_perc == 0 and not perc_match: continue # Skip if no % found in Auto mode
                val = (base_perc + add_val) if "LT" in key else base_perc
            
            # Logic for ASP keys
            elif any(x in key for x in ['absolute', 'custom']):
                if base_asp == 0 and not asp_match: continue # Skip if no ASP found in Auto mode
                val = (base_asp + add_val) if "LT" in key else base_asp
            
            data_rows.append({"fsn": fsn, "key": key, "value": val, "expiry": ""})

    return pd.DataFrame(data_rows)

# --- STREAMLIT UI ---
st.set_page_config(page_title="Ops Hub", layout="wide")
st.title("🛡️ Pricing Operations Hub")

tab1, tab2 = st.tabs(["🚀 Pricing CSV Generator", "🧹 Anomaly Cleaner"])

with tab1:
    col1, col2 = st.columns([3, 1])
    
    with col2:
        st.subheader("Config")
        mode = st.radio("Mode:", ["BAU", "Event ASP", "Full Custom", "Auto-Detect"])
        
        # Sale Toggle for logic switching
        is_sale_live = st.toggle("Is Sale/Event Live?", value=False, help="Switches UT_disc_percent_cat to mrp_disc_percent")
        
        # Define base keys
        perc_keys = [('mrp_disc_percent' if is_sale_live else 'UT_disc_percent_cat'), 'UT_disc_percent', 'LT_disc_percent']
        asp_keys_14 = ['custom_14', 'UT_absolute', 'LT_absolute']
        asp_keys_15 = ['custom_15', 'UT_absolute', 'LT_absolute']

        if mode == "BAU":
            target_keys = perc_keys
        elif mode == "Event ASP":
            target_keys = asp_keys_15
        elif mode == "Full Custom":
            target_keys = perc_keys + asp_keys_14 + asp_keys_15
        else: # Auto-Detect
            target_keys = perc_keys + asp_keys_14

        st.write("**Keys to Include:**")
        selected_keys = [k for k in target_keys if st.checkbox(k, value=True, key=f"cb_{k}")]
        generate_btn = st.button("Generate Pricing CSV", type="primary")

    with col1:
        st.info(f"💡 Currently using **{'mrp_disc_percent' if is_sale_live else 'UT_disc_percent_cat'}** based on Sale toggle.")
        user_input = st.text_area("Paste Scenarios here:", height=400, placeholder="FSN... 30%\nFSN... ASP 500")

    if generate_btn and user_input:
        res_df = parse_advanced_scenarios(user_input, mode, selected_keys, is_sale_live)
        if not res_df.empty:
            st.success(f"Generated {len(res_df)} rows.")
            st.dataframe(res_df, use_container_width=True)
            csv_data = res_df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download CSV", csv_data, "pricing_upload.csv", "text/csv")

# --- TAB 2 (Kept for completeness) ---
with tab2:
    st.header("Anomalies Data Clearance")
    # ... (Same logic as previous version)
