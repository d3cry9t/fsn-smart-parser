from datetime import datetime
import streamlit as st
import pandas as pd
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
        
        # Check if this specific FSN block is an Event/Sale
        is_event = any(word in context for word in ["SALE", "EVENT", "LIVE"])

        # Find all numbers in the block
        numbers = re.findall(r'(-?\d+(?:\.\d+)?)', context)
        
        base_perc = None
        base_asp = None
        lt_modifier = 0.0

        # Detect LT modifier (Plus/Minus logic)
        lt_mod_match = re.search(r'(?:LT|PLUS|MINUS)\s*(-?\d+)', context)
        if lt_mod_match:
            lt_modifier = float(lt_mod_match.group(1))

        # Categorize numbers found in the block
        for num_str in numbers:
            num = float(num_str)
            # Skip if it's the LT modifier itself
            if lt_mod_match and num_str == lt_mod_match.group(1):
                continue
            
            if 0 < num <= 100:
                base_perc = num
            elif num > 100 or num < 0: # Negative values or > 100 treated as ASP
                base_asp = num

        # Generate rows based on selected keys and detected values
        for key in selected_keys:
            val = 0.0
            
            # --- DISCOUNT / BAU LOGIC ---
            if any(x in key for x in ['percent', 'disc']):
                if base_perc is not None:
                    # Handle Event swap for %
                    if is_event and key == 'UT_disc_percent_cat': continue # Skip BAU key in event
                    if not is_event and key == 'mrp_disc_percent': continue # Skip Event key in BAU
                    
                    val = (base_perc + lt_modifier) if "LT" in key else base_perc
                    data_rows.append({"fsn": fsn, "key": key, "value": val, "expiry": ""})

            # --- ASP LOGIC ---
            elif any(x in key for x in ['absolute', 'custom']):
                if base_asp is not None:
                    # Handle Event swap for ASP
                    if is_event and key == 'custom_14': continue
                    if not is_event and key == 'custom_15': continue
                    
                    val = (base_asp + lt_modifier) if "LT" in key else base_asp
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
        mode = st.radio("Mode:", ["BAU", "ASP", "Event Mode", "Auto-Detect All"])
        
        key_map = {
            "BAU": ['UT_disc_percent_cat', 'UT_disc_percent', 'LT_disc_percent'],
            "ASP": ['custom_14', 'UT_absolute', 'LT_absolute'],
            "Event Mode": ['mrp_disc_percent', 'custom_15', 'UT_disc_percent', 'LT_disc_percent', 'UT_absolute', 'LT_absolute'],
            "Auto-Detect All": [
                'UT_disc_percent_cat', 'mrp_disc_percent', 'UT_disc_percent', 'LT_disc_percent',
                'custom_15', 'custom_14', 'UT_absolute', 'LT_absolute'
            ]
        }
        
        st.write("**Keys to Include:**")
        selected_keys = [k for k in key_map[mode] if st.checkbox(k, value=True, key=f"cb_{k}")]
        generate_btn = st.button("Generate Pricing CSV", type="primary")

    with col1:
        st.info("""
        **Smart Detection Rules:**
        - Value **<= 100**: Treated as Discount/BAU.
        - Value **> 100 or Negative**: Treated as ASP.
        - Include word **'SALE'** or **'EVENT'** to auto-switch to Event keys (mrp_disc / custom_15).
        - Use **'minus 100'** or **'-100'** for LT reductions.
        """)
        user_input = st.text_area("Paste Scenarios here:", height=400, placeholder="Example: FSN123... 50, ASP 1200, LT -100")

    if generate_btn and user_input:
        res_df = parse_advanced_scenarios(user_input, mode, selected_keys)
        if not res_df.empty:
            st.success(f"Processed {len(res_df.fsn.unique())} FSNs")
            st.dataframe(res_df, use_container_width=True)
            st.download_button("📥 Download CSV", res_df.to_csv(index=False).encode('utf-8'), "pricing_upload.csv", "text/csv")
