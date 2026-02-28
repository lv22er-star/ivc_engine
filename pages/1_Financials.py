# pages/1_Financials.py
# Financial Statement Viewer (No Scroll Display + Shared Ticker)

import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(layout="wide")

st.title("Financial Statements")

# -----------------------------------
# SHARE TICKER FROM DASHBOARD
# -----------------------------------

if "shared_ticker" not in st.session_state:
    st.session_state.shared_ticker = "NVDA"

ticker = st.text_input("Ticker", st.session_state.shared_ticker)

st.session_state.shared_ticker = ticker

# -----------------------------------
# VIEW MODE
# -----------------------------------

view_type = st.radio(
    "Select View",
    ["Annual", "Quarterly"],
    horizontal=True
)

# -----------------------------------
# SIDEBAR NAVIGATION
# -----------------------------------

st.sidebar.title("Statements")

statement_choice = st.sidebar.radio(
    "Select Statement",
    ["Income Statement", "Balance Sheet", "Cash Flow"]
)

# -----------------------------------
# FORMAT FUNCTION
# -----------------------------------

def format_financial(df):

    if df is None or df.empty:
        return None

    # Reverse columns so most recent is first
    df = df.iloc[:, ::-1]

    # Convert to billions
    df = df / 1_000_000_000

    # Round
    df = df.round(2)

    return df

# -----------------------------------
# LOAD DATA
# -----------------------------------

if ticker:

    t = yf.Ticker(ticker)

    if view_type == "Annual":
        income = t.financials
        balance = t.balance_sheet
        cashflow = t.cashflow
    else:
        income = t.quarterly_financials
        balance = t.quarterly_balance_sheet
        cashflow = t.quarterly_cashflow

    # -----------------------------------
    # DISPLAY FULL TABLE (NO SCROLL WINDOW)
    # -----------------------------------

    if statement_choice == "Income Statement":
        st.header("Income Statement")
        formatted = format_financial(income)

    elif statement_choice == "Balance Sheet":
        st.header("Balance Sheet")
        formatted = format_financial(balance)

    elif statement_choice == "Cash Flow":
        st.header("Cash Flow Statement")
        formatted = format_financial(cashflow)

    if formatted is not None:
        html_table = formatted.to_html(classes="financial-table", border=0)
        st.markdown(html_table, unsafe_allow_html=True)
    else:
        st.warning("Statement not available.")

# -----------------------------------
# BACK NAVIGATION
# -----------------------------------

st.markdown("---")

if st.button("Back to Dashboard"):
    st.switch_page("app.py")