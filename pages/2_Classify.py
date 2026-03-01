import math
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple, Dict, Any

import pandas as pd
import streamlit as st
import yfinance as yf


# ----------------------------
# Page Config (inherits theme; keep dark vibe)
# ----------------------------
st.set_page_config(
    page_title="Business Classification & Routing",
    layout="wide",
)

# ----------------------------
# Session State: ticker sync
# ----------------------------
if "ticker" not in st.session_state:
    st.session_state["ticker"] = "AAPL"

ticker = (st.session_state.get("ticker") or "").strip().upper()
if not ticker:
    ticker = "AAPL"
    st.session_state["ticker"] = ticker

# ----------------------------
# Styling helpers (spreadsheet vibe)
# ----------------------------
NEUTRAL_BG = "#2b2b2b"
NEUTRAL_FG = "#d9d9d9"

PASS_BG = "#1f6f3a"   # green
FAIL_BG = "#7a1f1f"   # red
NA_BG = "#3a3a3a"     # neutral gray


def _fmt_pct(x: Optional[float]) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "N/A"
    return f"{x*100:.2f}%"


def _fmt_num(x: Optional[float]) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "N/A"
    # small numbers keep precision
    ax = abs(x)
    if ax != 0 and ax < 0.01:
        return f"{x:.6f}"
    if ax < 1:
        return f"{x:.4f}"
    if ax < 1000:
        return f"{x:,.2f}"
    return f"{x:,.0f}"


def _passfail_bg(status: Optional[bool]) -> str:
    if status is True:
        return PASS_BG
    if status is False:
        return FAIL_BG
    return NA_BG


def _status_text(status: Optional[bool]) -> str:
    if status is True:
        return "PASS"
    if status is False:
        return "FAIL"
    return "N/A"


def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        if isinstance(v, (int, float)) and not (isinstance(v, bool)):
            if math.isnan(float(v)) or math.isinf(float(v)):
                return None
            return float(v)
        # pandas scalars
        if hasattr(v, "item"):
            vv = v.item()
            return _safe_float(vv)
        return None
    except Exception:
        return None


def _normalize_label(s: str) -> str:
    return "".join(ch.lower() for ch in s.strip() if ch.isalnum() or ch.isspace()).strip()


