from datetime import datetime
import streamlit as st
import pandas as pd
import re
import pytz

# --- PREMIUM CSS STYLING ---
def apply_custom_style():
    st.markdown("""
    <style>
        /* Main background */
        .stApp {
            background-color: #0e1117;
        }
        
        /* Glassmorphism containers */
        div[data-testid="stVerticalBlock"] > div:has(div.stTextArea) {
            background: rgba(255, 255, 255, 0.05);
            padding: 20px;
            border-radius: 15px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        }

        /* Buttons styling */
        .stButton>button {
            width: 100%;
            border-radius: 8px;
            height: 3em;
            background-color: #ff4b4b;
            color: white;
            font-weight: bold;
            border: none;
            transition: all 0.3s ease;
        }
        .stButton>button:hover {
            background-color: #ff3333;
            box-shadow: 0 4px 15px rgba(255, 75, 75, 0.4);
            transform: translateY(-2px);
        }

        /* Tabs styling */
        .stTabs [data-baseweb="tab-list"] {
            gap: 10px;
        }
        .stTabs [data-baseweb="tab"] {
            height: 50px;
            background-color: rgba(255, 255, 255, 0.05);
            border-radius: 10px 10px 0 0;
            padding: 0 20px;
            color: white;
        }
        .stTabs [aria-selected="true"] {
            background-color: rgba(255, 75, 75, 0.2) !important;
            border-bottom: 2px solid #ff4b4b !important;
        }

        /* Sidebar styling */
        section[data-testid="stSidebar"] {
            background-color: #161b22;
            border-right: 1px solid rgba(255, 255, 255, 0.1);
        }

        /* Headers */
        h1, h2, h3 {
            font-family: 'Inter', sans-serif;
            letter-spacing: -1px;
        }
    </style>
    """, unsafe_allow_html=True)

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
        numbers = re.findall(r'(-?\d+(?:\.\d+)?)', context)
        
        base_perc = None
        base_asp = None

        lt_abs_match = re.search(r'LT\s*(\d+(?:\.\d+)?)\b(?!\s*[\+\-])', context)
        lt_rel_match = re.search(r'(?:LT|PLUS|MINUS|\+)\s*(-?\d+(?:\.\d+)?)', context)

        for num_str in numbers:
            num = float(num_str)
            if lt_abs_match and num_str == lt_abs_match.group(1): continue
            if lt_rel_match and num_str == lt_rel_match.group(1): continue
            
            if 0 < num <= 100:
                base_perc = num
            elif num > 100 or num < 0:
                base_asp = num

        for key in selected_keys:
            val = None
            is_perc_key = any(x in key for x in ['percent', 'disc'])
            is_asp_key = any(x in key for x in ['absolute', 'custom'])

            if mode != "Manual Selector":
                if is_perc_key:
                    if is_event and key == 'UT_disc_percent_cat': continue
                    if not is_event and key == 'mrp_disc_percent': continue
                if is_asp_key:
                    if is_event and key == 'custom_14': continue
                    if not is_event and key == 'custom_15': continue

            base = base_perc if is_perc_key else base_asp if is_asp_key else None

            if base is not None:
                if "LT" in key:
                    if lt_abs_match: val = float(lt_abs_match.group(1))
                    elif lt_rel_match: val = base + float(lt_rel_match.group(1))
                    else: val = base
                else:
                    val = base

            if val is not None:
                data_rows.append({"fsn": fsn, "key": key, "value": val, "expiry": ""})

    return pd.DataFrame(data_rows)

# --- STREAMLIT UI ---
st.set_page_config(page_title="Ops Hub Pro", layout="wide", initial_sidebar_state="expanded")
apply_custom_style()

# Sidebar Brand & Config
with st.sidebar:
    st.markdown("<h1 style='color: #ff4b4b;'>🛡️ OPS HUB PRO</h1>", unsafe_allow_html=True)
    st.markdown("---")
    
    st.subheader("⚙️ Control Panel")
    mode = st.selectbox("Operation Mode", ["BAU", "ASP", "Event Mode", "Auto-Detect All", "Manual Selector"])
    
    all_possible_keys = [
        'UT_disc_percent_cat', 'mrp
