import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
import json
import os
import datetime
import calendar
import requests
import re
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image

# ==========================================
# 1. PAGE SETUP & THEME ENGINE
# ==========================================
st.set_page_config(page_title="Finance Command Center", page_icon="💎", layout="wide")

if 'theme' not in st.session_state:
    st.session_state['theme'] = 'Light'

# --- CSS THEMES ---
DARK_THEME = """
<style>
    /* Global Dark Mode */
    [data-testid="stAppViewContainer"], [data-testid="stHeader"], .main { background-color: #000000 !important; color: #fff !important; }
    [data-testid="stSidebar"] { background-color: #050505 !important; border-right: 1px solid #222 !important; }
    
    /* Text Visibility */
    h1, h2, h3, h4, h5, p, span, label, div { color: #ffffff !important; text-shadow: 0 0 1px rgba(255,255,255,0.3); }
    
    /* Input Fields */
    input, .stSelectbox div, .stNumberInput input, textarea { background-color: #111 !important; color: #fff !important; border: 1px solid #444 !important; }
    
    /* KPI Cards */
    .glow-income { border-top: 3px solid #00c853; background: #0a0a0a; padding: 15px; border-radius: 10px; box-shadow: 0 5px 15px rgba(0,200,83,0.15); text-align: center; }
    .glow-expenses { border-top: 3px solid #ff1744; background: #0a0a0a; padding: 15px; border-radius: 10px; box-shadow: 0 5px 15px rgba(255,23,68,0.15); text-align: center; }
    .glow-savings { border-top: 3px solid #2979ff; background: #0a0a0a; padding: 15px; border-radius: 10px; box-shadow: 0 5px 15px rgba(41,121,255,0.15); text-align: center; }
    .glow-balance { border-top: 3px solid #ffd600; background: #0a0a0a; padding: 15px; border-radius: 10px; box-shadow: 0 5px 15px rgba(255,214,0,0.15); text-align: center; }
    
    .kpi-title { font-size: 0.9rem; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; }
    .kpi-value { font-size: 2rem; font-weight: 800; color: #fff; }
</style>
"""
LIGHT_THEME = """<style>[data-testid="stAppViewContainer"]{background:#f8f9fa;color:#212529;}</style>"""

# --- HELPER FUNCTIONS ---
def format_inr(number):
    try:
        n = float(number); is_neg = n < 0; n = abs(n)
        s, *d = "{:.0f}".format(n).partition(".")
        r = ",".join([s[x-2:x] for x in range(-3, -len(s), -2)][::-1] + [s[-3:]])
        return "-" + "".join([r] + d) if is_neg else "".join([r] + d)
    except: return str(number)

def get_financial_year(date):
    if pd.isna(date): return "Unknown"
    return f"FY {date.year}-{str(date.year+1)[-2:]}" if date.month >= 4 else f"FY {date.year-1}-{str(date.year)[-2:]}"

# ==========================================
# 2. CLOUD CONNECTION ENGINE (FIXED)
# ==========================================
@st.cache_resource
def init_connection():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # CASE 1: Local Laptop (Uses file)
    if os.path.exists('credentials.json'):
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    
    # CASE 2: Streamlit Cloud (Uses Secrets)
    else:
        creds_dict = {
            "type": st.secrets["gcp_service_account"]["type"],
            "project_id": st.secrets["gcp_service_account"]["project_id"],
            "private_key_id": st.secrets["gcp_service_account"]["private_key_id"],
            "private_key": st.secrets["gcp_service_account"]["private_key"],
            "client_email": st.secrets["gcp_service_account"]["client_email"],
            "client_id": st.secrets["gcp_service_account"]["client_id"],
            "auth_uri": st.secrets["gcp_service_account"]["auth_uri"],
            "token_uri": st.secrets["gcp_service_account"]["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["gcp_service_account"]["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["gcp_service_account"]["client_x509_cert_url"]
        }
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        
    client = gspread.authorize(creds)
    return client

# ==========================================
# 3. DATA LOADER (FULL TABS)
# ==========================================
@st.cache_data(ttl=5)
def load_data():
    try:
        client = init_connection()
        sh = client.open("Finance Tracker")
    except Exception as e:
        st.error(f"🚨 Connection Error: {e}")
        st.stop()

    def get_df(worksheet_name):
        try:
            ws = sh.worksheet(worksheet_name)
            data = ws.get_all_records()
            return pd.DataFrame(data)
        except: return pd.DataFrame()

    # Load Main Data
    df = get_df('Budget Tracking')
    
    # Clean Data
    if not df.empty and 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date'])
        df['Year'] = df['Date'].dt.year 
        df['FY'] = df['Date'].apply(get_financial_year)
        df['Month'] = df['Date'].dt.month_name()
        df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0)
    
    # Load Budget
    budget_raw = get_df('Budget Planning')
    budget_melted = pd.DataFrame()
    if not budget_raw.empty:
        month_cols = ['April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December', 'January', 'February', 'March']
        valid_months = [m for m in month_cols if m in budget_raw.columns]
        if valid_months:
            budget_melted = budget_raw.melt(id_vars=['Category', 'Type'], value_vars=valid_months, var_name='Month', value_name='Amount')
            budget_melted['Amount'] = pd.to_numeric(budget_melted['Amount'], errors='coerce').fillna(0)

    # Return ALL tabs
    return df, budget_melted, budget_raw, get_df('Credit Cards'), get_df('Loans'), get_df('Physical Assets'), get_df('Splitwise'), get_df('Subscriptions'), get_df('Goals')

