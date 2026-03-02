# app.py
# Buffett & Lynch Core Metrics + Stock Diagnostic Dashboard
# Single-file Streamlit app (NO local module imports)
# Includes: Run Analysis + Financials + Business Classification & Routing (Option A)

import math
import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(layout="wide")

# ----------------------------
# GLOBAL STYLE
# ----------------------------
st.markdown(
    """
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

/* Make number inputs look tighter */
div[data-testid="stNumberInput"] label {
    font-size: 12px;
    opacity: 0.95;
}
</style>
""",
    unsafe_allow_html=True,
)

# ----------------------------
# UTILITIES
# ----------------------------

def _is_nan(x):
    try:
        return x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x)))
    except Exception:
        return True

def safe_div(a, b):
    if _is_nan(a) or _is_nan(b) or b == 0:
        return None
    return a / b

def fmt_num(x):
    if _is_nan(x):
        return "N/A"
    try:
        ax = abs(float(x))
        if ax != 0 and ax < 0.01:
            return f"{x:.6f}"
        if ax < 1:
            return f"{x:.4f}"
        if ax < 1000:
            return f"{x:,.2f}"
        return f"{x:,.0f}"
    except Exception:
        return "N/A"

def fmt_pct(x):
    if _is_nan(x):
        return "N/A"
    try:
        return f"{float(x)*100:.2f}%"
    except Exception:
        return "N/A"

def color_value(val, passed):
    if val == "N/A":
        return f'<span style="color:#9aa0a6;">{val}</span>'
    if passed is True:
        return f'<span style="color:#1f7a3f;font-weight:600;">{val}</span>'
    if passed is False:
        return f'<span style="color:#c0392b;font-weight:600;">{val}</span>'
    return f'<span style="color:#9aa0a6;">{val}</span>'

def badge(passed):
    if passed is True:
        return '<span style="background:#1f6f3a;color:#eaf5ee;padding:5px 9px;border-radius:8px;font-weight:800;">PASS</span>'
    if passed is False:
        return '<span style="background:#7a1f1f;color:#ffecec;padding:5px 9px;border-radius:8px;font-weight:800;">FAIL</span>'
    return '<span style="background:#3a3a3a;color:#d9d9d9;padding:5px 9px;border-radius:8px;font-weight:800;">N/A</span>'

def _df_ok(df):
    return df is not None and hasattr(df, "empty") and (not df.empty) and hasattr(df, "columns") and len(df.columns) > 0

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

def normalize_label(s: str) -> str:
    return "".join(ch for ch in str(s).lower().strip() if ch.isalnum() or ch.isspace()).replace("  ", " ")

def safe_get(df, labels, col):
    """
    Robust row match:
    - exact match
    - normalized exact match
    - contains match (normalized)
    Returns float or None.
    """
    if not _df_ok(df) or col is None:
        return None

    try:
        idx = list(df.index)
    except Exception:
        return None

    idx_norm = [normalize_label(x) for x in idx]

    # 1) exact match
    for lab in labels:
        if lab in df.index:
            return _safe_float(df.loc[lab, col])

    # 2) normalized exact match
    for lab in labels:
        labn = normalize_label(lab)
        for i, n in enumerate(idx_norm):
            if labn == n:
                return _safe_float(df.loc[idx[i], col])

    # 3) contains match
    for lab in labels:
        labn = normalize_label(lab)
        for i, n in enumerate(idx_norm):
            if labn and labn in n:
                return _safe_float(df.loc[idx[i], col])

    return None

def get_statement(tkr: yf.Ticker, statement_name: str, period: str):
    """
    statement_name: 'income'|'balance'|'cashflow'
    period: 'annual'|'quarterly'
    """
    try:
        if statement_name == "income":
            df = tkr.financials if period == "annual" else tkr.quarterly_financials
        elif statement_name == "balance":
            df = tkr.balance_sheet if period == "annual" else tkr.quarterly_balance_sheet
        elif statement_name == "cashflow":
            df = tkr.cashflow if period == "annual" else tkr.quarterly_cashflow
        else:
            df = None
    except Exception:
        df = None

    if df is None:
        return None

    # Make sure columns are datetime-like if possible
    try:
        cols = []
        for c in df.columns:
            if isinstance(c, pd.Timestamp):
                cols.append(c)
            else:
                try:
                    cols.append(pd.to_datetime(c))
                except Exception:
                    cols.append(c)
        df.columns = cols
    except Exception:
        pass

    return df

def quarterly_to_annual_series(df_q, labels, agg="sum", max_years=5):
    """
    Convert quarterly statement to annual series by fiscal year (calendar year grouping).
    agg: 'sum' for income/cashflow, 'last' for balance.
    Returns (values_chrono, years_used, years_list_chrono)
    """
    if not _df_ok(df_q):
        return [], 0, []

    # columns: timestamps likely
    cols = list(df_q.columns)
    # keep only timestamp-like
    cols_ts = []
    for c in cols:
        if isinstance(c, pd.Timestamp):
            cols_ts.append(c)
        else:
            try:
                cols_ts.append(pd.to_datetime(c))
            except Exception:
                pass

    if not cols_ts:
        return [], 0, []

    # group by year
    by_year = {}
    for c in cols_ts:
        y = int(c.year)
        by_year.setdefault(y, []).append(c)

    years = sorted(by_year.keys())
    if not years:
        return [], 0, []

    # take last max_years years
    years = years[-max_years:]

    vals = []
    years_out = []
    for y in years:
        year_cols = sorted(by_year[y])
        year_vals = []
        for col in year_cols:
            v = safe_get(df_q, labels, col)
            if v is None:
                continue
            year_vals.append(v)

        if not year_vals:
            continue

        if agg == "sum":
            v_annual = float(sum(year_vals))
        else:
            v_annual = float(year_vals[-1])

        vals.append(v_annual)
        years_out.append(y)

    used = len(vals)
    return vals, used, years_out

