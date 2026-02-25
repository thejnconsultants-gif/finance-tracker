import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import datetime
import calendar
import requests
import re
import io
import json
import os
import gspread
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
    [data-testid="stAppViewContainer"], [data-testid="stHeader"], .main { background-color: #000000 !important; color: #ffffff !important; }
    [data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child { background-color: #050505 !important; border-right: 1px solid #222 !important; }
    
    /* 2. TEXT GLOW */
    h1, h2, h3, h4, p, span, div, label { color: #ffffff !important; text-shadow: 0 0 1px rgba(255, 255, 255, 0.4); }
    
    /* 3. INPUTS & CARDS */
    .stTextInput input, .stNumberInput input, .stSelectbox div, .stDateInput input { background-color: #111 !important; color: #fff !important; border: 1px solid #333 !important; }
    
    /* 4. KPI CARDS (NEON) */
    .glow-income { border-top: 4px solid #00c853 !important; background: #0a0a0a; box-shadow: 0 4px 15px rgba(0, 200, 83, 0.2); border-radius: 10px; padding: 15px; text-align: center; }
    .glow-expenses { border-top: 4px solid #ff1744 !important; background: #0a0a0a; box-shadow: 0 4px 15px rgba(255, 23, 68, 0.2); border-radius: 10px; padding: 15px; text-align: center; }
    .glow-savings { border-top: 4px solid #2979ff !important; background: #0a0a0a; box-shadow: 0 4px 15px rgba(41, 121, 255, 0.2); border-radius: 10px; padding: 15px; text-align: center; }
    .glow-balance { border-top: 4px solid #ffd600 !important; background: #0a0a0a; box-shadow: 0 4px 15px rgba(255, 214, 0, 0.2); border-radius: 10px; padding: 15px; text-align: center; }
    
    .kpi-value { font-size: 2rem; font-weight: 800; margin: 0; }
    .kpi-title { font-size: 0.9rem; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; }
    
    /* 5. CHART BOXES */
    .chart-box { background: #0a0a0a; border: 1px solid #333; border-radius: 12px; padding: 20px; margin-bottom: 20px; }
</style>
"""

LIGHT_THEME = """<style>[data-testid="stAppViewContainer"]{background-color:#f8f9fa;color:#212529;}</style>"""

# ==========================================
# 2. ALGORITHMS & LOADERS
# ==========================================
FY_MONTHS = ['April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December', 'January', 'February', 'March']

def get_financial_year(date):
    if pd.isna(date): return "Unknown"
    y = date.year
    if date.month >= 4: return f"FY {y}-{str(y+1)[-2:]}"
    else: return f"FY {y-1}-{str(y)[-2:]}"

# ==========================================
# 3. DATA LOADER (CLOUD SMART EDITION)
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

@st.cache_data(ttl=5)
def load_data():
    client = init_connection()
    try:
        sh = client.open("Finance Tracker")
    except:
        st.error("🚨 Cloud Connection Failed: Could not find 'Finance Tracker' sheet.")
        st.stop()

    def get_df(worksheet_name):
        try:
            ws = sh.worksheet(worksheet_name)
            data = ws.get_all_records()
            # If sheet is empty or only has headers, return empty DF with correct columns
            if not data:
                return pd.DataFrame()
            return pd.DataFrame(data)
        except: return pd.DataFrame()

    df = get_df('Budget Tracking')
    
    # --- SAFETY: Handle Empty Sheets ---
    if df.empty or 'Date' not in df.columns:
        # Create a dummy DataFrame so the app doesn't crash on 'KeyError: FY'
        df = pd.DataFrame(columns=['Date', 'Type', 'Category', 'Amount', 'Details', 'FY', 'Month', 'Year', 'Bank'])
    else:
        # Standard processing
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date'])
        if not df.empty:
            df['Year'] = df['Date'].dt.year 
            df['FY'] = df['Date'].apply(get_financial_year)
            df['Month'] = df['Date'].dt.month_name()
            df['Amount'] = pd.to_numeric(df['Amount'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    
    budget_raw = get_df('Budget Planning')
    budget_melted = pd.DataFrame()
    if not budget_raw.empty:
        valid_months = [m for m in FY_MONTHS if m in budget_raw.columns]
        if valid_months:
            budget_melted = budget_raw.melt(id_vars=['Category', 'Type'], value_vars=valid_months, var_name='Month', value_name='Amount')
            budget_melted['Amount'] = pd.to_numeric(budget_melted['Amount'], errors='coerce').fillna(0)

    return df, budget_melted, budget_raw, get_df('Credit Cards'), get_df('Loans'), get_df('Physical Assets'), get_df('Splitwise'), get_df('Subscriptions'), get_df('Goals')

df, budget_df, budget_matrix_df, cc_df, loan_df, assets_df, split_df, subs_df, goals_df = load_data()

# Splitwise Users
split_users = set(["Partner"])
if not split_df.empty:
    split_users.update(split_df['Payer'].dropna().astype(str).unique())
    split_users.update(split_df['Debtor'].dropna().astype(str).unique())
if "Jaynik" in split_users: split_users.remove("Jaynik")
split_users = sorted(list(split_users))

# ==========================================
# 4. SIDEBAR: NAVIGATION
# ==========================================
st.sidebar.markdown("## 🎨 App Theme")
theme_choice = st.sidebar.radio("Select Mode:", ["Light", "Dark Mode"], horizontal=True)

if theme_choice == "Dark Mode":
    st.markdown(DARK_THEME, unsafe_allow_html=True); chart_text_color = "#e0e0e0"; root_node_color = "#333333"
else:
    st.markdown(LIGHT_THEME, unsafe_allow_html=True); chart_text_color = "#212529"; root_node_color = "#e9ecef"

current_user = "Jaynik"

st.sidebar.markdown("---")
st.sidebar.markdown("## 🧭 Navigation")
page = st.sidebar.radio("Go To Screen", ["🏠 Main Dashboard (I&E)", "💰 Budget Planner", "📈 Investment Tracker", "💳 Credit Cards", "🔄 Subscription Radar", "🤝 Splitwise / Settles", "⚖️ Net Worth & Goals", "📸 AI Bill Scanner", "📝 Transactions"])

st.sidebar.markdown("---")
st.sidebar.header("📅 Financial Year Filters")

# SAFETY FIX: Ensure 'FY' column exists before trying to access it
if 'FY' in df.columns and not df.empty:
    data_fys = df['FY'].dropna().unique().tolist()
    current_fy = get_financial_year(datetime.datetime.today())
    if current_fy not in data_fys: data_fys.append(current_fy)
    data_fys = sorted(list(set(data_fys)), reverse=True)
else:
    current_fy = get_financial_year(datetime.datetime.today())
    data_fys = [current_fy]

selected_fy = st.sidebar.selectbox("Select Financial Year", ["All Years"] + data_fys)
all_months = list(calendar.month_name)[1:]
selected_month = st.sidebar.selectbox("Select Month", ["All Months"] + all_months)

filtered_df = df.copy(); filtered_budget_df = budget_df.copy()

# Apply Filters (Safely)
if not filtered_df.empty and 'FY' in filtered_df.columns:
    if selected_fy != "All Years":
        filtered_df = filtered_df[filtered_df['FY'] == selected_fy]
    if selected_month != "All Months":
        filtered_df = filtered_df[filtered_df['Month'] == selected_month]

if not filtered_budget_df.empty and 'Month' in filtered_budget_df.columns:
    if selected_month != "All Months":
        filtered_budget_df = filtered_budget_df[filtered_budget_df['Month'] == selected_month]

def process_pie_data(target_df, threshold=0.05):
    if target_df.empty: return target_df
    agg_df = target_df.groupby('Category')['Amount'].sum().reset_index()
    total = agg_df['Amount'].sum()
    if total == 0: return agg_df
    agg_df['Percent'] = agg_df['Amount'] / total
    main_cats = agg_df[agg_df['Percent'] >= threshold].copy()
    small_cats = agg_df[agg_df['Percent'] < threshold]
    if not small_cats.empty:
        others_row = pd.DataFrame([{'Category': 'Others', 'Amount': small_cats['Amount'].sum(), 'Percent': small_cats['Percent'].sum()}])
        main_cats = pd.concat([main_cats, others_row], ignore_index=True)
    return main_cats

# ==========================================
# 5. PAGE LOGIC MANAGER
# ==========================================

if page == "🏠 Main Dashboard (I&E)":
    if current_user != "Household (Combined)":
        pending_alerts = split_df[(split_df['Debtor'] == current_user) & (split_df['Status'] == 'Pending')]
        if not pending_alerts.empty:
            total_owed_by_me = pending_alerts['Split Amount'].sum()
            st.markdown(f"<div class='alert-box'><b>🔔 You have pending Splitwise settlements!</b> You owe ₹{total_owed_by_me:,.0f} to other members.</div>", unsafe_allow_html=True)
            
    if filtered_df.empty: st.info("👋 Welcome! Your database is connected but empty. Use the sidebar to add your first transaction.")

    total_income = filtered_df[filtered_df['Type'] == 'Income']['Amount'].sum() if not filtered_df.empty else 0
    total_expenses = filtered_df[filtered_df['Type'] == 'Expenses']['Amount'].sum() if not filtered_df.empty else 0
    total_savings = filtered_df[filtered_df['Type'] == 'Savings']['Amount'].sum() if not filtered_df.empty else 0
    net_balance = total_income - total_expenses - total_savings

    col1, col2, col3, col4 = st.columns(4)
    with col1: st.markdown(f"<div class='glow-income'><div class='kpi-title'>TOTAL INCOME</div><div class='kpi-value' style='color:#00c853'>₹{total_income:,.0f}</div></div>", unsafe_allow_html=True)
    with col2: st.markdown(f"<div class='glow-expenses'><div class='kpi-title'>TOTAL EXPENSES</div><div class='kpi-value' style='color:#d50000'>₹{total_expenses:,.0f}</div></div>", unsafe_allow_html=True)
    with col3: st.markdown(f"<div class='glow-savings'><div class='kpi-title'>TOTAL SAVINGS</div><div class='kpi-value' style='color:#2962ff'>₹{total_savings:,.0f}</div></div>", unsafe_allow_html=True)
    with col4: st.markdown(f"<div class='glow-balance'><div class='kpi-title'>NET BALANCE</div><div class='kpi-value' style='color:#ffd600'>₹{net_balance:,.0f}</div></div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    col_pie1, col_pie2, col_pie3 = st.columns(3)
    
    # SAFE PIE CHARTS
    if not filtered_df.empty:
        with col_pie1:
            st.markdown("<div class='chart-box'><h4 style='text-align: center;'>💼 INCOME</h4>", unsafe_allow_html=True)
            income_df = filtered_df[(filtered_df['Type'] == 'Income') & (filtered_df['Amount'] > 0)]
            income_df = process_pie_data(income_df, 0.05)
            if not income_df.empty:
                fig_inc = px.pie(income_df, values='Amount', names='Category', hole=0.5, color_discrete_sequence=px.colors.sequential.Teal)
                fig_inc.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color=chart_text_color), margin=dict(t=0, b=20, l=0, r=0), showlegend=False)
                fig_inc.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_inc, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

        with col_pie2:
            st.markdown("<div class='chart-box'><h4 style='text-align: center;'>📉 EXPENSES</h4>", unsafe_allow_html=True)
            expense_df = filtered_df[(filtered_df['Type'] == 'Expenses') & (filtered_df['Amount'] > 0)]
            expense_df = process_pie_data(expense_df, 0.05)
            if not expense_df.empty:
                fig_exp = px.pie(expense_df, values='Amount', names='Category', hole=0.5, color_discrete_sequence=px.colors.sequential.Reds)
                fig_exp.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color=chart_text_color), margin=dict(t=0, b=20, l=0, r=0), showlegend=False)
                fig_exp.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_exp, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

        with col_pie3:
            st.markdown("<div class='chart-box'><h4 style='text-align: center;'>🏦 SAVINGS</h4>", unsafe_allow_html=True)
            savings_df = filtered_df[(filtered_df['Type'] == 'Savings') & (filtered_df['Amount'] > 0)]
            savings_df = process_pie_data(savings_df, 0.05)
            if not savings_df.empty:
                fig_sav = px.pie(savings_df, values='Amount', names='Category', hole=0.5, color_discrete_sequence=px.colors.sequential.Blues)
                fig_sav.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color=chart_text_color), margin=dict(t=0, b=20, l=0, r=0), showlegend=False)
                fig_sav.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_sav, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

elif page == "💰 Budget Planner":
    st.markdown("<h2>💰 Budget Planner</h2>", unsafe_allow_html=True)
    tab_input, tab_month_view, tab_full_matrix = st.tabs(["📝 Input & Update", "🗓️ Monthly View", "📊 Full Matrix"])
    
    with tab_input:
        st.write("### Set a Budget Goal")
        c1, c2 = st.columns(2)
        with c1:
            b_type = st.selectbox("Type", ["Income", "Expenses", "Savings"])
            # SAFETY: Handle empty df
            existing_cats = []
            if not df.empty and 'Type' in df.columns:
                 existing_cats = df[df['Type'] == b_type]['Category'].unique().tolist()
            b_cat = st.selectbox("Category", existing_cats + ["+ Add New..."])
            if b_cat == "+ Add New...": b_cat = st.text_input("New Category Name")
        with c2:
            b_val = st.number_input("Budget Amount (₹)", min_value=0.0, step=500.0)
            b_freq = st.radio("Budget Frequency", ["Entire Year (Apr-Mar)", "Specific Month"], horizontal=True)
            b_month = st.selectbox("Select Month", FY_MONTHS)
        
        if st.button("💾 Save Budget Goal"):
            if b_cat and b_val >= 0:
                try:
                    client = init_connection(); sh = client.open("Finance Tracker")
                    try: ws = sh.worksheet('Budget Planning')
                    except: ws = sh.add_worksheet('Budget Planning', 100, 20); ws.append_row(['Type', 'Category'] + FY_MONTHS)
                    
                    all_data = ws.get_all_values()
                    headers = all_data[0]
                    row_idx = -1
                    for idx, row in enumerate(all_data):
                        if idx == 0: continue
                        if len(row) > 1 and row[0] == b_type and row[1] == b_cat:
                            row_idx = idx + 1; break
                    
                    if row_idx == -1:
                        new_row = [b_type, b_cat] + [0]*12
                        ws.append_row(new_row)
                        row_idx = len(all_data) + 1
                    
                    if b_freq == "Entire Year (Apr-Mar)":
                        cell_list = []
                        for c_i in range(3, 15): cell_list.append(gspread.Cell(row_idx, c_i, b_val))
                        ws.update_cells(cell_list)
                    else:
                        col_idx = headers.index(b_month) + 1
                        ws.update_cell(row_idx, col_idx, b_val)
                    
                    st.success("✅ Budget Updated!"); st.cache_data.clear(); st.rerun()
                except Exception as e: st.error(f"Cloud Error: {e}")

    with tab_month_view:
        view_month = st.selectbox("Select Month to View", FY_MONTHS)
        if not budget_df.empty:
            monthly_data = budget_df[budget_df['Month'] == view_month]
            monthly_data = monthly_data[monthly_data['Amount'] > 0]
            st.dataframe(monthly_data, use_container_width=True, hide_index=True)

    with tab_full_matrix:
        if not budget_matrix_df.empty: st.dataframe(budget_matrix_df, use_container_width=True)

elif page == "📈 Investment Tracker":
    st.title("📈 Investment Portfolio")
    # Investment Read-Only Logic
    summary_df = pd.DataFrame()
    if not df.empty and 'Details' in df.columns:
        t_col = df['Details'].astype(str).str.extract(r'\[Ticker:\s*([^,\]]+)')[0]
        q_col = df['Details'].astype(str).str.extract(r'Qty:\s*([0-9.-]+)')[0]
        c_col = df['Details'].astype(str).str.extract(r'Class:\s*([^,\]]+)')[0]
        extracted = pd.DataFrame({'Ticker': t_col, 'Qty': q_col, 'Asset_Class': c_col})
        portfolio_data = pd.concat([df[['Date', 'Category', 'Amount']], extracted], axis=1).dropna(subset=['Ticker'])
        portfolio_data['Qty'] = pd.to_numeric(portfolio_data['Qty'], errors='coerce').fillna(0)
        
        if not portfolio_data.empty:
            summary_df = portfolio_data.groupby('Ticker')['Qty'].sum().reset_index()
            # Basic display for now
            st.dataframe(portfolio_data, use_container_width=True)
            
    # Write Logic for Sales
    with st.expander("📉 Sell an Asset"):
        sell_ticker = st.text_input("Ticker Symbol")
        sell_qty = st.number_input("Quantity", min_value=0.0)
        sell_price = st.number_input("Price", min_value=0.0)
        
        if st.button("Execute Sale"):
            try:
                client = init_connection(); sh = client.open("Finance Tracker"); ws = sh.worksheet('Budget Tracking')
                # Add Income entry
                ws.append_row([str(datetime.datetime.now().timestamp()), str(datetime.date.today()), "Income", "Investment Payout", sell_qty * sell_price, f"[Ticker: {sell_ticker}, Qty: {-sell_qty}] Sold Asset"])
                st.success("Sale Recorded!"); st.cache_data.clear(); st.rerun()
            except Exception as e: st.error(f"Error: {e}")

elif page == "💳 Credit Cards":
    st.markdown("<h2>💳 Credit Health</h2>", unsafe_allow_html=True)
    with st.expander("⚙️ Manage Wallet"):
        if cc_df.empty: cc_df = pd.DataFrame(columns=['Card Name', 'Limit', 'Statement Date'])
        edited_cc = st.data_editor(cc_df, num_rows="dynamic")
        if st.button("💾 Save Wallet"):
            try:
                client = init_connection(); sh = client.open("Finance Tracker")
                ws = sh.worksheet('Credit Cards')
                ws.clear()
                ws.update([edited_cc.columns.values.tolist()] + edited_cc.values.tolist())
                st.success("Updated!"); st.cache_data.clear(); st.rerun()
            except Exception as e: st.error(f"Error: {e}")

elif page == "🔄 Subscription Radar":
    st.title("🔄 Subscription Radar")
    with st.expander("⚙️ Manage Subscriptions"):
        if subs_df.empty: subs_df = pd.DataFrame(columns=['Service Name', 'Category', 'Amount', 'Next Due Date'])
        edited_subs = st.data_editor(subs_df, num_rows="dynamic")
        if st.button("💾 Save Subs"):
            try:
                client = init_connection(); sh = client.open("Finance Tracker")
                ws = sh.worksheet('Subscriptions')
                ws.clear()
                edited_subs['Next Due Date'] = edited_subs['Next Due Date'].astype(str)
                ws.update([edited_subs.columns.values.tolist()] + edited_subs.values.tolist())
                st.success("Updated!"); st.cache_data.clear(); st.rerun()
            except Exception as e: st.error(f"Error: {e}")

elif page == "🤝 Splitwise / Settles":
    st.title("🤝 Splitwise")
    with st.form("split_form"):
        sp_desc = st.text_input("Description")
        sp_amt = st.number_input("Amount", min_value=0.0)
        sp_payer = st.selectbox("Payer", ["Jaynik", "Partner"])
        if st.form_submit_button("Add Split"):
            try:
                client = init_connection(); sh = client.open("Finance Tracker")
                ws = sh.worksheet('Splitwise')
                ws.append_row([str(datetime.datetime.now().timestamp()), str(datetime.date.today()), sp_payer, "Partner" if sp_payer=="Jaynik" else "Jaynik", sp_amt, sp_amt/2, sp_desc, "Pending"])
                st.success("Added!"); st.cache_data.clear(); st.rerun()
            except Exception as e: st.error(f"Error: {e}")
            
    st.dataframe(split_df, use_container_width=True)

elif page == "⚖️ Net Worth & Goals":
    st.title("⚖️ Net Worth")
    with st.expander("➕ Add Goal"):
        g_name = st.text_input("Goal Name")
        g_target = st.number_input("Target Amount")
        if st.button("Save Goal"):
            try:
                client = init_connection(); sh = client.open("Finance Tracker")
                ws = sh.worksheet('Goals')
                ws.append_row([g_name, g_target, str(datetime.date.today()), 5, "Active"])
                st.success("Saved!"); st.cache_data.clear(); st.rerun()
            except Exception as e: st.error(f"Error: {e}")
            
    st.dataframe(goals_df, use_container_width=True)

elif page == "📝 Transactions":
    st.title("📝 Ledger")
    st.dataframe(df, use_container_width=True)

# ==========================================
# 7. CONDITIONAL DATA ENTRY FORM (SIDEBAR)
# ==========================================
if page == "🏠 Main Dashboard (I&E)":
    st.sidebar.markdown("---")
    st.sidebar.subheader("➕ Quick Add Transaction")
    new_date = st.sidebar.date_input("Date", datetime.datetime.today())
    new_type = st.sidebar.selectbox("Type", ["Income", "Expenses", "Savings"])
    new_cat = st.sidebar.text_input("Category")
    new_amt = st.sidebar.number_input("Amount", min_value=0.0)
    new_note = st.sidebar.text_input("Notes")
    
    if st.sidebar.button("💾 Save to Cloud"):
        if new_amt > 0:
            try:
                client = init_connection()
                sh = client.open("Finance Tracker")
                ws = sh.worksheet('Budget Tracking')
                # Check if headers exist, if not, create them
                if ws.row_count == 0 or not ws.row_values(1):
                    ws.append_row(['ID', 'Date', 'Type', 'Category', 'Amount', 'Details'])
                ws.append_row([str(datetime.datetime.now().timestamp()), str(new_date), new_type, new_cat, new_amt, new_note])
                st.sidebar.success("Saved!")
                st.cache_data.clear()
                st.rerun()
            except Exception as e: st.sidebar.error(f"Error: {e}")
