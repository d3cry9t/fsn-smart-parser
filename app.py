from datetime import datetime
import streamlit as st
import pandas as pd
import re

# --- LOGIC: CSV GENERATOR ---
def parse_advanced_scenarios(raw_text, mode, selected_keys):
    if not selected_keys:
        return pd.DataFrame()

    blocks = re.split(r'([A-Z0-9]{16})', raw_text)
    if len(blocks) < 2:
        return pd.DataFrame()

    data_rows = []
    for i in range(1, len(blocks), 2):
        fsn = blocks[i].strip()
        context = blocks[i+1].upper() if i+1 < len(blocks) else ""
        
        is_event = (mode == "Event Mode") or any(word in context for word in ["SALE", "EVENT", "LIVE"])

        # Extract all numbers
        numbers = re.findall(r'(-?\d+(?:\.\d+)?)', context)
        
        base_perc = None
        base_asp = None

        # 1. Detect LT Logic
        # Pattern for "LT 40" (Absolute) or "LT +5"/"LT -100" (Relative)
        lt_abs_match = re.search(r'LT\s*(\d+(?:\.\d+)?)\b(?!\s*[\+\-])', context)
        lt_rel_match = re.search(r'(?:LT|PLUS|MINUS|\+)\s*(-?\d+(?:\.\d+)?)', context)

        # 2. Categorize Base Values (Threshold 101)
        for num_str in numbers:
            num = float(num_str)
            # Skip if this number is likely the LT value/modifier
            if lt_abs_match and num_str == lt_abs_match.group(1): continue
            if lt_rel_match and num_str == lt_rel_match.group(1): continue
            
            if 0 < num <= 100:
                base_perc = num
            elif num > 100 or num < 0:
                base_asp = num

        # 3. Process Keys
        for key in selected_keys:
            val = None
            base = None
            
            # Identify if key is Percentage or ASP
            is_perc_key = any(x in key for x in ['percent', 'disc'])
            is_asp_key = any(x in key for x in ['absolute', 'custom'])

            # Smart Filtering (Skip in Manual Mode)
            if mode != "Manual Selector":
                if is_perc_key:
                    if is_event and key == 'UT_disc_percent_cat': continue
                    if not is_event and key == 'mrp_disc_percent': continue
                if is_asp_key:
                    if is_event and key == 'custom_14': continue
                    if not is_event and key == 'custom_15': continue

            # Assign Base
            if is_perc_key: base = base_perc
            if is_asp_key: base = base_asp

            if base is not None:
                if "LT" in key:
                    if lt_abs_match: # "LT 40"
                        val = float(lt_abs_match.group(1))
                    elif lt_rel_match: # "LT +5" or "LT -100"
                        val = base + float(lt_rel_match.group(1))
                    else:
                        val = base # Default LT = UT if no LT instruction
                else:
                    val = base # UT/Custom Keys

            if val is not None:
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
        mode = st.radio("Mode:", ["BAU", "ASP", "Event Mode", "Auto-Detect All", "Manual Selector"])
        
        all_possible_keys = [
            'UT_disc_percent_cat', 'mrp_disc_percent', 'UT_disc_percent', 'LT_disc_percent',
            'custom_15', 'custom_14', 'UT_absolute', 'LT_absolute'
        ]
        
        key_map = {
            "BAU": ['UT_disc_percent_cat', 'UT_disc_percent', 'LT_disc_percent'],
            "ASP": ['custom_14', 'UT_absolute', 'LT_absolute'],
            "Event Mode": ['mrp_disc_percent', 'UT_disc_percent', 'LT_disc_percent', 'custom_15', 'UT_absolute', 'LT_absolute'],
            "Auto-Detect All": all_possible_keys,
            "Manual Selector": all_possible_keys
        }
        
        st.write("**Keys to Include:**")
        current_keys = key_map[mode]
        selected_keys = [k for k in all_possible_keys if st.checkbox(k, value=(k in current_keys), key=f"cb_{k}_{mode}")]
        
        generate_btn = st.button("Generate Pricing CSV", type="primary")

    with col1:
        st.info("""
        **LT Instruction Examples:**
        - `40, LT 35` -> UT is 40, LT is 35 (Absolute)
        - `40, LT +5` -> UT is 40, LT is 45 (Addition)
        - `1200, LT -100` -> UT is 1200, LT is 1100 (Subtraction)
        """)
        user_input = st.text_area("Paste Scenarios here:", height=400)

    if generate_btn and user_input:
        res_df = parse_advanced_scenarios(user_input, mode, selected_keys)
        if not res_df.empty:
            st.success(f"Processed {len(res_df.fsn.unique())} FSNs")
            st.dataframe(res_df, use_container_width=True)
            st.download_button("📥 Download CSV", res_df.to_csv(index=False).encode('utf-8'), "pricing_upload.csv", "text/csv")
