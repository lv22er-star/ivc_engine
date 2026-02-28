# app.py
# Buffett & Lynch Core Metrics + Stock Diagnostic Dashboard
# Fully Hard-Coded | Uniform Cells | No Sidebar

import streamlit as st
import yfinance as yf
import math

st.set_page_config(layout="wide")

# ----------------------------
# GLOBAL STYLE
# ----------------------------

st.markdown("""
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

table {
    width: 100%;
    table-layout: fixed;
    border-collapse: collapse;
}

th, td {
    padding: 6px;
    text-align: center;
    vertical-align: middle;
}

th {
    font-weight: 600;
}

.col-metric { width: 18%; }
.col-formula { width: 28%; }
.col-threshold { width: 10%; }
.col-value { width: 12%; }
.col-why { width: 32%; }

/* Tighter buttons */
div.stButton > button {
    margin-right: 2px;
    padding: 4px 10px;
}

/* Remove extra column spacing */
div[data-testid="column"] {
    padding-left: 4px !important;
    padding-right: 4px !important;
}
</style>
""", unsafe_allow_html=True)

# ----------------------------
# UTILITIES
# ----------------------------

def safe_div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b

def fmt_num(x):
    if x is None or (isinstance(x,float) and math.isnan(x)):
        return "N/A"
    return f"{x:,.2f}"

def fmt_pct(x):
    if x is None or (isinstance(x,float) and math.isnan(x)):
        return "N/A"
    return f"{x*100:.2f}%"

def color_value(val, passed):
    if val == "N/A":
        return f'<span style="color:#9aa0a6;">{val}</span>'
    if passed:
        return f'<span style="color:#1f7a3f;font-weight:600;">{val}</span>'
    return f'<span style="color:#c0392b;font-weight:600;">{val}</span>'

def find_value(df, labels):
    if df is None:
        return None
    for label in labels:
        if label in df.index:
            return df.loc[label].iloc[0]
    return None
# ----------------------------
# STATE
# ----------------------------

if "run" not in st.session_state:
    st.session_state.run = False

if "financials" not in st.session_state:
    st.session_state.financials = False

# 👇 ADD THIS LINE RIGHT HERE
if "financial_view" not in st.session_state:
    st.session_state.financial_view = None

# ----------------------------
# METRIC ENGINE (IMPROVED ACCURACY)
# ----------------------------

def compute_metrics(ticker):

    t = yf.Ticker(ticker)

    income = t.financials
    balance = t.balance_sheet
    cashflow = t.cashflow

    # ----------------------------
    # INCOME STATEMENT
    # ----------------------------

    net_income = find_value(income, [
        "Net Income",
        "Net Income Common Stockholders",
        "Net Income From Continuing Operations"
    ])

    revenue = find_value(income, [
        "Total Revenue",
        "Revenue"
    ])

    op_income = find_value(income, [
        "Operating Income",
        "EBIT"
    ])

    interest = find_value(income, [
        "Interest Expense",
        "Interest Expense Non Operating"
    ])

    # ----------------------------
    # BALANCE SHEET
    # ----------------------------

    equity = find_value(balance, [
        "Total Stockholder Equity",
        "Stockholders Equity"
    ])

    total_debt = find_value(balance, [
        "Total Debt"
    ])

    long_debt = find_value(balance, [
        "Long Term Debt"
    ])

    short_debt = find_value(balance, [
        "Short Long Term Debt",
        "Short Term Debt"
    ])

    # Build debt if Total Debt missing
    debt = total_debt
    if debt is None:
        debt = (long_debt or 0) + (short_debt or 0)

    current_assets = find_value(balance, [
        "Total Current Assets"
    ])

    current_liab = find_value(balance, [
        "Total Current Liabilities"
    ])

    # ----------------------------
    # CASH FLOW
    # ----------------------------

    depreciation = find_value(cashflow, [
        "Depreciation",
        "Depreciation & Amortization"
    ])

    capex = find_value(cashflow, [
        "Capital Expenditures"
    ])

    free_cash_flow = find_value(cashflow, [
        "Free Cash Flow"
    ])

    if capex is not None:
        capex = abs(capex)

    # Build FCF if missing
    if free_cash_flow is None and net_income is not None:
        free_cash_flow = (net_income or 0) + (depreciation or 0) - (capex or 0)

    # ----------------------------
    # RATIOS
    # ----------------------------

    debt_equity = safe_div(debt, equity)

    current_ratio = safe_div(current_assets, current_liab)

    interest_coverage = None
    if op_income is not None and interest not in (None, 0):
        interest_coverage = safe_div(op_income, abs(interest))

    fcf_conversion = safe_div(free_cash_flow, net_income)

    fcf_margin = safe_div(free_cash_flow, revenue)

    roe = safe_div(net_income, equity)

    # ----------------------------
    # ROIC (Cleaner)
    # ----------------------------

    invested_capital = None
    if debt is not None and equity is not None:
        invested_capital = debt + equity

    roic = None
    if op_income is not None and invested_capital not in (None, 0):
        tax_rate = 0.21  # conservative default
        nopat = op_income * (1 - tax_rate)
        roic = safe_div(nopat, invested_capital)

    return {
        "debt_equity": debt_equity,
        "current_ratio": current_ratio,
        "interest_coverage": interest_coverage,
        "fcf_conversion": fcf_conversion,
        "fcf_margin": fcf_margin,
        "roe": roe,
        "roic": roic,
    }