def annual_series(df_a, labels, max_years=5):
    """
    Pull annual series across columns (yfinance: most recent first).
    Return chrono order.
    """
    if not _df_ok(df_a):
        return [], 0

    cols = list(df_a.columns[:max_years])  # most recent first
    vals = []
    for c in cols:
        vals.append(safe_get(df_a, labels, c))
    # chrono
    chrono = [v for v in vals[::-1] if v is not None]
    return chrono, len(chrono)

def cagr_from_series(chrono_vals):
    if chrono_vals is None:
        return None, 0
    vals = [v for v in chrono_vals if v is not None and v > 0]
    if len(vals) < 2:
        return None, len(vals)
    n_years = len(vals) - 1
    try:
        return (vals[-1] / vals[0]) ** (1 / n_years) - 1, len(vals)
    except Exception:
        return None, len(vals)

def build_signal_row(metric, value, threshold_display, passed, years_used=None, value_is_pct=False):
    if value_is_pct:
        v_disp = fmt_pct(value)
    else:
        v_disp = fmt_num(value) if not isinstance(value, str) else value

    label = metric
    if years_used is not None:
        label = f"{metric} (Years Used: {years_used})"

    return {
        "Metric": label,
        "Value": v_disp if v_disp is not None else "N/A",
        "Threshold": threshold_display,
        "Pass?": badge(passed),
        "_pass_raw": passed,
        "_value_raw": value,
    }

def html_table(rows):
    html = """
    <table style="width:100%;border-collapse:collapse;">
      <tr style="background:rgba(255,255,255,0.06);">
        <th style="padding:8px;border:1px solid rgba(255,255,255,0.12);text-align:left;">Metric</th>
        <th style="padding:8px;border:1px solid rgba(255,255,255,0.12);">Value</th>
        <th style="padding:8px;border:1px solid rgba(255,255,255,0.12);">Threshold</th>
        <th style="padding:8px;border:1px solid rgba(255,255,255,0.12);">Pass?</th>
      </tr>
    """
    for r in rows:
        html += f"""
        <tr>
          <td style="padding:8px;border:1px solid rgba(255,255,255,0.12);text-align:left;">{r['Metric']}</td>
          <td style="padding:8px;border:1px solid rgba(255,255,255,0.12);">{r['Value']}</td>
          <td style="padding:8px;border:1px solid rgba(255,255,255,0.12);">{r['Threshold']}</td>
          <td style="padding:8px;border:1px solid rgba(255,255,255,0.12);">{r['Pass?']}</td>
        </tr>
        """
    html += "</table>"
    return html

# ----------------------------
# SESSION STATE
# ----------------------------
if "run" not in st.session_state:
    st.session_state.run = False
if "financials" not in st.session_state:
    st.session_state.financials = False
if "show_classify" not in st.session_state:
    st.session_state.show_classify = False
if "financial_view" not in st.session_state:
    st.session_state.financial_view = None

# Threshold state
if "preset" not in st.session_state:
    st.session_state.preset = "Default (Balanced)"
if "preset_last" not in st.session_state:
    st.session_state.preset_last = st.session_state.preset

# ----------------------------
# METRIC ENGINE (RUN ANALYSIS)
# ----------------------------

def find_value(df, labels):
    if df is None or df.empty:
        return None
    col = df.columns[0] if len(df.columns) else None
    if col is None:
        return None
    return safe_get(df, labels, col)