# Load data into variables
df, budget_df, budget_raw_df, cc_df, loan_df, assets_df, split_df, subs_df, goals_df = load_data()

# ==========================================
# 4. SIDEBAR & NAVIGATION
# ==========================================
st.sidebar.markdown("## 🎨 Theme")
if st.sidebar.radio("Mode", ["Light", "Dark"]) == "Dark":
    st.markdown(DARK_THEME, unsafe_allow_html=True)
else:
    st.markdown(LIGHT_THEME, unsafe_allow_html=True)

st.sidebar.markdown("---")
page = st.sidebar.radio("Navigation", ["Main Dashboard", "Budget Planner", "Credit Cards", "Transaction Ledger"])

# ==========================================
# 5. PAGE: MAIN DASHBOARD
# ==========================================
if page == "Main Dashboard":
    st.title("Cloud Command Center")
    
    if df.empty:
        st.info("👋 Welcome! Your database is connected but empty. Use the sidebar to add your first transaction.")
        ti, te, ts = 0, 0, 0
    else:
        ti = df[df['Type']=='Income']['Amount'].sum()
        te = df[df['Type']=='Expenses']['Amount'].sum()
        ts = df[df['Type']=='Savings']['Amount'].sum()

    # --- KPI CARDS ---
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(f"<div class='glow-income'><div class='kpi-title' style='color:#00e676'>Income</div><div class='kpi-value'>₹{format_inr(ti)}</div></div>", unsafe_allow_html=True)
    with c2: st.markdown(f"<div class='glow-expenses'><div class='kpi-title' style='color:#ff5252'>Expenses</div><div class='kpi-value'>₹{format_inr(te)}</div></div>", unsafe_allow_html=True)
    with c3: st.markdown(f"<div class='glow-savings'><div class='kpi-title' style='color:#448aff'>Savings</div><div class='kpi-value'>₹{format_inr(ts)}</div></div>", unsafe_allow_html=True)
    with c4: st.markdown(f"<div class='glow-balance'><div class='kpi-title' style='color:#ffd600'>Balance</div><div class='kpi-value'>₹{format_inr(ti-te-ts)}</div></div>", unsafe_allow_html=True)

    # --- MAIN CHARTS ---
    if not df.empty:
        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown("### 📈 Income vs Expense Trend")
            daily_trend = df.groupby(['Date', 'Type'])['Amount'].sum().reset_index()
            fig = px.bar(daily_trend, x='Date', y='Amount', color='Type', barmode='group', 
                         color_discrete_map={'Income': '#00e676', 'Expenses': '#ff5252', 'Savings': '#448aff'})
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="white" if st.session_state.theme == 'Dark' else "black")
            st.plotly_chart(fig, use_container_width=True)
            
        with col2:
            st.markdown("### 🍩 Expense Breakdown")
            exp_data = df[df['Type']=='Expenses'].groupby('Category')['Amount'].sum().reset_index()
            fig = px.pie(exp_data, values='Amount', names='Category', hole=0.5)
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', font_color="white" if st.session_state.theme == 'Dark' else "black")
            st.plotly_chart(fig, use_container_width=True)

    # --- QUICK ADD SIDEBAR ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("⚡ Quick Add")
    with st.sidebar.form("quick_add"):
        d = st.date_input("Date")
        t = st.selectbox("Type", ["Income", "Expenses", "Savings"])
        cats = df[df['Type']==t]['Category'].unique().tolist() if not df.empty else []
        c = st.selectbox("Category", cats + ["+ New..."])
        if c == "+ New...": c = st.text_input("Name")
        a = st.number_input("Amount", min_value=0.0)
        n = st.text_input("Notes")
        
        if st.form_submit_button("🚀 Upload to Cloud"):
            if a > 0:
                try:
                    client = init_connection()
                    sh = client.open("Finance Tracker")
                    ws = sh.worksheet('Budget Tracking')
                    row = [str(datetime.datetime.now().timestamp()), d.strftime("%Y-%m-%d"), t, c, a, n]
                    ws.append_row(row)
                    st.success("Saved!")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Cloud Error: {e}")

