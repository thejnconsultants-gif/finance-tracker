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

# --- OPTIONAL IMPORTS (Safety Check) ---
try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False

try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

try:
    import pdfplumber
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

# ==========================================
# 1. PAGE SETUP & THEME ENGINE
# ==========================================
st.set_page_config(page_title="Jaynik's Finance Dashboard", page_icon="💎", layout="wide")

if 'theme' not in st.session_state:
    st.session_state['theme'] = 'Light'

# --- CSS THEMES ---
DARK_THEME = """
<style>
    /* 1. GLOBAL BACKGROUNDS */
    [data-testid="stAppViewContainer"], [data-testid="stHeader"], .main {
        background-color: #000000 !important; color: #ffffff !important;
    }
    [data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child {
        background-color: #050505 !important; border-right: 1px solid #222 !important;
    }
    
    /* 2. TEXT GLOW */
    h1, h2, h3, h4, p, span, div, label { color: #ffffff !important; text-shadow: 0 0 1px rgba(255, 255, 255, 0.4); }
    
    /* 3. INPUTS & CARDS */
    .stTextInput input, .stNumberInput input, .stSelectbox div, .stDateInput input {
        background-color: #111 !important; color: #fff !important; border: 1px solid #333 !important;
    }
    
    /* 4. KPI CARDS (NEON) */
    .glow-income { border-top: 4px solid #00c853 !important; background: #0a0a0a; box-shadow: 0 4px 15px rgba(0, 200, 83, 0.2); border-radius: 10px; padding: 15px; text-align: center; }
    .glow-expenses { border-top: 4px solid #ff1744 !important; background: #0a0a0a; box-shadow: 0 4px 15px rgba(255, 23, 68, 0.2); border-radius: 10px; padding: 15px; text-align: center; }
    .glow-savings { border-top: 4px solid #2979ff !important; background: #0a0a0a; box-shadow: 0 4px 15px rgba(41, 121, 255, 0.2); border-radius: 10px; padding: 15px; text-align: center; }
    .glow-balance { border-top: 4px solid #ffd600 !important; background: #0a0a0a; box-shadow: 0 4px 15px rgba(255, 214, 0, 0.2); border-radius: 10px; padding: 15px; text-align: center; }
    
    .kpi-value { font-size: 2rem; font-weight: 800; margin: 0; }
    .kpi-title { font-size: 0.9rem; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; }
</style>
"""

LIGHT_THEME = """<style>[data-testid="stAppViewContainer"]{background-color:#f8f9fa;color:#212529;}</style>"""

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
    
    # CASE 1: Local Laptop
    if os.path.exists('credentials.json'):
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    
    # CASE 2: Streamlit Cloud
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
# 3. DATA LOADER (FULL 9 TABS)
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

    # 1. Main Data
    df = get_df('Budget Tracking')
    if not df.empty and 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date'])
        df['Year'] = df['Date'].dt.year 
        df['FY'] = df['Date'].apply(get_financial_year)
        df['Month'] = df['Date'].dt.month_name()
        df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0)
    
    # 2. Budget
    budget_raw = get_df('Budget Planning')
    budget_melted = pd.DataFrame()
    if not budget_raw.empty:
        month_cols = ['April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December', 'January', 'February', 'March']
        valid_months = [m for m in month_cols if m in budget_raw.columns]
        if valid_months:
            budget_melted = budget_raw.melt(id_vars=['Category', 'Type'], value_vars=valid_months, var_name='Month', value_name='Amount')
            budget_melted['Amount'] = pd.to_numeric(budget_melted['Amount'], errors='coerce').fillna(0)

    # Return ALL DataFrames
    return df, budget_melted, budget_raw, get_df('Credit Cards'), get_df('Loans'), get_df('Physical Assets'), get_df('Splitwise'), get_df('Subscriptions'), get_df('Goals'), get_df('Investments')

# Load Data
df, budget_df, budget_raw_df, cc_df, loan_df, assets_df, split_df, subs_df, goals_df, invest_df = load_data()