def _find_row_value(df: Optional[pd.DataFrame], labels: Sequence[str]) -> Optional[float]:
    """
    yfinance statements are DataFrames where index is the label and columns are periods.
    We want the last available year (most recent column).
    Hardened:
      - Case/spacing-insensitive match
      - Tries exact normalized match, then 'contains' match
      - Never crashes
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return None
    if df.columns is None or len(df.columns) == 0:
        return None

    # Most recent period is typically first column in yfinance statements
    col = df.columns[0]

    idx_norm = [_normalize_label(str(i)) for i in df.index]
    df_index_map = {idx_norm[i]: df.index[i] for i in range(len(idx_norm))}

    wanted_norm = [_normalize_label(x) for x in labels]

    # 1) exact normalized match
    for w in wanted_norm:
        if w in df_index_map:
            raw_label = df_index_map[w]
            return _safe_float(df.loc[raw_label, col])

    # 2) contains match (best effort)
    for w in wanted_norm:
        for k_norm, raw_label in df_index_map.items():
            if w and (w in k_norm):
                return _safe_float(df.loc[raw_label, col])

    return None


def _sum_row_values(df: Optional[pd.DataFrame], labels: Sequence[str]) -> Optional[float]:
    vals = []
    for lab in labels:
        v = _find_row_value(df, [lab])
        if v is not None:
            vals.append(v)
    if not vals:
        return None
    return float(sum(vals))


# ----------------------------
# Thresholds (edit as needed)
# ----------------------------
DEFAULT_THRESHOLDS = {
    "Net PP&E / Total Assets >": 0.40,
    "CapEx / Revenue >": 0.15,
    "Debt / EBITDA >": 3.50,
    "D&A / Revenue >": 0.10,
    "EBITDAR / Invested Capital >": 0.002,
    "Asset Yield (Stability Test) >": 0.08,
}

if "classify_thresholds" not in st.session_state:
    st.session_state["classify_thresholds"] = DEFAULT_THRESHOLDS.copy()


def get_threshold(key: str) -> float:
    d = st.session_state["classify_thresholds"]
    return float(d.get(key, DEFAULT_THRESHOLDS[key]))


def set_threshold(key: str, val: float) -> None:
    st.session_state["classify_thresholds"][key] = float(val)


# ----------------------------
# Data extraction (yfinance only)
# ----------------------------
@st.cache_data(show_spinner=False, ttl=60 * 60)
def load_statements(tkr: str) -> Dict[str, Optional[pd.DataFrame]]:
    try:
        yt = yf.Ticker(tkr)
        # Annual statements
        bs = getattr(yt, "balance_sheet", None)
        is_ = getattr(yt, "financials", None)
        cf = getattr(yt, "cashflow", None)
        # Some tickers return empty frames; normalize to None
        if bs is not None and isinstance(bs, pd.DataFrame) and bs.empty:
            bs = None
        if is_ is not None and isinstance(is_, pd.DataFrame) and is_.empty:
            is_ = None
        if cf is not None and isinstance(cf, pd.DataFrame) and cf.empty:
            cf = None
        return {"bs": bs, "is": is_, "cf": cf}
    except Exception:
        return {"bs": None, "is": None, "cf": None}


stmts = load_statements(ticker)
bs = stmts["bs"]
inc = stmts["is"]
cf = stmts["cf"]


# ----------------------------
# Signals computation
# ----------------------------
@dataclass
class SignalRow:
    name: str
    value: Optional[float]
    threshold: Optional[float]
    passed: Optional[bool]
    display_as: str  # "pct" or "num"


def _cmp_gt(value: Optional[float], threshold: Optional[float]) -> Optional[bool]:
    if value is None or threshold is None:
        return None
    try:
        return bool(value > threshold)
    except Exception:
        return None


def compute_signals(th: Dict[str, float]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    # ---- Pull needed raw fields
    net_ppe = _find_row_value(
        bs,
        ["Net PPE", "Net Property Plant Equipment", "Property Plant Equipment Net", "Net Tangible Assets"],
    )
    total_assets = _find_row_value(bs, ["Total Assets"])

    capex = _find_row_value(cf, ["Capital Expenditures"])
    if capex is not None:
        capex = abs(capex)

    revenue = _find_row_value(inc, ["Total Revenue"])

    total_debt = _find_row_value(bs, ["Total Debt"])
    if total_debt is None:
        # fallback: LT Debt + ST Debt if present
        lt = _find_row_value(bs, ["Long Term Debt"])
        st = _find_row_value(bs, ["Short Long Term Debt"])
        if lt is not None or st is not None:
            total_debt = (lt or 0.0) + (st or 0.0)
        else:
            total_debt = None

    ebitda = _find_row_value(inc, ["EBITDA"])
    op_income = _find_row_value(inc, ["Operating Income", "Operating Income Loss"])
    da = _find_row_value(cf, ["Depreciation", "Depreciation And Amortization"])
    if ebitda is None:
        if op_income is not None and da is not None:
            ebitda = op_income + da
        else:
            ebitda = None

    # Negative/zero EBITDA => N/A for Debt/EBITDA
    if ebitda is not None and ebitda <= 0:
        debt_to_ebitda = None
    else:
        debt_to_ebitda = None if (total_debt is None or ebitda is None) else (total_debt / ebitda)

    # ---- Signal 1: Net PPE / Total Assets
    s1 = None if (net_ppe is None or total_assets is None or total_assets == 0) else (net_ppe / total_assets)

    # ---- Signal 2: CapEx / Revenue
    s2 = None if (capex is None or revenue is None or revenue == 0) else (capex / revenue)

    # ---- Signal 3: Debt / EBITDA (computed above)
    s3 = debt_to_ebitda

    # ---- Signal 4: D&A / Revenue
    s4 = None if (da is None or revenue is None or revenue == 0) else (da / revenue)

    # ---- Signal 5: EBITDAR / Invested Capital
    # Rent usually missing; treat missing rent as 0 but do not treat missing core fields as 0.
    rent = _find_row_value(inc, ["Rent"])  # very likely None
    rent_val = 0.0 if rent is None else rent

    # EBITDAR: op_income + D&A + rent (rent may be 0)
    ebitdar = None
    if op_income is not None and da is not None:
        ebitdar = op_income + da + rent_val
    elif op_income is not None and da is None:
        # Can't compute EBITDAR reliably if D&A missing
        ebitdar = None
    elif op_income is None and da is not None:
        ebitdar = None

    total_equity = _find_row_value(bs, ["Total Stockholder Equity", "Stockholders Equity"])
    cash = _find_row_value(
        bs,
        ["Cash And Cash Equivalents", "Cash And Cash Equivalents At Carrying Value", "Cash"],
    )

    invested_capital = None
    if total_debt is not None and total_equity is not None and cash is not None:
        invested_capital = total_debt + total_equity - cash
        if invested_capital <= 0:
            invested_capital = None
    else:
        invested_capital = None

    s5 = None if (ebitdar is None or invested_capital is None) else (ebitdar / invested_capital)

    # ---- Signal 6: Asset Yield (Stability Test)
    # Keep visible; if cannot compute reliably, N/A.
    # We'll attempt 3-year average if statement columns allow, else N/A.
    s6 = None
    try:
        if inc is not None and bs is not None and isinstance(inc, pd.DataFrame) and isinstance(bs, pd.DataFrame):
            # Need Operating Income and Total Assets over up to 3 years
            # yfinance typically returns columns as periods; take up to first 3 columns
            inc_cols = list(inc.columns[:3])
            bs_cols = list(bs.columns[:3])
            n = min(len(inc_cols), len(bs_cols), 3)

            yields = []
            for i in range(n):
                col_inc = inc_cols[i]
                col_bs = bs_cols[i]

                # operating income per year
                op_i = None
                for lab in ["Operating Income", "Operating Income Loss"]:
                    # direct index access by column year
                    op_i = _safe_float(inc.loc[inc.index.map(str).str.lower().str.strip().isin([lab.lower()]), col_inc].iloc[0]) \
                        if op_i is None and any(inc.index.map(str).str.lower().str.strip() == lab.lower()) else op_i

                # fallback robust: reuse finder but temporarily swap to column i by making a 1-col df
                if op_i is None:
                    inc_one = inc[[col_inc]].copy()
                    inc_one.columns = [inc.columns[0]]  # hack for _find_row_value first-col logic
                    op_i = _find_row_value(inc_one, ["Operating Income", "Operating Income Loss"])

                ta_i = None
                if "Total Assets" in bs.index:
                    ta_i = _safe_float(bs.loc["Total Assets", col_bs])
                else:
                    bs_one = bs[[col_bs]].copy()
                    bs_one.columns = [bs.columns[0]]
                    ta_i = _find_row_value(bs_one, ["Total Assets"])

                if op_i is None or ta_i is None or ta_i == 0:
                    continue

                nopat = op_i * (1.0 - 0.21)
                yields.append(nopat / ta_i)

            if len(yields) >= 2:
                s6 = float(sum(yields) / len(yields))
            elif len(yields) == 1:
                s6 = float(yields[0])
            else:
                s6 = None
        else:
            s6 = None
    except Exception:
        s6 = None

    # ---- Build rows with pass/fail vs thresholds
    rows = []

    # 1) Net PP&E / Total Assets > 0.40
    t1 = th["Net PP&E / Total Assets >"]
    rows.append(SignalRow(
        name="Net PP&E / Total Assets",
        value=s1,
        threshold=t1,
        passed=_cmp_gt(s1, t1),
        display_as="pct",
    ))

    # 2) CapEx / Revenue > 0.15
    t2 = th["CapEx / Revenue >"]
    rows.append(SignalRow(
        name="CapEx / Revenue",
        value=s2,
        threshold=t2,
        passed=_cmp_gt(s2, t2),
        display_as="pct",
    ))

    # 3) Debt / EBITDA > 3.50
    t3 = th["Debt / EBITDA >"]
    rows.append(SignalRow(
        name="Debt / EBITDA",
        value=s3,
        threshold=t3,
        passed=_cmp_gt(s3, t3),
        display_as="num",
    ))

    # 4) D&A / Revenue > 0.10
    t4 = th["D&A / Revenue >"]
    rows.append(SignalRow(
        name="D&A / Revenue",
        value=s4,
        threshold=t4,
        passed=_cmp_gt(s4, t4),
        display_as="pct",
    ))

    # 5) EBITDAR / Invested Capital > 0.002
    t5 = th["EBITDAR / Invested Capital >"]
    rows.append(SignalRow(
        name="EBITDAR / Invested Capital",
        value=s5,
        threshold=t5,
        passed=_cmp_gt(s5, t5),
        display_as="pct",  # it's a ratio; show as %
    ))

    # 6) Asset Yield (Stability Test) > 0.08
    t6 = th["Asset Yield (Stability Test) >"]
    rows.append(SignalRow(
        name="Asset Yield (Stability Test)",
        value=s6,
        threshold=t6,
        passed=_cmp_gt(s6, t6),
        display_as="pct",
    ))

    # ---- Right side outputs
    # Count signals passed (only non-N/A)
    passed_count = sum(1 for r in rows if r.passed is True)
    considered_count = sum(1 for r in rows if r.passed is not None)

    infra_class = (passed_count >= 3) if considered_count > 0 else None

    # Too Early / Build Phase Flag:
    # FAIL (too early) if (Revenue <= 0) OR (Net Income < 0 AND FCF < 0)
    net_income = _find_row_value(inc, ["Net Income", "Net Income Common Stockholders", "Net Income Applicable To Common Shares"])
    cfo = _find_row_value(cf, ["Total Cash From Operating Activities", "Operating Cash Flow"])
    # FCF = CFO - CapEx (if CFO exists)
    fcf = None
    if cfo is not None and capex is not None:
        fcf = cfo - capex
    else:
        fcf = None  # per requirement, do not silently proxy to 0

    too_early_flag = None
    try:
        if revenue is None or net_income is None or fcf is None:
            # If missing key fields -> N/A
            too_early_flag = None
        else:
            too_early = (revenue <= 0) or ((net_income < 0) and (fcf < 0))
            too_early_flag = (not too_early)  # PASS means NOT too early
    except Exception:
        too_early_flag = None

    routed_model = "OWNER_EARNINGS_DCF"
    if infra_class is True and too_early_flag is True:
        routed_model = "INFRASTRUCTURE_DCF"
    else:
        routed_model = "OWNER_EARNINGS_DCF"

    # ---- Signals table df
    def fmt_val(r: SignalRow) -> str:
        if r.display_as == "pct":
            return _fmt_pct(r.value)
        return _fmt_num(r.value)

    def fmt_thr(r: SignalRow) -> str:
        if r.display_as == "pct":
            return _fmt_pct(r.threshold)
        return _fmt_num(r.threshold)

    df = pd.DataFrame([{
        "Signal": r.name,
        "Value": fmt_val(r),
        "Threshold": fmt_thr(r),
        "Pass?": _status_text(r.passed),
        "_pass_bool": r.passed,
    } for r in rows])

    outputs = {
        "passed_count": passed_count,
        "considered_count": considered_count,
        "infra_class": infra_class,
        "too_early_flag": too_early_flag,
        "routed_model": routed_model,
        "raw": {
            "revenue": revenue,
            "net_income": net_income,
            "cfo": cfo,
            "capex": capex,
            "fcf": fcf,
        }
    }

    return df, outputs


# ----------------------------
# Header row (like app): ticker + nav buttons
# ----------------------------
top_left, top_mid, top_right = st.columns([1.25, 1.75, 1.0], vertical_alignment="center")

with top_left:
    st.text_input("Ticker", key="ticker")

with top_mid:
    btn_cols = st.columns([1, 1, 1], vertical_alignment="center")
    with btn_cols[0]:
        if st.button("Run Analysis", use_container_width=True):
            st.switch_page("app.py")
    with btn_cols[1]:
        if st.button("Financials", use_container_width=True):
            st.switch_page("pages/1_Financials.py")
    with btn_cols[2]:
        st.button("Classify", use_container_width=True, disabled=True)

with top_right:
    st.caption("")

st.divider()

# ----------------------------
# Three-panel layout
# ----------------------------
left, mid, right = st.columns([1.15, 1.55, 1.05], gap="large")

with left:
    st.markdown("### Business Classification & Routing")
    st.markdown("**Thresholds (Edit as needed)**")

    # Keep spreadsheet vibe: row layout
    def thresh_row(label: str, key: str, default: float, kind: str):
        c1, c2 = st.columns([1.35, 0.65], vertical_alignment="center")
        with c1:
            st.markdown(f"<div style='color:{NEUTRAL_FG}; padding:6px 0'>{label}</div>", unsafe_allow_html=True)
        with c2:
            if kind == "pct":
                v = st.number_input(
                    "",
                    min_value=0.0,
                    max_value=5.0,
                    value=float(get_threshold(key)),
                    step=0.01,
                    format="%.4f",
                    key=f"th_{key}",
                    help="Enter as decimal (e.g., 0.40 = 40%)",
                )
            else:
                v = st.number_input(
                    "",
                    value=float(get_threshold(key)),
                    step=0.10,
                    format="%.2f",
                    key=f"th_{key}",
                )
            set_threshold(key, v)

    st.markdown(
        f"<div style='background:{NEUTRAL_BG}; padding:12px; border-radius:10px;'>",
        unsafe_allow_html=True,
    )

    thresh_row("1) Net PP&E / Total Assets >", "Net PP&E / Total Assets >", DEFAULT_THRESHOLDS["Net PP&E / Total Assets >"], "pct")
    thresh_row("2) CapEx / Revenue >", "CapEx / Revenue >", DEFAULT_THRESHOLDS["CapEx / Revenue >"], "pct")
    thresh_row("3) Debt / EBITDA >", "Debt / EBITDA >", DEFAULT_THRESHOLDS["Debt / EBITDA >"], "num")
    thresh_row("4) D&A / Revenue >", "D&A / Revenue >", DEFAULT_THRESHOLDS["D&A / Revenue >"], "pct")
    thresh_row("5) EBITDAR / Invested Capital >", "EBITDAR / Invested Capital >", DEFAULT_THRESHOLDS["EBITDAR / Invested Capital >"], "pct")
    thresh_row("6) Asset Yield (Stability Test) >", "Asset Yield (Stability Test) >", DEFAULT_THRESHOLDS["Asset Yield (Stability Test) >"], "pct")

    st.markdown("</div>", unsafe_allow_html=True)

with mid:
    st.markdown("### Signals (auto-calculated)")

    thresholds = st.session_state["classify_thresholds"].copy()
    df_signals, outputs = compute_signals(thresholds)

    def style_signals(styler: pd.io.formats.style.Styler) -> pd.io.formats.style.Styler:
        def row_style(row):
            pb = row["_pass_bool"]
            bg = _passfail_bg(pb)
            # Apply to Pass? cell strongly, and lightly to whole row
            styles = [""] * len(row.index)
            for i, col in enumerate(row.index):
                if col == "Pass?":
                    styles[i] = f"background-color:{bg}; color:{NEUTRAL_FG}; font-weight:700;"
                elif col in ("Value", "Threshold"):
                    styles[i] = f"background-color:{NEUTRAL_BG}; color:{NEUTRAL_FG};"
                elif col == "Signal":
                    styles[i] = f"background-color:{NEUTRAL_BG}; color:{NEUTRAL_FG}; font-weight:600;"
                else:
                    styles[i] = f"background-color:{NEUTRAL_BG}; color:{NEUTRAL_FG};"
            return styles

        display_df = df_signals.drop(columns=["_pass_bool"]).copy()
        s = display_df.style.apply(row_style, axis=1)
        s = s.set_table_styles([
            {"selector": "th", "props": [("background-color", NEUTRAL_BG), ("color", NEUTRAL_FG), ("font-weight", "700")]},
            {"selector": "td", "props": [("border-color", "#444"), ("border-style", "solid"), ("border-width", "1px")]},
            {"selector": "table", "props": [("border-collapse", "collapse")]},
        ])
        return s

    st.dataframe(
        style_signals(df_signals.style),  # type: ignore
        use_container_width=True,
        hide_index=True,
    )

with right:
    st.markdown("### Business Classification & Routing")

    passed_count = outputs["passed_count"]
    infra_class = outputs["infra_class"]
    too_early_flag = outputs["too_early_flag"]
    routed_model = outputs["routed_model"]

    # Right panel: spreadsheet-like cards
    def info_row(label: str, value_text: str, status: Optional[bool] = None):
        bg = _passfail_bg(status) if status is not None else NEUTRAL_BG
        st.markdown(
            f"""
            <div style="background:{NEUTRAL_BG}; border-radius:10px; padding:10px 12px; margin-bottom:10px;">
              <div style="color:{NEUTRAL_FG}; font-weight:700; margin-bottom:6px;">{label}</div>
              <div style="background:{bg}; color:{NEUTRAL_FG}; border-radius:8px; padding:10px; font-weight:800; text-align:center;">
                {value_text}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    info_row("Infrastructure Signals Passed", f"{passed_count}", None)

    if infra_class is None:
        info_row("Infra Classification (3+ signals)", "N/A", None)
    else:
        info_row("Infra Classification (3+ signals)", _status_text(infra_class), infra_class)

    if too_early_flag is None:
        info_row("Too Early / Build Phase Flag", "N/A", None)
    else:
        # PASS means not too early; FAIL means too early
        info_row("Too Early / Build Phase Flag", _status_text(too_early_flag), too_early_flag)

    # Routed Model (string) — always shown
    # Color it green only when INFRASTRUCTURE_DCF is selected
    routed_is_infra = (routed_model == "INFRASTRUCTURE_DCF")
    info_row("Routed Model", routed_model, True if routed_is_infra else False)

    # Optional small transparency box (doesn't change required labels)
    with st.expander("Raw inputs (debug)"):
        raw = outputs.get("raw", {})
        st.write({
            "Revenue": _fmt_num(raw.get("revenue")),
            "Net Income": _fmt_num(raw.get("net_income")),
            "Operating Cash Flow (CFO)": _fmt_num(raw.get("cfo")),
            "CapEx": _fmt_num(raw.get("capex")),
            "FCF (CFO - CapEx)": _fmt_num(raw.get("fcf")),
        })