# ==========================================
# 6. PAGE: BUDGET PLANNER
# ==========================================
elif page == "Budget Planner":
    st.title("🎯 Budget vs Actuals")
    
    if budget_df.empty:
        st.warning("No Budget Plan found. Please add data to the 'Budget Planning' tab in Google Sheets.")
    else:
        # Filter Logic
        all_months = budget_df['Month'].unique()
        selected_month = st.selectbox("Select Month", all_months, index=len(all_months)-1)
        
        # Filter Budget & Actuals
        budget_filtered = budget_df[budget_df['Month'] == selected_month]
        actuals_filtered = df[(df['Month'] == selected_month) & (df['Type'] == 'Expenses')]
        actual_sums = actuals_filtered.groupby('Category')['Amount'].sum().reset_index()
        
        # Merge Data
        merged = pd.merge(budget_filtered, actual_sums, on='Category', how='left', suffixes=('_Budget', '_Actual'))
        merged['Amount_Actual'] = merged['Amount_Actual'].fillna(0)
        merged['Variance'] = merged['Amount_Budget'] - merged['Amount_Actual']
        
        # Display Grid
        st.dataframe(merged[['Category', 'Amount_Budget', 'Amount_Actual', 'Variance']], use_container_width=True)
        
        # Visualization
        fig = go.Figure(data=[
            go.Bar(name='Budget', x=merged['Category'], y=merged['Amount_Budget'], marker_color='#448aff'),
            go.Bar(name='Actual', x=merged['Category'], y=merged['Amount_Actual'], marker_color='#ff5252')
        ])
        fig.update_layout(barmode='group', title=f"Budget vs Actual ({selected_month})", 
                          paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', 
                          font_color="white" if st.session_state.theme == 'Dark' else "black")
        st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 7. PAGE: CREDIT CARDS
# ==========================================
elif page == "Credit Cards":
    st.title("💳 Credit Card Manager")
    
    if cc_df.empty:
        st.info("No Credit Card data found.")
    else:
        # Display Cards
        for index, row in cc_df.iterrows():
            st.markdown(f"### {row.get('Card Name', 'Unknown Card')}")
            col1, col2, col3 = st.columns(3)
            
            limit = float(str(row.get('Limit', 0)).replace(',',''))
            used = float(str(row.get('Used', 0)).replace(',',''))
            avail = limit - used
            util = (used / limit) * 100 if limit > 0 else 0
            
            with col1: st.metric("Limit", f"₹{format_inr(limit)}")
            with col2: st.metric("Used", f"₹{format_inr(used)}")
            with col3: st.metric("Available", f"₹{format_inr(avail)}")
            
            st.progress(util / 100)
            st.caption(f"Utilization: {util:.1f}%")
            st.markdown("---")

# ==========================================
# 8. PAGE: TRANSACTION LEDGER
# ==========================================
elif page == "Transaction Ledger":
    st.title("📝 Full Transaction History")
    
    # Filters
    col1, col2 = st.columns(2)
    with col1: search_txt = st.text_input("🔍 Search Transactions")
    with col2: type_filter = st.multiselect("Filter Type", df['Type'].unique(), default=df['Type'].unique())
    
    # Apply Filters
    filtered_df = df[df['Type'].isin(type_filter)]
    if search_txt:
        filtered_df = filtered_df[
            filtered_df['Category'].str.contains(search_txt, case=False) | 
            filtered_df['Details'].str.contains(search_txt, case=False)
        ]
        
    st.dataframe(filtered_df, use_container_width=True)