# ----------------------------
# STATE
# ----------------------------

if "run" not in st.session_state:
    st.session_state.run = False

if "financials" not in st.session_state:
    st.session_state.financials = False

# ----------------------------
# HEADER
# ----------------------------

st.title("Buffett & Lynch Core Metrics + Stock Diagnostic Dashboard")

ticker = st.text_input("Enter Ticker", "CLOV")

btn1, btn2, _ = st.columns([1,1,6])

with btn1:
    if st.button("Run Analysis"):
        st.session_state.run = not st.session_state.run
        st.session_state.financials = False

with btn2:
    if st.button("Financials"):
        st.session_state.financials = not st.session_state.financials
        st.session_state.run = False

# ----------------------------
# DASHBOARD VIEW
# ----------------------------

if st.session_state.run:

    metrics = compute_metrics(ticker)

    # ----------------------------
    # SECTION 1
    # ----------------------------

    st.markdown("### Balance Sheet Safety (must pass)")

    debt_pass = metrics["debt_equity"] is not None and metrics["debt_equity"] < 0.5
    current_pass = metrics["current_ratio"] is not None and metrics["current_ratio"] > 1.5
    interest_pass = metrics["interest_coverage"] is not None and metrics["interest_coverage"] > 5

    html_section1 = f"""
    <table>
    <tr>
        <th class="col-metric">Metric</th>
        <th class="col-formula">Formula</th>
        <th class="col-threshold">Threshold</th>
        <th class="col-value">Current Value</th>
        <th class="col-why">Why It Matters</th>
    </tr>
    <tr>
        <td>Debt to Equity (D/E)</td>
        <td>Total Debt ÷ Shareholders' Equity</td>
        <td>&lt; 0.5</td>
        <td>{color_value(fmt_num(metrics["debt_equity"]), debt_pass)}</td>
        <td>Buffett: Avoid businesses that need good years just to survive.</td>
    </tr>
    <tr>
        <td>Current Ratio</td>
        <td>Current Assets ÷ Current Liabilities</td>
        <td>&gt; 1.5</td>
        <td>{color_value(fmt_num(metrics["current_ratio"]), current_pass)}</td>
        <td>Measures short-term liquidity strength.</td>
    </tr>
    <tr>
        <td>Interest Coverage</td>
        <td>Operating Income ÷ Interest Expense</td>
        <td>&gt; 5</td>
        <td>{color_value(fmt_num(metrics["interest_coverage"]), interest_pass)}</td>
        <td>Lynch: Debt can turn a small problem into a disaster.</td>
    </tr>
    </table>
    """

    st.markdown(html_section1, unsafe_allow_html=True)

    # ----------------------------
    # SECTION 2
    # ----------------------------

    st.markdown("### Cash & Earnings Quality (important)")

    fcf_conv_pass = metrics["fcf_conversion"] is not None and metrics["fcf_conversion"] > 0.8
    fcf_margin_pass = metrics["fcf_margin"] is not None and metrics["fcf_margin"] > 0.15

    html_section2 = f"""
    <table>
    <tr>
        <th class="col-metric">Metric</th>
        <th class="col-formula">Formula</th>
        <th class="col-threshold">Threshold</th>
        <th class="col-value">Current Value</th>
        <th class="col-why">Why It Matters</th>
    </tr>
    <tr>
        <td>Free Cash Flow Conversion</td>
        <td>Free Cash Flow ÷ Net Income</td>
        <td>&gt; 0.8</td>
        <td>{color_value(fmt_num(metrics["fcf_conversion"]), fcf_conv_pass)}</td>
        <td>Buffett: Earnings without cash are a hallucination.</td>
    </tr>
    <tr>
        <td>FCF Margin (TTM)</td>
        <td>Free Cash Flow ÷ Revenue</td>
        <td>&gt; 15%</td>
        <td>{color_value(fmt_pct(metrics["fcf_margin"]), fcf_margin_pass)}</td>
        <td>Indicates pricing power & operating efficiency.</td>
    </tr>
    </table>
    """

    st.markdown(html_section2, unsafe_allow_html=True)

    # ----------------------------
    # SECTION 3
    # ----------------------------

    st.markdown("### Capital Efficiency (quality signal)")

    roe_pass = metrics["roe"] is not None and metrics["roe"] > 0.20
    roic_pass = metrics["roic"] is not None and metrics["roic"] > 0.15

    html_section3 = f"""
    <table>
    <tr>
        <th class="col-metric">Metric</th>
        <th class="col-formula">Formula</th>
        <th class="col-threshold">Threshold</th>
        <th class="col-value">Current Value</th>
        <th class="col-why">Why It Matters</th>
    </tr>
    <tr>
        <td>Return on Equity (ROE)</td>
        <td>Net Income ÷ Shareholders' Equity</td>
        <td>&gt; 20%</td>
        <td>{color_value(fmt_pct(metrics["roe"]), roe_pass)}</td>
        <td>Lynch: Companies earning 20%+ can grow very fast.</td>
    </tr>
    <tr>
        <td>Return on Invested Capital (ROIC)</td>
        <td>NOPAT ÷ (Debt + Equity)</td>
        <td>&gt; 15%</td>
        <td>{color_value(fmt_pct(metrics["roic"]), roic_pass)}</td>
        <td>Buffett: Best single measure of business quality.</td>
    </tr>
    </table>
    """

    st.markdown(html_section3, unsafe_allow_html=True)
