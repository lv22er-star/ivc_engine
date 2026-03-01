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

.section-bar {
    background-color: #0b3d5c;
    text-align: center;
    font-weight: 600;
    font-size: 16px;
    padding: 8px;
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
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "N/A"
    try:
        return f"{float(x):,.2f}"
    except Exception:
        return "N/A"

def fmt_pct(x):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "N/A"
    try:
        return f"{float(x)*100:.2f}%"
    except Exception:
        return "N/A"

def color_value(val, passed):
    if val == "N/A":
        return f'<span style="color:#9aa0a6;">{val}</span>'
    if passed:
        return f'<span style="color:#1f7a3f;font-weight:600;">{val}</span>'
    return f'<span style="color:#c0392b;font-weight:600;">{val}</span>'

def find_value(df, labels):
    if df is None or not hasattr(df, "index"):
        return None
    for label in labels:
        if label in df.index:
            try:
                return df.loc[label].iloc[0]
            except Exception:
                return None
    return None

# ----------------------------
# SESSION STATE (SINGLE SOURCE OF TRUTH)
# ----------------------------

if "run" not in st.session_state:
    st.session_state.run = False

if "financials" not in st.session_state:
    st.session_state.financials = False

if "show_classify" not in st.session_state:
    st.session_state.show_classify = False

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

    # If still None, assume zero debt (common for some companies)
    if debt is None:
        debt = 0

    current_assets = find_value(balance, [
        "Total Current Assets",
        "Current Assets",
        "Current Assets Total"
    ])

    current_liab = find_value(balance, [
        "Total Current Liabilities",
        "Current Liabilities",
        "Current Liabilities Total"
    ])

    # If liabilities exist but assets missing, try to compute from components
    if current_assets is None:
        cash = find_value(balance, ["Cash And Cash Equivalents", "Cash"]) or 0
        receivables = find_value(balance, ["Accounts Receivable"]) or 0
        inventory = find_value(balance, ["Inventory"]) or 0

        total_components = cash + receivables + inventory
        if total_components > 0:
            current_assets = total_components

    # ----------------------------
    # CASH FLOW
    # ----------------------------

    depreciation = find_value(cashflow, [
        "Depreciation",
        "Depreciation & Amortization",
        "Depreciation And Amortization"
    ])

    capex = find_value(cashflow, [
        "Capital Expenditures"
    ])

    free_cash_flow = find_value(cashflow, [
        "Free Cash Flow"
    ])

    # ----------------------------
    # FCF STABILITY (5-Year Test)
    # ----------------------------

    fcf_stability = None
    if cashflow is not None and hasattr(cashflow, "index") and "Free Cash Flow" in cashflow.index:
        try:
            fcf_series = cashflow.loc["Free Cash Flow"][::-1]  # chronological
            if len(fcf_series) >= 5:
                last5 = fcf_series.iloc[-5:]
                fcf_stability = all((x is not None) and (x > 0) for x in last5)
        except Exception:
            fcf_stability = None

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
    # ROIC (Improved Invested Capital)
    # ----------------------------

    cash = find_value(balance, [
        "Cash And Cash Equivalents",
        "Cash"
    ]) or 0

    invested_capital = None
    if debt is not None and equity is not None:
        invested_capital = debt + equity - cash

    roic = None
    if op_income is not None and invested_capital not in (None, 0):
        tax_rate = 0.21
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
        "fcf_stability": fcf_stability,
    }

# ----------------------------
# HEADER + BUTTONS
# ----------------------------

st.title("Buffett & Lynch Core Metrics + Stock Diagnostic Dashboard")

col_ticker, col_spacer = st.columns([1, 7])

with col_ticker:
    ticker = st.text_input("Enter Ticker", "CLOV")

with col_spacer:
    st.empty()

btn1, btn2, btn3, _ = st.columns([1, 1, 1, 6])

with btn1:
    if st.button("Run Analysis"):
        st.session_state.run = not st.session_state.run
        st.session_state.financials = False
        st.session_state.show_classify = False

