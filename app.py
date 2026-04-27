import streamlit as st
import pandas as pd
import io
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
        
        base_match = re.search(r'(?<!LT\s)(?<!LT)(?<!PLUS\s)(?<!PLUS)\b(\d+(?:\.\d+)?)\b%?', context)
        base_val = float(base_match.group(1)) if base_match else 0.0

        lt_val = base_val 
        lt_absolute = re.search(r'LT\s*(\d+(?:\.\d+)?)', context)
        lt_plus = re.search(r'(?:LT\s*)?(?:\+|\bPLUS\b)\s*(\d+)', context)

        if lt_absolute:
            lt_val = float(lt_absolute.group(1))
        elif lt_plus:
            lt_val = base_val + float(lt_plus.group(1))

        for key in selected_keys:
            val = lt_val if "LT" in key else base_val
            data_rows.append({"fsn": fsn, "key": key, "value": val, "expiry": ""})

    return pd.DataFrame(data_rows)

# --- LOGIC: ANOMALY CLEANER ---
def clean_anomalies(df):
    """
    Optimized version of the VBA logic:
    1. Removes rows where 'Rule id' starts with 'SR_'
    2. Removes rows where 'MRP' <= 100
    3. Updates 'Anomaly/Not anomaly' to 'Not anomaly'
    """
    # Standardize column names to match VBA search (case-insensitive)
    df.columns = [c.strip() for c in df.columns]
    
    # Validation
    required = ["Rule id", "MRP", "Anomaly/Not anomaly"]
    if not all(col in df.columns for col in required):
        return None, f"Missing columns. Need: {required}"

    initial_count = len(df)

    # Filtering (Vectorized - Much faster than VBA loop)
    # Keep rows where Rule id does NOT start with SR_ AND MRP is > 100
    mask = (
        (~df['Rule id'].astype(str).str.startswith('SR_', na=False)) & 
        (pd.to_numeric(df['MRP'], errors='coerce') > 100)
    )
    
    clean_df = df[mask].copy()
    
    # Update Status
    clean_df['Anomaly/Not anomaly'] = "Not anomaly"
    
    rows_deleted = initial_count - len(clean_df)
    return clean_df, rows_deleted

# --- STREAMLIT UI ---
st.set_page_config(page_title="Ops Hub", layout="wide")

# Create Tabs
tab1, tab2 = st.tabs(["🚀 Pricing CSV Generator", "🧹 Anomaly Cleaner"])

# --- TAB 1: PRICING GENERATOR ---
with tab1:
    col1, col2 = st.columns([3, 1])
    
    with col2:
        st.subheader("Configuration")
        mode = st.radio("Mode:", ["Percentage", "ASP", "P0"])
        
        # Define Key Mapping
        key_map = {
            "Percentage": ['UT_disc_percent_cat', 'UT_disc_percent', 'LT_disc_percent'],
            "ASP": ['custom_14', 'UT_absolute', 'LT_absolute'],
            "P0": ['mrp_disc_percent', 'UT_disc_percent', 'LT_disc_percent']
        }
        
        # KEY SELECTION (Default all selected)
        st.write("**Select Keys to Include:**")
        selected_keys = []
        for k in key_map[mode]:
            if st.checkbox(k, value=True):
                selected_keys.append(k)
        
        generate_btn = st.button("Generate CSV", type="primary", use_container_width=True)

    with col1:
        user_input = st.text_area("Paste Scenarios:", height=450, placeholder="SOPFZ2G8DYPZA3TF\nUT 34, LT 44")

    if generate_btn and user_input:
        res_df = parse_advanced_scenarios(user_input, mode, selected_keys)
        if not res_df.empty:
            st.success("CSV Ready!")
            st.dataframe(res_df, use_container_width=True)
            st.download_button("📥 Download Pricing CSV", res_df.to_csv(index=False).encode('utf-8'), "pricing_upload.csv")

# --- TAB 2: ANOMALY CLEANER ---
with tab2:
    st.header("Anomalies Data Clearance")
    st.write("Upload your Excel/CSV file to remove SR_ rules and low MRP rows.")
    
    uploaded_file = st.file_uploader("Upload Anomalies File", type=["csv", "xlsx"])
    
    if uploaded_file:
        # Load data
        if uploaded_file.name.endswith('.csv'):
            input_df = pd.read_csv(uploaded_file)
        else:
            input_df = pd.read_excel(uploaded_file)
            
        st.write("### File Preview (Original)")
        st.dataframe(input_df.head(5), use_container_width=True)
        
        if st.button("Clean Data", type="primary"):
            cleaned_df, result = clean_anomalies(input_df)
            
            if cleaned_df is not None:
                st.success(f"Cleaning Complete! {result} rows removed.")
                st.write("### Preview (Cleaned)")
                st.dataframe(cleaned_df.head(5), use_container_width=True)
                
                # Download
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    cleaned_df.to_excel(writer, index=False)
                
                st.download_button(
                    label="📥 Download Cleaned File",
                    data=output.getvalue(),
                    file_name="Anomalies_Cleaned.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.error(result)
