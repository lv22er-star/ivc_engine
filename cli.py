import logging
from models.oe_dcf import calculate_owner_earnings
from data.fmp_client import get_financial_data

logging.basicConfig(level=logging.INFO)


def safe_get(df, labels, default=0):
    """Get latest value for the first matching label."""
    if isinstance(labels, str):
        labels = [labels]
    for label in labels:
        if label in df.index:
            try:
                return df.loc[label].iloc[0]
            except:
                pass
    return default


def get_series(df, labels):
    """Get full historical Series (latest -> oldest) for the first matching label."""
    if isinstance(labels, str):
        labels = [labels]
    for label in labels:
        if label in df.index:
            try:
                return df.loc[label].dropna()
            except:
                pass
    return None


def calculate_cagr(series):
    """
    Generic CAGR for a pandas Series ordered latest -> oldest.
    Uses all available periods (needs >=2).
    """
    if series is None:
        return 0

    series = series.dropna()
    n = len(series)
    if n < 2:
        return 0

    latest = series.iloc[0]
    oldest = series.iloc[n - 1]

    if oldest <= 0:
        return 0

    periods = n - 1
    return (latest / oldest) ** (1 / periods) - 1


def get_capex_outflow_latest(cashflow_df):
    capex_raw = safe_get(cashflow_df, ["Capital Expenditure", "Capital Expenditures"], 0)
    return abs(capex_raw)


def get_capex_outflow_series(cashflow_df):
    capex_series = get_series(cashflow_df, ["Capital Expenditure", "Capital Expenditures"])
    if capex_series is None:
        return None
    return capex_series.abs()


def get_da_latest(income_df, cashflow_df):
    da = safe_get(
        income_df,
        ["Depreciation & Amortization", "Depreciation And Amortization", "Depreciation"],
        None,
    )
    if not da:
        da = safe_get(
            cashflow_df,
            ["Depreciation & Amortization", "Depreciation And Amortization", "Depreciation"],
            0,
        )
    return da


def get_da_series(income_df, cashflow_df):
    # Try income statement first
    da_series = get_series(
        income_df,
        ["Depreciation & Amortization", "Depreciation And Amortization", "Depreciation"],
    )
    # Fallback to cash flow
    if da_series is None or len(da_series) < 2:
        da_series = get_series(
            cashflow_df,
            ["Depreciation & Amortization", "Depreciation And Amortization", "Depreciation"],
        )
    return da_series


def get_shares_latest(balance_df, income_df):
    shares = safe_get(
        balance_df,
        ["Ordinary Shares Number", "Share Issued", "Common Stock Shares Outstanding"],
        None,
    )
    if not shares:
        shares = safe_get(
            income_df,
            ["Weighted Average Shares Outstanding", "Weighted Average Shares Outstanding Diluted"],
            0,
        )
    return shares


def get_shares_series(balance_df, income_df):
    # Prefer balance sheet share count
    shares_series = get_series(
        balance_df,
        ["Ordinary Shares Number", "Share Issued", "Common Stock Shares Outstanding"],
    )
    # Fallback to weighted average shares
    if shares_series is None or len(shares_series) < 2:
        shares_series = get_series(
            income_df,
            ["Weighted Average Shares Outstanding", "Weighted Average Shares Outstanding Diluted"],
        )
    return shares_series


def suggest_multiple(growth):
    # Conservative tiering (same as before)
    if growth < 0.02:
        return 12
    elif growth < 0.05:
        return 15
    elif growth < 0.10:
        return 18
    elif growth < 0.15:
        return 22
    else:
        return 25


def align_common_years(*series_list):
    """
    Keep only years/columns common across all series.
    Returns list of aligned series (same index).
    """
    valid = [s for s in series_list if s is not None and len(s) > 0]
    if len(valid) != len(series_list):
        return None

    common_index = valid[0].index
    for s in valid[1:]:
        common_index = common_index.intersection(s.index)

    if len(common_index) < 2:
        return None

    aligned = [s.loc[common_index].dropna() for s in series_list]
    # Ensure still >=2 after dropna
    if any(len(s) < 2 for s in aligned):
        return None

    return aligned