def compute_metrics(ticker):
    t = yf.Ticker(ticker)

    income = get_statement(t, "income", "annual")
    balance = get_statement(t, "balance", "annual")
    cashflow = get_statement(t, "cashflow", "annual")

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
        "EBIT",
        "Operating Income Loss"
    ])

    interest = find_value(income, [
        "Interest Expense",
        "Interest Expense Non Operating"
    ])

    equity = find_value(balance, [
        "Total Stockholder Equity",
        "Stockholders Equity",
        "Total Equity Gross Minority Interest"
    ])

    total_debt = find_value(balance, ["Total Debt"])
    long_debt = find_value(balance, ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"])
    short_debt = find_value(balance, ["Short Long Term Debt", "Short Term Debt", "Current Debt", "Current Debt And Capital Lease Obligation"])

    debt = total_debt
    if debt is None:
        if long_debt is None and short_debt is None:
            debt = None
        else:
            debt = (long_debt or 0) + (short_debt or 0)

    current_assets = find_value(balance, ["Total Current Assets", "Current Assets"])
    current_liab = find_value(balance, ["Total Current Liabilities", "Current Liabilities"])

    depreciation = find_value(cashflow, [
        "Depreciation",
        "Depreciation & Amortization",
        "Depreciation And Amortization"
    ])
    capex = find_value(cashflow, ["Capital Expenditures"])
    capex = abs(capex) if capex is not None else None

    free_cash_flow = find_value(cashflow, ["Free Cash Flow"])

    # Build FCF if missing: CFO - CapEx (preferred)
    cfo = find_value(cashflow, ["Total Cash From Operating Activities", "Operating Cash Flow"])
    if free_cash_flow is None and cfo is not None and capex is not None:
        free_cash_flow = cfo - capex
    # fallback: NI + D&A - CapEx
    if free_cash_flow is None and net_income is not None:
        free_cash_flow = (net_income or 0) + (depreciation or 0) - (capex or 0)

    # FCF STABILITY (5-year): positive FCF each year if available
    fcf_stability = None
    if _df_ok(cashflow) and "Free Cash Flow" in list(cashflow.index):
        try:
            series = cashflow.loc["Free Cash Flow"][::-1]  # chrono
            series = [ _safe_float(x) for x in series.tolist() ]
            series = [x for x in series if x is not None]
            if len(series) >= 3:
                last = series[-5:] if len(series) >= 5 else series
                fcf_stability = all(x > 0 for x in last)
        except Exception:
            fcf_stability = None

    debt_equity = safe_div(debt, equity)
    current_ratio = safe_div(current_assets, current_liab)

    interest_coverage = None
    if op_income is not None and interest not in (None, 0):
        interest_coverage = safe_div(op_income, abs(interest))

    fcf_conversion = safe_div(free_cash_flow, net_income)
    fcf_margin = safe_div(free_cash_flow, revenue)
    roe = safe_div(net_income, equity)

    cash = find_value(balance, ["Cash And Cash Equivalents", "Cash", "Cash And Cash Equivalents At Carrying Value"]) or 0
    invested_capital = None
    if debt is not None and equity is not None:
        invested_capital = debt + equity - cash

    roic = None
    if op_income is not None and invested_capital not in (None, 0):
        nopat = op_income * (1 - 0.21)
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

col_ticker, col_info = st.columns([1, 3])

with col_ticker:
    ticker = st.text_input("Enter Ticker", "CLOV")

company_name = ""
sector = ""

if ticker:
    try:
        t_info = yf.Ticker(ticker).info
        company_name = t_info.get("longName", "")
        sector = t_info.get("sector", "")
    except Exception:
        company_name = ""
        sector = ""

with col_info:
    if company_name:
        st.markdown(
            f"<div style='margin-top:28px;font-size:16px;'>"
            f"<b>{ticker.upper()}</b> — {company_name} | "
            f"<span style='opacity:0.8;'>Sector: {sector}</span>"
            f"</div>",
            unsafe_allow_html=True
        )

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

    st.markdown("### Balance Sheet Safety (must pass)")
    debt_pass = metrics["debt_equity"] is not None and metrics["debt_equity"] < 0.5
    current_pass = metrics["current_ratio"] is not None and metrics["current_ratio"] > 1.5
    interest_pass = metrics["interest_coverage"] is not None and metrics["interest_coverage"] > 5

    html_section1 = f"""
    <table>
    <tr>
        <th colspan="5" class="section-bar">
            Can this company survive bad times?
        </th>
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

    st.markdown("### Cash & Earnings Quality (important)")
    fcf_conv_pass = metrics["fcf_conversion"] is not None and metrics["fcf_conversion"] > 0.8
    fcf_margin_pass = metrics["fcf_margin"] is not None and metrics["fcf_margin"] > 0.15

    html_section2 = f"""
    <table>
    <tr>
        <th colspan="5" class="section-bar">
            Are the earnings real and durable?
        </th>
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
        <td>FAIL if any of last years ≤ 0</td>
        <td>PASS</td>
        <td>{color_value("PASS" if metrics["fcf_stability"] else ("FAIL" if metrics["fcf_stability"] is False else "N/A"),
                        metrics["fcf_stability"] == True if metrics["fcf_stability"] is not None else None)}</td>
        <td>Lynch: If it makes money in good times but not in bad, it’s not a great business.</td>
    </tr>
    <tr>
        <td>FCF Margin (TTM-ish)</td>
        <td>Free Cash Flow ÷ Revenue</td>
        <td>&gt; 15%</td>
        <td>{color_value(fmt_pct(metrics["fcf_margin"]), fcf_margin_pass)}</td>
        <td>Measures how much free cash flow a company generates from each dollar of revenue.</td>
    </tr>
    </table>
    """
    st.markdown(html_section2, unsafe_allow_html=True)

    st.markdown("### Capital Efficiency (quality signal)")
    roe_pass = metrics["roe"] is not None and metrics["roe"] > 0.20
    roic_pass = metrics["roic"] is not None and metrics["roic"] > 0.15

    html_section3 = f"""
    <table>
    <tr>
        <th colspan="5" class="section-bar">
            Can it compound capital?
        </th>
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
    period = "annual" if view_type == "Annual" else "quarterly"

    t = yf.Ticker(ticker)

    income = get_statement(t, "income", period)
    balance = get_statement(t, "balance", period)
    cashflow = get_statement(t, "cashflow", period)

    if st.button("Income Statement", key="income_btn"):
        st.session_state.financial_view = "income"
    if st.button("Balance Sheet", key="balance_btn"):
        st.session_state.financial_view = "balance"
    if st.button("Cash Flow", key="cashflow_btn"):
        st.session_state.financial_view = "cashflow"

    def format_statement(df):
        if df is None or df.empty:
            return None
        df = df.iloc[:, ::-1]
        try:
            return (df / 1_000_000).round(2)
        except Exception:
            return df

    def render_table(df):
        df = format_statement(df)
        if df is None:
            st.write("N/A")
            return
        html = df.to_html()
        st.markdown(html, unsafe_allow_html=True)

    if st.session_state.financial_view == "income":
        st.markdown("### Income Statement")
        render_table(income)
    if st.session_state.financial_view == "balance":
        st.markdown("### Balance Sheet")
        render_table(balance)
    if st.session_state.financial_view == "cashflow":
        st.markdown("### Cash Flow")
        render_table(cashflow)

# ----------------------------
# CLASSIFY VIEW (OPTION A)
# ----------------------------
if st.session_state.show_classify:
    st.divider()
    st.header("Business Classification & Routing")

    # Pull data
    tkr = yf.Ticker(ticker)
    info = {}
    try:
        info = tkr.info or {}
    except Exception:
        info = {}

    inc_a = get_statement(tkr, "income", "annual")
    bs_a = get_statement(tkr, "balance", "annual")
    cf_a = get_statement(tkr, "cashflow", "annual")

    inc_q = get_statement(tkr, "income", "quarterly")
    bs_q = get_statement(tkr, "balance", "quarterly")
    cf_q = get_statement(tkr, "cashflow", "quarterly")

    # Detect financials/banks (limited usefulness)
    sector = str(info.get("sector", "") or "")
    industry = str(info.get("industry", "") or "")
    is_financial = any(k in (sector + " " + industry).lower() for k in [
        "financial", "bank", "insurance", "capital markets", "credit", "asset management"
    ])

    # Threshold presets
    presets = {
        "Default (Balanced)": {
            "th_net_ppe": 0.40,
            "th_capex_rev": 0.15,
            "th_debt_ebitda": 3.50,
            "th_da_rev": 0.10,
            "th_ebitdar_ic": 0.002,
            "th_asset_yield": 0.08,
            "th_margin_range": 0.15,      # NOTE: smaller is better (range <= threshold => PASS)
            "th_share_cagr": -0.02,       # more negative is better (cagr < threshold => PASS)
            "th_reinvest": 0.40,          # capex/cfo < threshold => PASS
            "trend_mode": "Improving Only"
        },
        "Tech / Platform": {
            "th_net_ppe": 0.25,
            "th_capex_rev": 0.10,
            "th_debt_ebitda": 4.00,
            "th_da_rev": 0.08,
            "th_ebitdar_ic": 0.002,
            "th_asset_yield": 0.10,
            "th_margin_range": 0.25,
            "th_share_cagr": 0.00,        # flat/down ok (PASS if < 0.00)
            "th_reinvest": 0.60,
            "trend_mode": "Improving Only"
        },
        "Cyclical / Commodity": {
            "th_net_ppe": 0.40,
            "th_capex_rev": 0.15,
            "th_debt_ebitda": 3.00,
            "th_da_rev": 0.10,
            "th_ebitdar_ic": 0.002,
            "th_asset_yield": 0.08,
            "th_margin_range": 0.35,
            "th_share_cagr": -0.02,
            "th_reinvest": 0.50,
            "trend_mode": "Improving Only"
        },
        "Financials / Banks": {
            "th_net_ppe": 0.40,
            "th_capex_rev": 0.15,
            "th_debt_ebitda": 3.50,
            "th_da_rev": 0.10,
            "th_ebitdar_ic": 0.002,
            "th_asset_yield": 0.08,
            "th_margin_range": 0.25,
            "th_share_cagr": -0.02,
            "th_reinvest": 0.40,
            "trend_mode": "Improving Only"
        },
    }

    # Initialize thresholds in session if missing
    for k in presets["Default (Balanced)"].keys():
        if k not in st.session_state:
            st.session_state[k] = presets[st.session_state.preset].get(k, presets["Default (Balanced)"][k])

    # Layout columns
    left, middle, right = st.columns([1, 1.2, 0.8])

    # LEFT: Thresholds + Presets
    with left:
        st.subheader("Thresholds (Edit as needed)")

        preset = st.selectbox(
            "Calibration presets",
            list(presets.keys()),
            index=list(presets.keys()).index(st.session_state.preset) if st.session_state.preset in presets else 0,
            key="preset",
        )

        # Apply preset when changed
        if st.session_state.preset != st.session_state.preset_last:
            chosen = presets.get(st.session_state.preset, presets["Default (Balanced)"])
            for key, val in chosen.items():
                st.session_state[key] = val
            st.session_state.preset_last = st.session_state.preset

        st.number_input("1) Net PP&E / Total Assets >", key="th_net_ppe", step=0.01, format="%.4f")
        st.number_input("2) CapEx / Revenue >", key="th_capex_rev", step=0.01, format="%.4f")
        st.number_input("3) Debt / EBITDA >", key="th_debt_ebitda", step=0.10, format="%.2f")
        st.number_input("4) D&A / Revenue >", key="th_da_rev", step=0.01, format="%.4f")
        st.number_input("5) EBITDAR / Invested Capital >", key="th_ebitdar_ic", step=0.0005, format="%.4f")
        st.number_input("6) Asset Yield (Stability Test) >", key="th_asset_yield", step=0.01, format="%.4f")

        st.markdown("---")
        st.number_input("Operating Margin Range (5Y) <", key="th_margin_range", step=0.01, format="%.4f")
        st.number_input("Share Count CAGR (5Y) <", key="th_share_cagr", step=0.005, format="%.4f")
        st.number_input("Reinvestment Rate (CapEx/CFO) <", key="th_reinvest", step=0.01, format="%.4f")
        st.selectbox("Margin Trend (3Y) Pass Condition", ["Improving Only"], key="trend_mode")

        if is_financial:
            st.info("Financial company detected: many infrastructure signals may be N/A (manual review recommended).")

    # ----------------------------
    # SIGNAL COMPUTATION (Annual preferred; fallback quarterly aggregated)
    # ----------------------------
    # Annual latest columns
    col_inc_a = inc_a.columns[0] if _df_ok(inc_a) else None
    col_bs_a = bs_a.columns[0] if _df_ok(bs_a) else None
    col_cf_a = cf_a.columns[0] if _df_ok(cf_a) else None

    # If annual is missing, we fallback using quarterly grouping
    use_quarterly_fallback = (not _df_ok(inc_a)) or (not _df_ok(bs_a)) or (not _df_ok(cf_a))

    # Revenue / Operating Income series (annual)
    rev_series, rev_years_used = annual_series(inc_a, ["Total Revenue", "Revenue"], max_years=5)
    oi_series, oi_years_used = annual_series(inc_a, ["Operating Income", "Operating Income Loss", "EBIT"], max_years=5)

    # Fallback series if annual insufficient
    if rev_years_used < 2:
        rev_series_q, used_q, _ = quarterly_to_annual_series(inc_q, ["Total Revenue", "Revenue"], agg="sum", max_years=5)
        if used_q >= 2:
            rev_series = rev_series_q
            rev_years_used = used_q

    if oi_years_used < 2:
        oi_series_q, used_q, _ = quarterly_to_annual_series(inc_q, ["Operating Income", "Operating Income Loss", "EBIT"], agg="sum", max_years=5)
        if used_q >= 2:
            oi_series = oi_series_q
            oi_years_used = used_q

    # CFO + CapEx series
    cfo_series, cfo_used = annual_series(cf_a, ["Total Cash From Operating Activities", "Operating Cash Flow"], max_years=5)
    capex_labels = [
        "Capital Expenditures",
        "Capital Expenditure",
        "Purchase Of PPE",
        "Purchases Of Property Plant And Equipment",
        "Additions To Property Plant And Equipment",
        "Investments In Property Plant And Equipment"
    ]

    capex_series, capex_used = annual_series(cf_a, capex_labels, max_years=5)
    capex_series = [abs(x) if x is not None else None for x in capex_series]

    if cfo_used < 2:
        cfo_q, used_q, _ = quarterly_to_annual_series(cf_q, ["Total Cash From Operating Activities", "Operating Cash Flow"], agg="sum", max_years=5)
        if used_q >= 2:
            cfo_series = cfo_q
            cfo_used = used_q

    if capex_used < 2:
        cap_q, used_q, _ = quarterly_to_annual_series(cf_q, capex_labels, agg="sum", max_years=5)
        cap_q = [abs(x) if x is not None else None for x in cap_q]
        if used_q >= 2:
            capex_series = cap_q
            capex_used = used_q

    # Balance: total assets, net PPE, debt/equity/cash series (need 'last' aggregation for quarterly)
    assets_series, assets_used = annual_series(bs_a, ["Total Assets"], max_years=5)
    ppe_series, ppe_used = annual_series(bs_a, [
        "Property Plant Equipment Net",
        "Net PPE",
        "Net Property Plant Equipment",
        "Property Plant Equipment",
        "Property Plant And Equipment Net"
    ], max_years=5)

    debt_series, debt_used = annual_series(bs_a, ["Total Debt"], max_years=5)
    eq_series, eq_used = annual_series(bs_a, ["Total Stockholder Equity", "Stockholders Equity", "Total Equity Gross Minority Interest"], max_years=5)
    cash_series, cash_used = annual_series(bs_a, ["Cash And Cash Equivalents", "Cash", "Cash And Cash Equivalents At Carrying Value"], max_years=5)

    # Debt fallback build from LT+ST
    if debt_used < 2:
        lt_series, lt_used = annual_series(bs_a, ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"], max_years=5)
        st_series, st_used = annual_series(bs_a, ["Short Long Term Debt", "Short Term Debt", "Current Debt", "Current Debt And Capital Lease Obligation"], max_years=5)
        if max(lt_used, st_used) >= 2:
            # align by length (use last min length)
            n = min(len(lt_series), len(st_series))
            if n >= 2:
                debt_series = [(lt_series[-n + i] or 0) + (st_series[-n + i] or 0) for i in range(n)]
                debt_used = len(debt_series)

    # Quarterly fallback for balance items
    if assets_used < 2:
        a_q, used_q, _ = quarterly_to_annual_series(bs_q, ["Total Assets"], agg="last", max_years=5)
        if used_q >= 2:
            assets_series = a_q
            assets_used = used_q

    if ppe_used < 2:
        p_q, used_q, _ = quarterly_to_annual_series(bs_q, [
            "Property Plant Equipment Net",
            "Net PPE",
            "Net Property Plant Equipment",
            "Property Plant Equipment",
            "Property Plant And Equipment Net"
        ], agg="last", max_years=5)
        if used_q >= 2:
            ppe_series = p_q
            ppe_used = used_q

    if debt_used < 2:
        d_q, used_q, _ = quarterly_to_annual_series(bs_q, ["Total Debt"], agg="last", max_years=5)
        if used_q >= 2:
            debt_series = d_q
            debt_used = used_q
        else:
            # build from quarterly LT+ST
            lt_q, lt_u, _ = quarterly_to_annual_series(bs_q, ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"], agg="last", max_years=5)
            st_q, st_u, _ = quarterly_to_annual_series(bs_q, ["Short Long Term Debt", "Short Term Debt", "Current Debt", "Current Debt And Capital Lease Obligation"], agg="last", max_years=5)
            n = min(len(lt_q), len(st_q))
            if n >= 2:
                debt_series = [(lt_q[i] or 0) + (st_q[i] or 0) for i in range(n)]
                debt_used = len(debt_series)

    if eq_used < 2:
        e_q, used_q, _ = quarterly_to_annual_series(bs_q, ["Total Stockholder Equity", "Stockholders Equity", "Total Equity Gross Minority Interest"], agg="last", max_years=5)
        if used_q >= 2:
            eq_series = e_q
            eq_used = used_q

    if cash_used < 2:
        c_q, used_q, _ = quarterly_to_annual_series(bs_q, ["Cash And Cash Equivalents", "Cash", "Cash And Cash Equivalents At Carrying Value"], agg="last", max_years=5)
        if used_q >= 2:
            cash_series = c_q
            cash_used = used_q

    # Latest "single-year" values (use last element in chrono series)
    revenue = rev_series[-1] if rev_series else None
    op_income = oi_series[-1] if oi_series else None
    cfo = cfo_series[-1] if cfo_series else None
    capex = capex_series[-1] if capex_series else None
    total_assets = assets_series[-1] if assets_series else None
    net_ppe = ppe_series[-1] if ppe_series else None
    total_debt = debt_series[-1] if debt_series else None
    equity = eq_series[-1] if eq_series else None
    cash = cash_series[-1] if cash_series else None

    # EBITDA series: try direct annual; else compute Operating Income + D&A
    ebitda_series, ebitda_used = annual_series(inc_a, ["EBITDA"], max_years=5)
    if ebitda_used < 2:
        eb_q, used_q, _ = quarterly_to_annual_series(inc_q, ["EBITDA"], agg="sum", max_years=5)
        if used_q >= 2:
            ebitda_series = eb_q
            ebitda_used = used_q

    da_series, da_used = annual_series(cf_a, ["Depreciation", "Depreciation And Amortization", "Depreciation & Amortization"], max_years=5)
    if da_used < 2:
        da_q, used_q, _ = quarterly_to_annual_series(cf_q, ["Depreciation", "Depreciation And Amortization", "Depreciation & Amortization"], agg="sum", max_years=5)
        if used_q >= 2:
            da_series = da_q
            da_used = used_q

    # if EBITDA missing, compute
    if (not ebitda_series) and oi_series and da_series:
        n = min(len(oi_series), len(da_series))
        if n >= 1:
            ebitda_series = [(oi_series[-n + i] if oi_series[-n + i] is not None else None) + (da_series[-n + i] if da_series[-n + i] is not None else None)
                             if (oi_series[-n + i] is not None and da_series[-n + i] is not None) else None
                             for i in range(n)]
            ebitda_used = len([x for x in ebitda_series if x is not None])

    ebitda = ebitda_series[-1] if ebitda_series else None
    da = da_series[-1] if da_series else None

    # Invested Capital series: Debt + Equity - Cash
    invcap_series = []
    n_ic = min(len(debt_series), len(eq_series), len(cash_series)) if debt_series and eq_series and cash_series else 0
    if n_ic >= 1:
        for i in range(n_ic):
            d = debt_series[-n_ic + i]
            e = eq_series[-n_ic + i]
            c = cash_series[-n_ic + i]
            if d is None or e is None or c is None:
                invcap_series.append(None)
                continue
            ic = d + e - c
            invcap_series.append(ic if ic > 0 else None)
    invcap_used = len([x for x in invcap_series if x is not None])
    invested_capital = invcap_series[-1] if invcap_series else None

    # EBITDAR proxy: EBITDA + Rent/Lease if available; else EBITDA
    rent_series, rent_used = annual_series(inc_a, ["Rent", "Lease", "Operating Lease"], max_years=5)
    if rent_used < 2:
        r_q, used_q, _ = quarterly_to_annual_series(inc_q, ["Rent", "Lease", "Operating Lease"], agg="sum", max_years=5)
        if used_q >= 2:
            rent_series = r_q
            rent_used = used_q

    ebitdar_series = []
    n_ed = min(len(ebitda_series), len(rent_series)) if ebitda_series and rent_series else (len(ebitda_series) if ebitda_series else 0)
    if n_ed >= 1:
        if rent_series:
            for i in range(n_ed):
                eb = ebitda_series[-n_ed + i]
                rn = rent_series[-n_ed + i] if len(rent_series) >= n_ed else None
                if eb is None:
                    ebitdar_series.append(None)
                else:
                    ebitdar_series.append(eb + (rn or 0))
        else:
            ebitdar_series = ebitda_series[:]
    ebitdar_used = len([x for x in ebitdar_series if x is not None])
    ebitdar = ebitdar_series[-1] if ebitdar_series else None

    # ----------------------------
    # Compute classification signals
    # ----------------------------
    th_net_ppe = st.session_state["th_net_ppe"]
    th_capex_rev = st.session_state["th_capex_rev"]
    th_debt_ebitda = st.session_state["th_debt_ebitda"]
    th_da_rev = st.session_state["th_da_rev"]
    th_ebitdar_ic = st.session_state["th_ebitdar_ic"]
    th_asset_yield = st.session_state["th_asset_yield"]
    th_margin_range = st.session_state["th_margin_range"]
    th_share_cagr = st.session_state["th_share_cagr"]
    th_reinvest = st.session_state["th_reinvest"]

    # 1) Net PPE / Total Assets
    s_net_ppe = None if (net_ppe is None or total_assets in (None, 0)) else (net_ppe / total_assets)
    p_net_ppe = None if s_net_ppe is None else (s_net_ppe > th_net_ppe)
    years_netppe = min(ppe_used, assets_used) if (ppe_used and assets_used) else 0

    # 2) CapEx / Revenue (CapEx positive outflow)
    s_capex_rev = None if (capex is None or revenue in (None, 0)) else (capex / revenue)
    p_capex_rev = None if s_capex_rev is None else (s_capex_rev > th_capex_rev)
    years_capexrev = min(capex_used, rev_years_used) if (capex_used and rev_years_used) else 0

    # 3) Debt / EBITDA
    s_debt_ebitda = None
    if total_debt is not None and ebitda is not None and ebitda > 0:
        s_debt_ebitda = total_debt / ebitda
    p_debt_ebitda = None if s_debt_ebitda is None else (s_debt_ebitda > th_debt_ebitda)
    years_debt = min(debt_used, ebitda_used) if (debt_used and ebitda_used) else 0

    # 4) D&A / Revenue
    s_da_rev = None if (da is None or revenue in (None, 0)) else (da / revenue)
    p_da_rev = None if s_da_rev is None else (s_da_rev > th_da_rev)
    years_darev = min(da_used, rev_years_used) if (da_used and rev_years_used) else 0

    # 5) EBITDAR / Invested Capital
    s_ebitdar_ic = None
    if ebitdar is not None and invested_capital not in (None, 0):
        s_ebitdar_ic = ebitdar / invested_capital
    p_ebitdar_ic = None if s_ebitdar_ic is None else (s_ebitdar_ic > th_ebitdar_ic)
    years_ebitdar = min(ebitdar_used, invcap_used) if (ebitdar_used and invcap_used) else 0

    # 6) Asset Yield (Stability Test): average(EBITDA / InvestedCapital) across years
    asset_yield_vals = []
    n_ay = min(len(ebitda_series), len(invcap_series)) if ebitda_series and invcap_series else 0
    if n_ay >= 1:
        for i in range(n_ay):
            eb = ebitda_series[-n_ay + i]
            ic = invcap_series[-n_ay + i]
            if eb is None or ic in (None, 0):
                continue
            asset_yield_vals.append(eb / ic)
    years_asset_yield = len(asset_yield_vals)
    s_asset_yield = None
    if years_asset_yield >= 1:
        s_asset_yield = sum(asset_yield_vals) / years_asset_yield
    # gate: do not force pass/fail unless at least 2 years (meaningful)
    p_asset_yield = None if (s_asset_yield is None or years_asset_yield < 2) else (s_asset_yield > th_asset_yield)

    # ----------------------------
    # Added calibration signals
    # ----------------------------

    # Operating Margin Range (5Y): smaller is better => PASS if range <= threshold
    margins = []
    n_m = min(len(oi_series), len(rev_series))
    if n_m >= 1:
        for i in range(n_m):
            oi = oi_series[-n_m + i]
            rv = rev_series[-n_m + i]
            if oi is None or rv in (None, 0):
                continue
            margins.append(oi / rv)
    # use up to 5 years
    margins = margins[-5:] if len(margins) > 5 else margins
    years_margin = len(margins)
    s_margin_range = None
    if years_margin >= 2:
        s_margin_range = max(margins) - min(margins)
    # don't force pass/fail unless >=2 years
    if s_margin_range is None or years_margin < 2:
        p_margin_range = None
    else:
        p_margin_range = s_margin_range <= th_margin_range
    # Share Count CAGR (5Y): prefer statement row; fallback to info sharesOutstanding only if no history => N/A
    share_labels = [
        "Diluted Average Shares",
        "Basic Average Shares",
        "Basic Average Shares Outstanding",
        "Diluted Weighted Average Shares",
        "Basic Weighted Average Shares",
        "Weighted Average Shares",
        "Common Stock Shares Outstanding",
        "Ordinary Shares Number",
    ]
    shares_series, shares_used = annual_series(inc_a, share_labels, max_years=5)
    if shares_used < 2:
        # try balance sheet share rows
        shares_series_bs, shares_used_bs = annual_series(bs_a, share_labels, max_years=5)
        if shares_used_bs >= 2:
            shares_series = shares_series_bs
            shares_used = shares_used_bs
        else:
            # quarterly fallback
            sh_q, used_q, _ = quarterly_to_annual_series(inc_q, share_labels, agg="sum", max_years=5)
            # sums on shares is not ideal; better use last for shares if present:
            if used_q < 2:
                sh_q, used_q, _ = quarterly_to_annual_series(bs_q, share_labels, agg="last", max_years=5)
            if used_q >= 2:
                shares_series = sh_q
                shares_used = used_q

    s_share_cagr, share_years = cagr_from_series(shares_series if shares_series else [])
    years_share = share_years if share_years >= 2 else 0
    # do not force if less than 2 points
    p_share_cagr = None if (s_share_cagr is None or years_share < 2) else (s_share_cagr < th_share_cagr)

    # Reinvestment Rate: CapEx_outflow / CFO (reliable proxy)
    s_reinvest = None
    years_reinvest = 0
    n_rr = min(len(capex_series), len(cfo_series)) if capex_series and cfo_series else 0
    if n_rr >= 1:
        # use latest year only (as requested)
        cfo_latest = cfo_series[-1]
        cap_latest = capex_series[-1]
        if cfo_latest is not None and cfo_latest > 0 and cap_latest is not None:
            s_reinvest = cap_latest / cfo_latest
            years_reinvest = 1
    p_reinvest = None if s_reinvest is None else (s_reinvest < th_reinvest)

    # Margin Trend (3Y): Improving / Declining / Flat / N/A
    trend_label = "N/A"
    p_margin_trend = None
    # last up to 3 margins
    m3 = margins[-3:] if margins else []
    if len(m3) >= 2:
        # compute simple direction using first vs last
        delta = m3[-1] - m3[0]
        if abs(delta) < 0.005:
            trend_label = "Flat"
        elif delta > 0:
            trend_label = "Improving"
        else:
            trend_label = "Declining"
        # Pass condition (Option A)
        p_margin_trend = True if trend_label == "Improving" else False
        # if fewer than 3 points, keep pass/fail but label years
    years_trend = len(m3)

    # ----------------------------
    # MIDDLE: Signals table
    # ----------------------------
    with middle:
        st.subheader("Signals (auto-calculated)")

        rows = []

        # Infrastructure / asset-heavy
        rows.append(build_signal_row(
            "Net PPE / Total Assets",
            s_net_ppe,
            fmt_pct(th_net_ppe),
            (p_net_ppe if years_netppe >= 1 else None),
            years_used=years_netppe,
            value_is_pct=True
        ))
        rows.append(build_signal_row(
            "CapEx / Revenue",
            s_capex_rev,
            fmt_pct(th_capex_rev),
            (p_capex_rev if years_capexrev >= 1 else None),
            years_used=years_capexrev,
            value_is_pct=True
        ))
        rows.append(build_signal_row(
            "Debt / EBITDA",
            s_debt_ebitda,
            fmt_num(th_debt_ebitda),
            (p_debt_ebitda if years_debt >= 1 else None),
            years_used=years_debt,
            value_is_pct=False
        ))
        rows.append(build_signal_row(
            "D&A / Revenue",
            s_da_rev,
            fmt_pct(th_da_rev),
            (p_da_rev if years_darev >= 1 else None),
            years_used=years_darev,
            value_is_pct=True
        ))
        rows.append(build_signal_row(
            "EBITDAR / Invested Capital",
            s_ebitdar_ic,
            fmt_pct(th_ebitdar_ic),
            (p_ebitdar_ic if years_ebitdar >= 1 else None),
            years_used=years_ebitdar,
            value_is_pct=True
        ))
        rows.append(build_signal_row(
            "Asset Yield (Stability Test)",
            s_asset_yield,
            fmt_pct(th_asset_yield),
            p_asset_yield,
            years_used=years_asset_yield,
            value_is_pct=True
        ))

        # Added signals
        rows.append(build_signal_row(
            "Operating Margin Range (5Y)",
            s_margin_range,
            f"< {fmt_pct(th_margin_range)}",
            p_margin_range,
            years_used=years_margin,
            value_is_pct=True
        ))
        rows.append(build_signal_row(
            "Share Count CAGR (5Y)",
            s_share_cagr,
            f"< {fmt_pct(th_share_cagr)}",
            p_share_cagr,
            years_used=years_share,
            value_is_pct=True
        ))
        rows.append(build_signal_row(
            "Reinvestment Rate (CapEx/CFO)",
            s_reinvest,
            f"< {fmt_pct(th_reinvest)}",
            p_reinvest,
            years_used=years_reinvest,
            value_is_pct=True
        ))
        rows.append(build_signal_row(
            "Margin Trend (3Y)",
            trend_label,
            "Improving",
            p_margin_trend,
            years_used=years_trend,
            value_is_pct=False
        ))

        import pandas as pd

        display_rows = []

        for r in rows:
            raw_pass = r["_pass_raw"]

            if raw_pass is True:
                pass_display = "PASS"
            elif raw_pass is False:
                pass_display = "FAIL"
            else:
                pass_display = "N/A"

            display_rows.append({
                "Metric": r["Metric"],
                "Value": r["Value"],
                "Threshold": r["Threshold"],
                "Pass?": pass_display
            })

        df_display = pd.DataFrame(display_rows)

        df_display = df_display.reset_index(drop=True)

        st.table(df_display)

    # ----------------------------
    # RIGHT: Outputs (robust routing)
    # ----------------------------
    with right:
        st.subheader("Outputs")

        # Helper: extract pass values by metric name startswith
        def pass_of(prefix):
            for r in rows:
                if r["Metric"].startswith(prefix):
                    return r.get("_pass_raw", None)
            return None

        # Infrastructure signals to count (exclude N/A)
        infra_pass_list = [
            pass_of("Net PPE / Total Assets"),
            pass_of("CapEx / Revenue"),
            pass_of("Debt / EBITDA"),
            pass_of("D&A / Revenue"),
            pass_of("EBITDAR / Invested Capital"),
        ]
        infra_count = sum(1 for x in infra_pass_list if x is True)

        asset_yield_pass = pass_of("Asset Yield (Stability Test)")

        st.write(f"Infrastructure Signals Passed: {infra_count}")

        # Infra Classification:
        # PASS if count >= 3 AND Asset Yield PASS (stability gate)
        infra_class = None
        if asset_yield_pass is None:
            infra_class = False  # stability gate missing => fail classification
        else:
            infra_class = (infra_count >= 3) and (asset_yield_pass is True)

        st.write("Infra Classification (3+ signals + Asset Yield gate):", "PASS" if infra_class else "FAIL")

        # Too Early / Build Phase Flag:
        # PASS if Revenue CAGR positive AND FCF margin positive
        rev_cagr, rev_pts = cagr_from_series(rev_series if rev_series else [])
        fcf_margin_latest = None
        if (cfo is not None) and (capex is not None) and (revenue not in (None, 0)):
            fcf_latest = cfo - capex  # CapEx treated positive outflow
            fcf_margin_latest = fcf_latest / revenue

        too_early_flag = None
        # require at least 2 points for rev CAGR
        if rev_cagr is not None and rev_pts >= 2 and fcf_margin_latest is not None:
            too_early_flag = (rev_cagr > 0) and (fcf_margin_latest > 0)

        st.write(
            "Too Early / Build Phase Flag:",
            "PASS" if too_early_flag is True else ("FAIL" if too_early_flag is False else "N/A"),
        )

        # Routing logic + Why
        routed = "OWNER_EARNINGS_DCF"
        reasons = []

        # Financials note
        if is_financial:
            routed = "OWNER_EARNINGS_DCF (Manual Review)"
            reasons.append("Financial company detected (many infra signals not applicable).")
        else:
            # 1) Infra PASS and not Too Early => INFRASTRUCTURE_BUILD_DCF
            if infra_class is True and (too_early_flag is True or too_early_flag is None):
                # If Too Early is N/A, we still allow infra build, but note uncertainty
                routed = "INFRASTRUCTURE_BUILD_DCF"
                reasons.append("Infra classification PASS (>=3 + Asset Yield gate).")
                if too_early_flag is True:
                    reasons.append("Not too early: revenue growth + positive FCF margin.")
                else:
                    reasons.append("Too Early flag N/A (limited data), defaulting to Infra build due to infra strength.")

            # 2) Repurchase-adjusted if strong buybacks and FCF margin positive
            elif (p_share_cagr is True) and (fcf_margin_latest is not None and fcf_margin_latest > 0):
                routed = "REPURCHASE_ADJUSTED_FCF_DCF"
                reasons.append("Share count shrinking meaningfully (CAGR below threshold).")
                reasons.append("Positive FCF margin supports buyback-driven compounding.")

            # 3) Growth normalization if volatility FAIL or margin trend declining
            elif (p_margin_range is False) or (p_margin_trend is False and trend_label == "Declining"):
                routed = "GROWTH_NORMALIZATION_DCF"
                if p_margin_range is False:
                    reasons.append("Operating margin range is volatile (range above threshold).")
                if trend_label == "Declining":
                    reasons.append("Operating margin trend is declining.")

            # 4) default
            else:
                routed = "OWNER_EARNINGS_DCF"
                reasons.append("Default route: stable enough for Owner Earnings DCF.")

        st.write("Routed Model:", routed)

        why = " • ".join(reasons[:4]) if reasons else "N/A"
        st.caption(f"Why this model: {why}")

        # Helpful small diagnostics (optional but safe)
        st.markdown("---")
        st.write("Revenue CAGR:", fmt_pct(rev_cagr) if rev_cagr is not None else "N/A")
        st.write("FCF Margin (latest):", fmt_pct(fcf_margin_latest) if fcf_margin_latest is not None else "N/A")