# ==========================================
# 4. SIDEBAR & NAVIGATION (THE "PIC 1" LOOK)
# ==========================================
st.sidebar.title("🎨 App Theme")
mode = st.sidebar.radio("Select Mode:", ["Light", "Dark Mode"])
if mode == "Dark Mode":
    st.session_state['theme'] = 'Dark'
    st.markdown(DARK_THEME, unsafe_allow_html=True)
else:
    st.session_state['theme'] = 'Light'
    st.markdown(LIGHT_THEME, unsafe_allow_html=True)

st.sidebar.markdown("---")
st.sidebar.title("🧭 Navigation")

# The Full 9-Item Menu
page = st.sidebar.radio("Go To Screen", [
    "🏠 Main Dashboard (I&E)",
    "💰 Budget Planner",
    "📈 Investment Tracker",
    "💳 Credit Cards",
    "🔄 Subscription Radar",
    "🤝 Splitwise / Settles",
    "⚖️ Net Worth & Goals",
    "📷 AI Bill Scanner",
    "📝 Transactions"
])

# ==========================================
# 5. PAGE: MAIN DASHBOARD
# ==========================================
if "Main Dashboard" in page:
    st.title("Cloud Command Center")
    
    if df.empty:
        st.info("Your database is connected but empty.")
        ti, te, ts = 0, 0, 0
    else:
        ti = df[df['Type']=='Income']['Amount'].sum()
        te = df[df['Type']=='Expenses']['Amount'].sum()
        ts = df[df['Type']=='Savings']['Amount'].sum()

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(f"<div class='glow-income'><div class='kpi-title' style='color:#00e676'>Income</div><div class='kpi-value'>₹{format_inr(ti)}</div></div>", unsafe_allow_html=True)
    with c2: st.markdown(f"<div class='glow-expenses'><div class='kpi-title' style='color:#ff5252'>Expenses</div><div class='kpi-value'>₹{format_inr(te)}</div></div>", unsafe_allow_html=True)
    with c3: st.markdown(f"<div class='glow-savings'><div class='kpi-title' style='color:#448aff'>Savings</div><div class='kpi-value'>₹{format_inr(ts)}</div></div>", unsafe_allow_html=True)
    with c4: st.markdown(f"<div class='glow-balance'><div class='kpi-title' style='color:#ffd600'>Balance</div><div class='kpi-value'>₹{format_inr(ti-te-ts)}</div></div>", unsafe_allow_html=True)

    if not df.empty:
        col1, col2 = st.columns([2,1])
        with col1:
            st.markdown("### 📈 Trends")
            daily = df.groupby(['Date', 'Type'])['Amount'].sum().reset_index()
            fig = px.bar(daily, x='Date', y='Amount', color='Type', barmode='group', color_discrete_map={'Income':'#00e676', 'Expenses':'#ff5252', 'Savings':'#448aff'})
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', font_color="white" if st.session_state.theme == 'Dark' else "black")
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            st.markdown("### 🍩 Breakdown")
            exp = df[df['Type']=='Expenses'].groupby('Category')['Amount'].sum().reset_index()
            fig = px.pie(exp, values='Amount', names='Category', hole=0.5)
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', font_color="white" if st.session_state.theme == 'Dark' else "black")
            st.plotly_chart(fig, use_container_width=True)

    # QUICK ADD
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
        if st.form_submit_button("🚀 Save"):
            try:
                client = init_connection()
                sh = client.open("Finance Tracker")
                ws = sh.worksheet('Budget Tracking')
                ws.append_row([str(datetime.datetime.now().timestamp()), d.strftime("%Y-%m-%d"), t, c, a, n])
                st.success("Saved!"); st.cache_data.clear(); st.rerun()
            except Exception as e: st.error(f"Error: {e}")