def main():
    ticker = input("Enter ticker: ").strip().upper()
    print("\nPulling financial data...\n")

    data = get_financial_data(ticker)

    income = data["income"]
    cashflow = data["cashflow"]
    balance = data["balance"]
    price = data["price"]

    # Latest snapshot metrics
    revenue_latest = safe_get(income, ["Total Revenue", "Revenue", "Operating Revenue"], "Not Found")
    net_income_latest = safe_get(income, ["Net Income", "Net Income Common Stockholders"], 0)
    da_latest = get_da_latest(income, cashflow)
    capex_outflow_latest = get_capex_outflow_latest(cashflow)
    shares_latest = get_shares_latest(balance, income)

    owner_earnings_latest = calculate_owner_earnings(net_income_latest, da_latest, capex_outflow_latest)
    oe_per_share_latest = owner_earnings_latest / shares_latest if shares_latest else 0

    # CAGR building blocks (series)
    revenue_series = get_series(income, ["Total Revenue", "Revenue", "Operating Revenue"])
    net_income_series = get_series(income, ["Net Income", "Net Income Common Stockholders"])

    revenue_cagr = calculate_cagr(revenue_series)
    net_income_cagr = calculate_cagr(net_income_series)

    # Owner Earnings per Share series CAGR (the “real” growth signal)
    da_series = get_da_series(income, cashflow)
    capex_outflow_series = get_capex_outflow_series(cashflow)
    shares_series = get_shares_series(balance, income)

    oe_ps_cagr = 0
    years_used_for_oeps = 0

    aligned = align_common_years(net_income_series, da_series, capex_outflow_series, shares_series)
    if aligned is not None:
        ni_s, da_s, capex_s, sh_s = aligned

        # OE by year (all positive/negative handled by capex_s already abs)
        oe_series = ni_s + da_s - capex_s

        # OE per share by year
        oe_per_share_series = oe_series / sh_s

        oe_per_share_series = oe_per_share_series.dropna()
        years_used_for_oeps = len(oe_per_share_series)
        oe_ps_cagr = calculate_cagr(oe_per_share_series)

    # Use OE/share CAGR for multiple suggestion (fallback to blended if OE/share not available)
    blended_growth = (revenue_cagr + net_income_cagr) / 2
    growth_driver = oe_ps_cagr if oe_ps_cagr > 0 else blended_growth
    growth_driver_name = "OE/Share CAGR" if oe_ps_cagr > 0 else "Blended Growth (fallback)"

    suggested_multiple = suggest_multiple(growth_driver)

    intrinsic_value = oe_per_share_latest * suggested_multiple
    discount_pct = ((intrinsic_value - price) / price) * 100 if intrinsic_value else 0

    # Output
    print("Latest Revenue:", revenue_latest)
    print("Latest Net Income:", net_income_latest)
    print("Latest D&A:", da_latest)
    print("Latest CapEx (outflow):", capex_outflow_latest)
    print("Shares Outstanding:", shares_latest)
    print("Current Price:", price)
    print("Owner Earnings:", owner_earnings_latest)
    print("Owner Earnings Per Share:", oe_per_share_latest)

    print("\nRevenue CAGR:", revenue_cagr)
    print("Net Income CAGR:", net_income_cagr)
    print("Blended Growth:", blended_growth)

    print("\nOE/Share CAGR:", oe_ps_cagr)
    print("OE/Share Years Used:", years_used_for_oeps)

    print("\nMultiple Driver Used:", growth_driver_name)
    print("Suggested Multiple:", suggested_multiple)
    print("Intrinsic Value Per Share:", intrinsic_value)
    print("Upside / Downside (%):", discount_pct)

    print("\nData pull successful.\n")


if __name__ == "__main__":
    main()