# ----------------------------
# FINANCIALS VIEW (DO NOT TOUCH DASHBOARD ABOVE)
# ----------------------------

if st.session_state.financials:

    st.markdown("## Financial Statements")

    # Annual / Quarterly Toggle
    view_type = st.radio(
        "Select View:",
        ["Annual", "Quarterly"],
        horizontal=True
    )

    ticker_obj = yf.Ticker(ticker)

    if view_type == "Annual":
        income = ticker_obj.financials
        balance = ticker_obj.balance_sheet
        cashflow = ticker_obj.cashflow
    else:
        income = ticker_obj.quarterly_financials
        balance = ticker_obj.quarterly_balance_sheet
        cashflow = ticker_obj.quarterly_cashflow

    # TIGHT BUTTON ROW
    button_container = st.container()

    with button_container:
        st.markdown("""
        <div style="display:flex; gap:6px;">
        """, unsafe_allow_html=True)

        if st.button("Income Statement", key="income_btn"):
            st.session_state.financial_view = "income"

        if st.button("Balance Sheet", key="balance_btn"):
        st.session_state.financial_view = "balance"

        if st.button("Cash Flow", key="cashflow_btn"):
        st.session_state.financial_view = "cashflow"

    st.markdown("</div>", unsafe_allow_html=True)

    def format_statement(df):
        if df is None:
            return None
        df = df.iloc[:, ::-1]
        return (df / 1_000_000).round(2)

    def render_table(df):
        if df is None:
            return
        df = format_statement(df)
        html = df.to_html(classes="financial-table")
        st.markdown(html, unsafe_allow_html=True)

    if st.session_state.financial_view == "income" and income is not None:
        st.markdown("### Income Statement (Millions)")
        render_table(income)

    if st.session_state.financial_view == "balance" and balance is not None:
        st.markdown("### Balance Sheet (Millions)")
        render_table(balance)

    if st.session_state.financial_view == "cashflow" and cashflow is not None:
        st.markdown("### Cash Flow (Millions)")
        render_table(cashflow)