import numpy as np


def calculate_owner_earnings(net_income, da, capex):
    return net_income + da - abs(capex)
    """
    Owner Earnings v1:
    Net Income
    + Depreciation & Amortization
    - Total CapEx
    """

    if net_income is None or da is None or capex is None:
        raise ValueError("Missing required inputs for Owner Earnings")

    return net_income + da - abs(capex)


def simple_dcf(owner_earnings, growth=0.03, discount=0.10, years=5):
    """
    Very conservative 5-year DCF with flat growth.
    """

    cash_flows = []

    for year in range(1, years + 1):
        cf = owner_earnings * ((1 + growth) ** year)
        discounted = cf / ((1 + discount) ** year)
        cash_flows.append(discounted)

    terminal_value = (
        owner_earnings * ((1 + growth) ** years) * (1 + growth)
        / (discount - growth)
    )

    discounted_terminal = terminal_value / ((1 + discount) ** years)

    return sum(cash_flows) + discounted_terminal