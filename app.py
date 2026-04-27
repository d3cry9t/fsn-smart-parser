import streamlit as st
import pandas as pd
import io
import re

# --- LOGIC: CSV GENERATOR ---
def parse_advanced_scenarios(raw_text, mode, selected_keys):
    if not selected_keys:
        return pd.DataFrame()

    # Split by FSN
    blocks = re.split(r'([A-Z0-9]{16})', raw_text)
    if len(blocks) < 2:
        return pd.DataFrame()

    data_rows = []
    for i in range(1, len(blocks), 2):
        fsn = blocks[i].strip()
        context = blocks[i+1].upper() if i+1 < len(blocks) else ""
        
        # Find base value (UT)
        base_match = re.search(r'(?<!LT\s)(?<!LT)(?<!PLUS\s)(?<!PLUS)\b(\d+(?:\.\d+)?)\b%?', context)
        base_val = float(base_match.group(1)) if base_match else 0.0

        # Find LT logic
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
    # Standardize column names (remove spaces and handle case)
    df.columns = [str(c).strip() for c in df.columns]
    
    # Mapping for flexible naming
    req_map = {
        "Rule id": "Rule id",
        "MRP": "MRP",
        "Anomaly/Not anomaly": "Anomaly/Not anomaly"
    }
    
    # Check if columns exist
    missing = [v for k, v in req_map.items() if v not in df.columns]
    if missing:
        return None, f"Missing columns: {missing}. Please check your file headers."

    initial_count = len(df)
    
    # Convert MRP to numeric safely
    df['MRP'] = pd.to_numeric(df['MRP'], errors='coerce')

    # Optimization: Vectorized filtering
    # Criteria: Rule ID does NOT start with SR_ AND MRP is > 100
    mask = (
        (~df['Rule id'].astype(str).str.startswith('SR_', na=False)) & 
        (df['MRP'] > 100)
    )
    
    clean_df = df[mask].copy()
    clean_df['Anomaly/Not anomaly'] = "Not anomaly"
    
    rows_deleted = initial_count - len(clean_df)
    return clean_df, rows_deleted

# --- STREAMLIT UI ---
st.set_page_config(page_title="Ops Hub", layout="wide")

st.title("🛡️ Operations Automation Hub")

# Create Tabs - This is where your previous error occurred
tab1, tab2 = st.tabs(["🚀 Pricing CSV Generator", "🧹 Anomaly Cleaner"])

# --- TAB 1: PRICING GENERATOR ---
with tab1:
    col1, col2 = st.columns([3, 1])
    
    with col2:
        st.subheader("Config")
        mode = st.radio("Mode:", ["Percentage", "ASP", "Mrp"])
        
        key_map = {
            "Percentage": ['UT_disc_percent_cat', 'UT_disc_percent', 'LT_disc_percent'],
            "ASP": ['custom_14', 'UT_absolute', 'LT_absolute'],
            "Mrp": ['mrp_disc_percent', 'UT_disc_percent', 'LT_disc_percent']
        }
        
        st.write("**Keys to Include:**")
        selected_keys = [k for k in key_map[mode] if st.checkbox(k, value=True, key=f"cb_{k}")]
        
        generate_btn = st.button("Generate Pricing CSV", type="primary")

    with col1:
        user_input = st.text_area("Paste Scenarios here:", height=400, placeholder="Example:\nSOPFZ2G8DYPZA3TF\nUT 34, LT 44")

    if generate_btn and user_input:
        res_df = parse_advanced_scenarios(user_input, mode, selected_keys)
        if not res_df.empty:
            st.success(f"Processed {len(res_df)//len(selected_keys) if selected_keys else 0} FSNs")
            st.dataframe(res_df, use_container_width=True)
            st.download_button("📥 Download CSV", res_df.to_csv(index=False).encode('utf-8'), "pricing_upload.csv", "text/csv")

# --- TAB 2: ANOMALY CLEANER ---
with tab2:
    st.header("Anomalies Data Clearance")
    st.info("Upload your Excel/CSV. Rules starting with 'SR_' and MRP <= 100 will be removed.")
    
    up_file = st.file_uploader("Upload file", type=["csv", "xlsx"], key="anomaly_up")
    
    if up_file:
        try:
            if up_file.name.endswith('.csv'):
                input_df = pd.read_csv(up_file)
            else:
                input_df = pd.read_excel(up_file, engine='openpyxl')
                
            if st.button("Run Deep Clean", type="primary"):
                with st.spinner("Processing large dataset..."):
                    cleaned_df, result = clean_anomalies(input_df)
                
                if cleaned_df is not None:
                    st.success(f"Cleaning Complete! {result} rows removed.")
                    
                    # Store as CSV for maximum compatibility and speed
                    csv_out = cleaned_df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Download Cleaned CSV",
                        data=csv_out,
                        file_name="Anomalies_Cleaned.csv",
                        mime="text/csv"
                    )
                else:
                    st.error(result)
        except Exception as e:
            st.error(f"Error processing file: {e}")