# ==========================================
# 6. PAGE: BUDGET PLANNER
# ==========================================
elif "Budget Planner" in page:
    st.title("🎯 Budget Control")
    if budget_df.empty:
        st.warning("Please setup 'Budget Planning' tab in Sheets.")
    else:
        month = st.selectbox("Select Month", budget_df['Month'].unique(), index=len(budget_df['Month'].unique())-1)
        
        bud_fil = budget_df[budget_df['Month'] == month]
        act_fil = df[(df['Month'] == month) & (df['Type'] == 'Expenses')]
        act_sum = act_fil.groupby('Category')['Amount'].sum().reset_index()
        
        merged = pd.merge(bud_fil, act_sum, on='Category', how='left', suffixes=('_Budget', '_Actual'))
        merged['Amount_Actual'] = merged['Amount_Actual'].fillna(0)
        merged['Variance'] = merged['Amount_Budget'] - merged['Amount_Actual']
        
        st.dataframe(merged[['Category', 'Amount_Budget', 'Amount_Actual', 'Variance']], use_container_width=True)
        
        fig = go.Figure(data=[
            go.Bar(name='Budget', x=merged['Category'], y=merged['Amount_Budget'], marker_color='#448aff'),
            go.Bar(name='Actual', x=merged['Category'], y=merged['Amount_Actual'], marker_color='#ff5252')
        ])
        fig.update_layout(barmode='group', paper_bgcolor='rgba(0,0,0,0)', font_color="white" if st.session_state.theme == 'Dark' else "black")
        st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 7. PAGE: INVESTMENT TRACKER (RESTORED)
# ==========================================
elif "Investment Tracker" in page:
    st.title("📈 Investment Portfolio")
    
    if not HAS_YFINANCE:
        st.error("⚠️ Library 'yfinance' is missing. Please add it to requirements.txt")
    elif invest_df.empty:
        st.info("Add stocks to 'Investments' tab in Sheets (Ticker, Buy Price, Quantity)")
    else:
        total_inv = 0
        current_val = 0
        
        live_data = []
        for index, row in invest_df.iterrows():
            ticker = row.get('Ticker')
            qty = float(row.get('Quantity', 0))
            buy_price = float(row.get('Buy Price', 0))
            
            try:
                stock = yf.Ticker(ticker)
                curr_price = stock.history(period="1d")['Close'].iloc[-1]
            except:
                curr_price = buy_price # Fallback
                
            invested = qty * buy_price
            current = qty * curr_price
            
            total_inv += invested
            current_val += current
            
            live_data.append({
                "Ticker": ticker, "Qty": qty, "Buy Avg": buy_price, 
                "CMP": round(curr_price, 2), "Invested": invested, "Current": current,
                "P&L": current - invested, "P&L %": ((current-invested)/invested)*100 if invested > 0 else 0
            })
            
        inv_final = pd.DataFrame(live_data)
        
        c1, c2, c3 = st.columns(3)
        with c1: st.metric("Total Invested", f"₹{format_inr(total_inv)}")
        with c2: st.metric("Current Value", f"₹{format_inr(current_val)}", delta=f"{format_inr(current_val-total_inv)}")
        with c3: st.metric("Returns", f"{((current_val-total_inv)/total_inv)*100:.2f}%")
        
        st.dataframe(inv_final.style.format({"P&L %": "{:.2f}%", "CMP": "₹{:.2f}"}), use_container_width=True)

# ==========================================
# 8. PAGE: CREDIT CARDS
# ==========================================
elif "Credit Cards" in page:
    st.title("💳 Credit Card Manager")
    if cc_df.empty: st.info("No Data in 'Credit Cards' tab.")
    else:
        for i, row in cc_df.iterrows():
            st.markdown(f"### {row.get('Card Name')}")
            l = float(str(row.get('Limit',0)).replace(',',''))
            u = float(str(row.get('Used',0)).replace(',',''))
            st.progress((u/l) if l > 0 else 0)
            c1, c2 = st.columns(2)
            c1.metric("Used", f"₹{format_inr(u)}")
            c2.metric("Available", f"₹{format_inr(l-u)}")
            st.markdown("---")

# ==========================================
# 9. PAGE: SUBSCRIPTION RADAR
# ==========================================
elif "Subscription Radar" in page:
    st.title("🔄 Subscription Radar")
    if subs_df.empty: st.info("No Data in 'Subscriptions' tab.")
    else:
        subs_df['Cost'] = pd.to_numeric(subs_df['Cost'], errors='coerce').fillna(0)
        monthly = subs_df[subs_df['Frequency']=='Monthly']['Cost'].sum()
        yearly = subs_df[subs_df['Frequency']=='Yearly']['Cost'].sum()
        total_monthly_impact = monthly + (yearly/12)
        
        c1, c2 = st.columns(2)
        c1.metric("Monthly Burn", f"₹{format_inr(total_monthly_impact)}")
        c2.metric("Active Subs", len(subs_df))
        
        st.dataframe(subs_df, use_container_width=True)