with btn2:
    if st.button("Classify"):
        st.session_state.show_classify = not st.session_state.show_classify
        st.session_state.run = False
        st.session_state.financials = False

with btn3:
    if st.button("Financials"):
        st.session_state.financials = not st.session_state.financials
        st.session_state.run = False
        st.session_state.show_classify = False

# ----------------------------
# DASHBOARD VIEW
# ----------------------------

if st.session_state.run:

    metrics = compute_metrics(ticker)

    # SECTION 1
    st.markdown("### Balance Sheet Safety (must pass)")

    debt_pass = metrics["debt_equity"] is not None and metrics["debt_equity"] < 0.5
    current_pass = metrics["current_ratio"] is not None and metrics["current_ratio"] > 1.5
    interest_pass = metrics["interest_coverage"] is not None and metrics["interest_coverage"] > 5

    html_section1 = f"""
    <table>
    <tr>
        <th colspan="5" class="section-bar">Can this company survive bad times?</th>
    </tr>
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
        <td>Buffett: “I don’t like businesses that need a good year just to survive.”</td>
    </tr>
    <tr>
        <td>Current Ratio</td>
        <td>Current Assets ÷ Current Liabilities</td>
        <td>&gt; 1.5</td>
        <td>{color_value(fmt_num(metrics["current_ratio"]), current_pass)}</td>
        <td>Measures short-term liquidity — whether the company can comfortably pay its bills over the next 12 months.</td>
    </tr>
    <tr>
        <td>Interest Coverage</td>
        <td>Operating Income ÷ Interest Expense</td>
        <td>&gt; 5</td>
        <td>{color_value(fmt_num(metrics["interest_coverage"]), interest_pass)}</td>
        <td>Lynch: “Debt can turn a small problem into a disaster.”</td>
    </tr>
    </table>
    """
    st.markdown(html_section1, unsafe_allow_html=True)

    # SECTION 2
    st.markdown("### Cash & Earnings Quality (important)")

    fcf_conv_pass = metrics["fcf_conversion"] is not None and metrics["fcf_conversion"] > 0.8
    fcf_margin_pass = metrics["fcf_margin"] is not None and metrics["fcf_margin"] > 0.15

    html_section2 = f"""
    <table>
    <tr>
        <th colspan="5" class="section-bar">Are the earnings real and durable?</th>
    </tr>
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
        <td>Buffett: “Earnings without cash are a hallucination.”</td>
    </tr>
    <tr>
        <td>FCF Stability</td>
        <td>FAIL if any of last 5 years ≤ 0</td>
        <td>PASS</td>
        <td>{color_value("PASS" if metrics["fcf_stability"] else "FAIL", metrics["fcf_stability"] is True)}</td>
        <td>Lynch: If it makes money in good times but not in bad, it’s not a great business.</td>
    </tr>
    <tr>
        <td>FCF Margin (TTM)</td>
        <td>Free Cash Flow ÷ Revenue</td>
        <td>&gt; 15%</td>
        <td>{color_value(fmt_pct(metrics["fcf_margin"]), fcf_margin_pass)}</td>
        <td>Measures how much free cash flow a company generates from each dollar of revenue.</td>
    </tr>
    </table>
    """
    st.markdown(html_section2, unsafe_allow_html=True)

    # SECTION 3
    st.markdown("### Capital Efficiency (quality signal)")

    roe_pass = metrics["roe"] is not None and metrics["roe"] > 0.20
    roic_pass = metrics["roic"] is not None and metrics["roic"] > 0.15

    html_section3 = f"""
    <table>
    <tr>
        <th colspan="5" class="section-bar">Can it compound capital?</th>
    </tr>
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
        <td>Lynch: Companies that can earn 20%+ on equity and reinvest it grow very fast.</td>
    </tr>
    <tr>
        <td>Return on Invested Capital (ROIC)</td>
        <td>NOPAT ÷ (Debt + Equity − Cash)</td>
        <td>&gt; 15%</td>
        <td>{color_value(fmt_pct(metrics["roic"]), roic_pass)}</td>
        <td>Buffett: “The single best measure of business quality is return on capital.”</td>
    </tr>
    </table>
    """
    st.markdown(html_section3, unsafe_allow_html=True)

