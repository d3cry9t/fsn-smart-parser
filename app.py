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
# --- LOGIC: ANOMALY CLEANER (Optimized) ---
def clean_anomalies(df):
    # Standardize column names
    df.columns = [c.strip() for c in df.columns]
    
    # Validation
    required = ["Rule id", "MRP", "Anomaly/Not anomaly"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        return None, f"Missing columns: {missing}"

    initial_count = len(df)

    # Convert MRP to numeric once, move invalid to NaN
    df['MRP'] = pd.to_numeric(df['MRP'], errors='coerce')

    # Apply filters using a single efficient mask
    # Logic: Keep if Rule ID doesn't start with SR_ AND MRP is > 100
    mask = (
        (~df['Rule id'].astype(str).str.startswith('SR_', na=False)) & 
        (df['MRP'] > 100)
    )
    
    # Create the cleaned dataframe
    clean_df = df[mask].copy()
    
    # Update Status
    clean_df['Anomaly/Not anomaly'] = "Not anomaly"
    
    rows_deleted = initial_count - len(clean_df)
    return clean_df, rows_deleted

# --- (Inside TAB 2 UI) ---
with tab2:
    st.header("Anomalies Data Clearance")
    uploaded_file = st.file_uploader("Upload Anomalies File", type=["csv", "xlsx"])
    
    if uploaded_file:
        try:
            # Use engine='openpyxl' for better memory management with .xlsx
            if uploaded_file.name.endswith('.csv'):
                input_df = pd.read_csv(uploaded_file)
            else:
                input_df = pd.read_excel(uploaded_file, engine='openpyxl')
                
            if st.button("Run Deep Clean", type="primary"):
                cleaned_df, result = clean_anomalies(input_df)
                
                if cleaned_df is not None:
                    st.success(f"Done! Removed {result} rows.")
                    
                    # Store as CSV in memory for faster download (Excel is heavy)
                    csv_data = cleaned_df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Download Cleaned File (CSV)",
                        data=csv_data,
                        file_name="Anomalies_Cleaned.csv",
                        mime="text/csv"
                    )
                    st.info("Note: Downloaded as CSV for speed. You can open this in Excel.")
                else:
                    st.error(result)
        except Exception as e:
            st.error(f"Error loading file: {e}")