# ==========================================
# 10. PAGE: SPLITWISE
# ==========================================
elif "Splitwise" in page:
    st.title("🤝 Splitwise / Settlements")
    if split_df.empty: st.info("No Data in 'Splitwise' tab.")
    else:
        split_df['Amount'] = pd.to_numeric(split_df['Amount'], errors='coerce').fillna(0)
        
        # Calculate Net Balances
        balances = {}
        for i, row in split_df.iterrows():
            payer = row['Payer']
            debtor = row['Debtor']
            amt = row['Amount']
            
            balances[payer] = balances.get(payer, 0) + amt
            balances[debtor] = balances.get(debtor, 0) - amt
            
        st.markdown("### 💰 Net Balances")
        for person, bal in balances.items():
            if bal > 0: st.success(f"**{person}** gets back ₹{format_inr(bal)}")
            elif bal < 0: st.error(f"**{person}** owes ₹{format_inr(abs(bal))}")
            
        st.markdown("### 📜 Ledger")
        st.dataframe(split_df, use_container_width=True)

# ==========================================
# 11. PAGE: NET WORTH & GOALS
# ==========================================
elif "Net Worth" in page:
    st.title("⚖️ Net Worth & Goals")
    
    # Assets
    assets_df['Value'] = pd.to_numeric(assets_df['Value'], errors='coerce').fillna(0)
    loan_df['Outstanding'] = pd.to_numeric(loan_df['Outstanding'], errors='coerce').fillna(0)
    
    total_assets = assets_df['Value'].sum()
    total_liab = loan_df['Outstanding'].sum()
    
    # Add savings/investments to assets
    savings_balance = df[df['Type']=='Income']['Amount'].sum() - df[df['Type']=='Expenses']['Amount'].sum()
    total_assets += savings_balance
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Assets", f"₹{format_inr(total_assets)}")
    col2.metric("Total Liabilities", f"₹{format_inr(total_liab)}")
    col3.metric("Net Worth", f"₹{format_inr(total_assets - total_liab)}")
    
    st.markdown("### 🎯 Financial Goals")
    if not goals_df.empty:
        goals_df['Target Amount'] = pd.to_numeric(goals_df['Target Amount'], errors='coerce')
        goals_df['Saved Amount'] = pd.to_numeric(goals_df['Saved Amount'], errors='coerce')
        
        for i, row in goals_df.iterrows():
            st.markdown(f"**{row['Goal Name']}**")
            prog = (row['Saved Amount'] / row['Target Amount']) if row['Target Amount'] > 0 else 0
            st.progress(min(prog, 1.0))
            st.caption(f"₹{format_inr(row['Saved Amount'])} / ₹{format_inr(row['Target Amount'])}")

# ==========================================
# 12. PAGE: AI BILL SCANNER
# ==========================================
elif "AI Bill Scanner" in page:
    st.title("📷 AI Bill Scanner")
    st.info("Upload a bill image/PDF to extract details automatically.")
    
    uploaded_file = st.file_uploader("Upload Bill", type=['png', 'jpg', 'jpeg', 'pdf'])
    
    if uploaded_file and st.button("🔍 Scan with AI"):
        if not HAS_GENAI:
            st.error("Library 'google-generativeai' is missing.")
        else:
            st.warning("⚠️ You need to add your Gemini API Key in secrets to make this work.")
            # Placeholder for actual AI logic (requires API Key)
            st.write("Simulated Extraction:")
            st.json({"Date": "2024-02-25", "Total": 1250, "Category": "Dining"})

# ==========================================
# 13. PAGE: TRANSACTIONS
# ==========================================
elif "Transactions" in page:
    st.title("📝 Ledger")
    st.dataframe(df, use_container_width=True)