# ----------------------------
# FINANCIALS VIEW
# ----------------------------

if st.session_state.financials:

    st.markdown("## Financial Statements")

    view_type = st.radio("Select View:", ["Annual", "Quarterly"], horizontal=True)

    ticker_obj = yf.Ticker(ticker)

    if view_type == "Annual":
        income = ticker_obj.financials
        balance = ticker_obj.balance_sheet
        cashflow = ticker_obj.cashflow
    else:
        income = ticker_obj.quarterly_financials
        balance = ticker_obj.quarterly_balance_sheet
        cashflow = ticker_obj.quarterly_cashflow

    if st.button("Income Statement", key="income_btn"):
        st.session_state.financial_view = "income"
    if st.button("Balance Sheet", key="balance_btn"):
        st.session_state.financial_view = "balance"
    if st.button("Cash Flow", key="cashflow_btn"):
        st.session_state.financial_view = "cashflow"

    def format_statement(df):
        if df is None:
            return None
        df = df.iloc[:, ::-1]
        return (df / 1_000_000).round(2)

    def render_table(df):
        if df is None:
            return
        df = format_statement(df)
        html = df.to_html()
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

# ----------------------------
# CLASSIFY VIEW (FULL ENGINE) — FIXED
# ----------------------------

if st.session_state.show_classify:

    st.divider()
    st.header("Business Classification & Routing")

    # ---- Local helpers (do not affect rest of app) ----

    def _safe_float(v):
        try:
            if v is None:
                return None
            if isinstance(v, bool):
                return None
            if isinstance(v, (int, float)):
                v = float(v)
                if math.isnan(v) or math.isinf(v):
                    return None
                return v
            if hasattr(v, "item"):
                return _safe_float(v.item())
            return None
        except Exception:
            return None

    def _fmt_pct(x):
        if x is None:
            return "N/A"
        return f"{x*100:.2f}%"

    def _fmt_num(x):
        if x is None:
            return "N/A"
        ax = abs(x)
        if ax != 0 and ax < 0.01:
            return f"{x:.6f}"
        if ax < 1:
            return f"{x:.4f}"
        if ax < 1000:
            return f"{x:,.2f}"
        return f"{x:,.0f}"

    def _badge(passed):
        if passed is True:
            return '<span style="background:#1f6f3a;color:#eaf5ee;padding:6px 10px;border-radius:8px;font-weight:800;">PASS</span>'
        if passed is False:
            return '<span style="background:#7a1f1f;color:#ffecec;padding:6px 10px;border-radius:8px;font-weight:800;">FAIL</span>'
        return '<span style="background:#3a3a3a;color:#d9d9d9;padding:6px 10px;border-radius:8px;font-weight:800;">N/A</span>'

    def _df_ok(df):
        return df is not None and hasattr(df, "empty") and (not df.empty) and hasattr(df, "columns") and len(df.columns) > 0

    def _find_row_value(df, labels, col):
        if not _df_ok(df):
            return None
        # exact match first
        for lab in labels:
            if lab in df.index:
                return _safe_float(df.loc[lab, col])
        # soft match second
        idx = list(df.index)
        idx_low = [str(x).lower() for x in idx]
        for lab in labels:
            lab_low = str(lab).lower()
            for i, n in enumerate(idx_low):
                if lab_low in n:
                    return _safe_float(df.loc[idx[i], col])
        return None

    def _get_series(df, labels, max_years):
        if not _df_ok(df):
            return [], 0
        cols = list(df.columns[:max_years])  # most recent first
        vals = []
        for c in cols:
            vals.append(_find_row_value(df, labels, c))
        used = sum(1 for v in vals if v is not None)
        return vals, used

    def _html_table(rows):
        header = """
        <table style="width:100%;table-layout:fixed;border-collapse:collapse;">
          <tr style="background:rgba(255,255,255,0.06);">
            <th style="width:36%;padding:8px;border:1px solid rgba(255,255,255,0.12);">Metric</th>
            <th style="width:20%;padding:8px;border:1px solid rgba(255,255,255,0.12);">Value</th>
            <th style="width:20%;padding:8px;border:1px solid rgba(255,255,255,0.12);">Threshold</th>
            <th style="width:24%;padding:8px;border:1px solid rgba(255,255,255,0.12);">Pass?</th>
          </tr>
        """
        body = ""
        for r in rows:
            body += (
                "<tr>"
                f"<td style='text-align:left;padding:8px;border:1px solid rgba(255,255,255,0.12);'>{r['Metric']}</td>"
                f"<td style='padding:8px;border:1px solid rgba(255,255,255,0.12);'>{r['Value']}</td>"
                f"<td style='padding:8px;border:1px solid rgba(255,255,255,0.12);'>{r['Threshold']}</td>"
                f"<td style='padding:8px;border:1px solid rgba(255,255,255,0.12);'>{r['Pass?']}</td>"
                "</tr>"
            )
        footer = "</table>"
        return header + body + footer

    # ---- Pull data (yfinance only) ----
    try:
        tkr = yf.Ticker(ticker)
        inc = tkr.financials
        bs = tkr.balance_sheet
        cf = tkr.cashflow
    except Exception:
        inc, bs, cf = None, None, None

    # ---- Layout columns ----
    left, middle, right = st.columns([1.2, 1.5, 1])

    # ----------------------------
    # LEFT: Thresholds (Edit as needed)
    # ----------------------------
    with left:
        st.subheader("Thresholds (Edit as needed)")

        th_net_ppe = st.number_input("1) Net PP&E / Total Assets >", value=0.40, step=0.01, format="%.4f")
        th_capex_rev = st.number_input("2) CapEx / Revenue >", value=0.15, step=0.01, format="%.4f")
        th_debt_ebitda = st.number_input("3) Debt / EBITDA >", value=3.50, step=0.10, format="%.2f")
        th_da_rev = st.number_input("4) D&A / Revenue >", value=0.10, step=0.01, format="%.4f")
        th_ebitdar_ic = st.number_input("5) EBITDAR / Invested Capital >", value=0.002, step=0.0005, format="%.4f")
        th_asset_yield = st.number_input("6) Asset Yield (Stability Test) >", value=0.08, step=0.01, format="%.4f")

        # NEW thresholds
        th_margin_range = st.number_input("Operating Margin Range (5Y) >", value=0.15, step=0.01, format="%.4f")
        th_share_cagr = st.number_input("Share Count CAGR (5Y) <", value=-0.02, step=0.005, format="%.4f")
        th_reinvest = st.number_input("Reinvestment Rate <", value=0.40, step=0.01, format="%.4f")

    # ----------------------------
    # Compute signals
    # ----------------------------

    col_inc = inc.columns[0] if _df_ok(inc) else None
    col_bs = bs.columns[0] if _df_ok(bs) else None
    col_cf = cf.columns[0] if _df_ok(cf) else None

    revenue = _find_row_value(inc, ["Total Revenue", "Revenue"], col_inc) if col_inc is not None else None
    op_income = _find_row_value(inc, ["Operating Income", "Operating Income Loss"], col_inc) if col_inc is not None else None
    net_income = _find_row_value(inc, ["Net Income", "Net Income Common Stockholders", "Net Income From Continuing Operations"], col_inc) if col_inc is not None else None

    total_assets = _find_row_value(bs, ["Total Assets"], col_bs) if col_bs is not None else None
    net_ppe = _find_row_value(bs, ["Net PPE", "Net Property Plant Equipment", "Property Plant Equipment Net"], col_bs) if col_bs is not None else None

    total_debt = _find_row_value(bs, ["Total Debt"], col_bs) if col_bs is not None else None
    if total_debt is None and col_bs is not None:
        lt = _find_row_value(bs, ["Long Term Debt"], col_bs)
        st_ = _find_row_value(bs, ["Short Long Term Debt", "Short Term Debt"], col_bs)
        if lt is not None or st_ is not None:
            total_debt = (lt or 0.0) + (st_ or 0.0)

    equity = _find_row_value(bs, ["Total Stockholder Equity", "Stockholders Equity"], col_bs) if col_bs is not None else None
    cash = _find_row_value(bs, ["Cash And Cash Equivalents", "Cash"], col_bs) if col_bs is not None else None

    capex = _find_row_value(cf, ["Capital Expenditures"], col_cf) if col_cf is not None else None
    capex = abs(capex) if capex is not None else None
    da = _find_row_value(cf, ["Depreciation", "Depreciation And Amortization", "Depreciation & Amortization"], col_cf) if col_cf is not None else None

    # 1) Net PP&E / Total Assets
    s_net_ppe = None if (net_ppe is None or total_assets in (None, 0)) else (net_ppe / total_assets)
    p_net_ppe = None if s_net_ppe is None else (s_net_ppe > th_net_ppe)

    # 2) CapEx / Revenue
    s_capex = None if (capex is None or revenue in (None, 0)) else (capex / revenue)
    p_capex = None if s_capex is None else (s_capex > th_capex_rev)

    # 3) Debt / EBITDA (EBITDA = Operating Income + D&A if missing)
    ebitda = _find_row_value(inc, ["EBITDA"], col_inc) if col_inc is not None else None
    if ebitda is None and op_income is not None and da is not None:
        ebitda = op_income + da

    s_debt_ebitda = None
    if total_debt is not None and ebitda is not None and ebitda > 0:
        s_debt_ebitda = total_debt / ebitda
    p_debt_ebitda = None if s_debt_ebitda is None else (s_debt_ebitda > th_debt_ebitda)

    # 4) D&A / Revenue
    s_da = None if (da is None or revenue in (None, 0)) else (da / revenue)
    p_da = None if s_da is None else (s_da > th_da_rev)

    # 5) EBITDAR / Invested Capital (rent assumed 0)
    rent = _find_row_value(inc, ["Rent"], col_inc) if col_inc is not None else None
    rent_val = 0.0 if rent is None else rent
    ebitdar = None if (op_income is None or da is None) else (op_income + da + rent_val)

    invested_cap = None
    if total_debt is not None and equity is not None and cash is not None:
        ic = total_debt + equity - cash
        invested_cap = ic if ic > 0 else None

    s_ebitdar = None if (ebitdar is None or invested_cap is None) else (ebitdar / invested_cap)
    p_ebitdar = None if s_ebitdar is None else (s_ebitdar > th_ebitdar_ic)

    # 6) Asset Yield (Stability Test) — 3y avg NOPAT/Assets
    s_asset_yield = None
    years_used_ay = 0
    try:
        if _df_ok(inc) and _df_ok(bs):
            inc_cols = list(inc.columns[:3])
            bs_cols = list(bs.columns[:3])
            n = min(len(inc_cols), len(bs_cols), 3)
            vals = []
            for i in range(n):
                oi = _find_row_value(inc, ["Operating Income", "Operating Income Loss"], inc_cols[i])
                ta = _find_row_value(bs, ["Total Assets"], bs_cols[i])
                if oi is None or ta in (None, 0):
                    continue
                nopat = oi * (1 - 0.21)
                vals.append(nopat / ta)
            years_used_ay = len(vals)
            if years_used_ay >= 1:
                s_asset_yield = sum(vals) / years_used_ay
    except Exception:
        s_asset_yield = None
        years_used_ay = 0

    p_asset_yield = None if s_asset_yield is None else (s_asset_yield > th_asset_yield)

    # ----------------------------
    # NEW SIGNALS
    # ----------------------------

    # 1) Operating Margin Range (5Y)
    op5, _ = _get_series(inc, ["Operating Income", "Operating Income Loss"], 5)
    rev5, _ = _get_series(inc, ["Total Revenue", "Revenue"], 5)

    margins = []
    for oi, rv in zip(op5, rev5):
        if oi is None or rv in (None, 0):
            continue
        margins.append(oi / rv)

    years_used_margin = len(margins)
    s_margin_range = None
    if years_used_margin >= 1:
        s_margin_range = max(margins) - min(margins)

    p_margin_range = None if s_margin_range is None else (s_margin_range <= th_margin_range)

    # 2) Share Count CAGR (5Y)
    share_labels = [
        "Common Stock Shares Outstanding",
        "Ordinary Shares Number",
        "Share Issued",
        "Shares Issued"
    ]
    sh5, _ = _get_series(bs, share_labels, 5)
    chrono = [v for v in sh5[::-1] if v is not None and v > 0]
    years_used_sh = max(0, len(chrono) - 1)

    s_share_cagr = None
    if len(chrono) >= 2 and years_used_sh > 0:
        try:
            s_share_cagr = (chrono[-1] / chrono[0]) ** (1 / years_used_sh) - 1
        except Exception:
            s_share_cagr = None

    p_share_cagr = None if s_share_cagr is None else (s_share_cagr < th_share_cagr)

    # 3) Reinvestment Rate = CapEx / Owner Earnings, OE = NI + D&A - CapEx
    ni5, _ = _get_series(inc, ["Net Income", "Net Income Common Stockholders", "Net Income From Continuing Operations"], 5)
    da5, _ = _get_series(cf, ["Depreciation", "Depreciation And Amortization", "Depreciation & Amortization"], 5)
    cap5, _ = _get_series(cf, ["Capital Expenditures"], 5)
    cap5 = [abs(v) if v is not None else None for v in cap5]

    s_reinvest = None
    years_used_reinv = 0
    for ni, d_a, cpx in zip(ni5, da5, cap5):
        if ni is None or d_a is None or cpx is None:
            continue
        owner_e = ni + d_a - cpx
        if owner_e <= 0:
            continue
        s_reinvest = cpx / owner_e
        years_used_reinv = 1
        break

    p_reinvest = None if s_reinvest is None else (s_reinvest < th_reinvest)

    # 4) Margin Trend (3Y): improving if last > first (chronological)
    op3, _ = _get_series(inc, ["Operating Income", "Operating Income Loss"], 3)
    rev3, _ = _get_series(inc, ["Total Revenue", "Revenue"], 3)

    op3c = op3[::-1]
    rev3c = rev3[::-1]
    m3 = []
    for oi, rv in zip(op3c, rev3c):
        if oi is None or rv in (None, 0):
            continue
        m3.append(oi / rv)

    years_used_trend = len(m3)
    p_margin_trend = None
    if years_used_trend >= 2:
        p_margin_trend = m3[-1] > m3[0]

    # ----------------------------
    # MIDDLE: Signals table
    # ----------------------------
    with middle:
        st.subheader("Signals (auto-calculated)")

        rows = []

        def add_row(metric, value_str, threshold_str, passed):
            rows.append({
                "Metric": metric,
                "Value": value_str,
                "Threshold": threshold_str,
                "Pass?": _badge(passed)
            })

        add_row("Net PP&E / Total Assets", _fmt_pct(s_net_ppe), _fmt_pct(th_net_ppe), p_net_ppe)
        add_row("CapEx / Revenue", _fmt_pct(s_capex), _fmt_pct(th_capex_rev), p_capex)
        add_row("Debt / EBITDA", _fmt_num(s_debt_ebitda), _fmt_num(th_debt_ebitda), p_debt_ebitda)
        add_row("D&A / Revenue", _fmt_pct(s_da), _fmt_pct(th_da_rev), p_da)
        add_row("EBITDAR / Invested Capital", _fmt_pct(s_ebitdar), _fmt_pct(th_ebitdar_ic), p_ebitdar)

        ay_label = "Asset Yield (Stability Test)"
        if years_used_ay > 0:
            ay_label += f" (Years Used: {years_used_ay})"
        add_row(ay_label, _fmt_pct(s_asset_yield), _fmt_pct(th_asset_yield), p_asset_yield)

        add_row(f"Operating Margin Range (5Y) (Years Used: {years_used_margin})",
                _fmt_pct(s_margin_range), _fmt_pct(th_margin_range), p_margin_range)

        add_row(f"Share Count CAGR (5Y) (Years Used: {years_used_sh})",
                _fmt_pct(s_share_cagr), _fmt_pct(th_share_cagr), p_share_cagr)

        reinv_label = "Reinvestment Rate"
        if years_used_reinv == 0:
            reinv_label += " (Years Used: 0)"
        add_row(reinv_label, _fmt_pct(s_reinvest), _fmt_pct(th_reinvest), p_reinvest)

        trend_value = "Improving" if p_margin_trend is True else ("Flat/Declining" if p_margin_trend is False else "N/A")
        add_row(f"Margin Trend (3Y) (Years Used: {years_used_trend})", trend_value, "Improving", p_margin_trend)

        st.markdown(_html_table(rows), unsafe_allow_html=True)

    # ----------------------------
    # RIGHT: Outputs + Updated Routing Logic
    # ----------------------------
    with right:
        st.subheader("Outputs")

        infra_passed = sum(1 for x in [p_net_ppe, p_capex, p_debt_ebitda, p_da, p_ebitdar, p_asset_yield] if x is True)
        infra_considered = sum(1 for x in [p_net_ppe, p_capex, p_debt_ebitda, p_da, p_ebitdar, p_asset_yield] if x is not None)

        st.write(f"Infrastructure Signals Passed: {infra_passed if infra_considered > 0 else 'N/A'}")

        infra_class = None if infra_considered == 0 else (infra_passed >= 3)
        st.write("Infra Classification (3+ signals):", "PASS" if infra_class is True else ("FAIL" if infra_class is False else "N/A"))

        # Too Early / Build Phase Flag
        too_early_flag = None
        cfo = _find_row_value(cf, ["Total Cash From Operating Activities", "Operating Cash Flow"], col_cf) if col_cf is not None else None
        if revenue is not None and net_income is not None and cfo is not None and capex is not None:
            fcf = cfo - capex
            too_early = (revenue <= 0) or ((net_income < 0) and (fcf < 0))
            too_early_flag = (not too_early)

        st.write("Too Early / Build Phase Flag:", "PASS" if too_early_flag is True else ("FAIL" if too_early_flag is False else "N/A"))

        # ROIC (for routing rule)
        roic = None
        if op_income is not None and total_debt is not None and equity is not None and cash is not None:
            ic = total_debt + equity - cash
            if ic and ic > 0:
                roic = (op_income * (1 - 0.21)) / ic

        # Updated Routing Logic
        routed = "OWNER_EARNINGS_DCF"

        if infra_class is True and s_margin_range is not None and s_margin_range <= th_margin_range:
            routed = "INFRASTRUCTURE_DCF"
        elif s_margin_range is not None and s_margin_range > th_margin_range and s_net_ppe is not None and s_net_ppe > th_net_ppe:
            routed = "GROWTH_NORMALIZATION_DCF"
        elif s_share_cagr is not None and s_share_cagr < th_share_cagr:
            routed = "REPURCHASE_ADJUSTED_FCF_DCF"
        elif s_reinvest is not None and s_reinvest < th_reinvest and roic is not None and roic > 0.15:
            routed = "OWNER_EARNINGS_DCF"
        else:
            routed = "OWNER_EARNINGS_DCF"

        st.write("Routed Model:", routed)