import streamlit as st
import pandas as pd
import io
import re

def parse_advanced_scenarios(raw_text, mode):
    # 1. Define Key Mapping based on Mode
    if mode == "Percentage":
        keys = ['UT_disc_percent_cat', 'UT_disc_percent', 'LT_disc_percent']
    elif mode == "ASP":
        keys = ['custom_14', 'UT_absolute', 'LT_absolute']
    else:  # P0 Mode
        keys = ['mrp_disc_percent', 'UT_disc_percent', 'LT_disc_percent']

    # Split input by FSN to process each block individually
    blocks = re.split(r'([A-Z0-9]{16})', raw_text)
    # The first element might be empty or header text, skip it
    if len(blocks) < 2:
        return pd.DataFrame()

    data_rows = []
    
    # Process blocks in pairs: [FSN, text_following_it]
    for i in range(1, len(blocks), 2):
        fsn = blocks[i].strip()
        context = blocks[i+1].upper() if i+1 < len(blocks) else ""
        
        # --- A. Find Base Value (UT) ---
        # Look for the first number that isn't attached to "LT" or "PLUS"
        base_match = re.search(r'(?<!LT\s)(?<!LT)(?<!PLUS\s)(?<!PLUS)\b(\d+(?:\.\d+)?)\b%?', context)
        base_val = float(base_match.group(1)) if base_match else 0.0

        # --- B. Find LT Value (Override or Math) ---
        lt_val = base_val # Default: LT is same as UT
        
        # 1. Check for absolute LT (e.g., "LT 44")
        lt_absolute = re.search(r'LT\s*(\d+(?:\.\d+)?)', context)
        # 2. Check for Plus logic (e.g., "LT +10", "plus 10", "LT plus 10")
        lt_plus = re.search(r'(?:LT\s*)?(?:\+|\bPLUS\b)\s*(\d+)', context)

        if lt_absolute:
            lt_val = float(lt_absolute.group(1))
        elif lt_plus:
            lt_val = base_val + float(lt_plus.group(1))

        # --- C. Generate Rows ---
        for key in keys:
            val = lt_val if "LT" in key else base_val
            data_rows.append({
                "fsn": fsn,
                "key": key,
                "value": val,
                "expiry": ""
            })

    return pd.DataFrame(data_rows)

# --- Streamlit UI ---
st.set_page_config(page_title="Pricing CSV", layout="wide")
st.title("FSN Parser & CSV Generator")

col1, col2 = st.columns([3, 1])

with col1:
    user_input = st.text_area("Paste Scenarios:", height=400, 
                              placeholder="kaise bhi daaldo fan aur value hona chahiye & if LT is required just mention 'LT' word")

with col2:
    mode = st.radio("Select Mode:", ["Percentage", "ASP", "P0"])
    st.write(f"**Target Keys:**")
    display_keys = (['UT_disc_percent_cat', 'UT_disc_percent', 'LT_disc_percent'] if mode == "Percentage" else 
                    ['custom_14', 'UT_absolute', 'LT_absolute'] if mode == "ASP" else 
                    ['mrp_disc_percent', 'UT_disc_percent', 'LT_disc_percent'])
    for k in display_keys:
        st.code(k)
    
    generate_btn = st.button("Generate CSV", type="primary", use_container_width=True)

if generate_btn and user_input:
    df = parse_advanced_scenarios(user_input, mode)
    if not df.empty:
        st.success("Scenarios Processed!")
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Download CSV 👀", data=csv, file_name=f"{mode}_upload.csv")
    else:
        st.error("No valid FSNs found. Ensure FSNs are 16 characters long.")
