import yfinance as yf
import pandas as pd


def get_financial_data(ticker: str):
    stock = yf.Ticker(ticker)

    income = stock.financials
    cashflow = stock.cashflow
    balance = stock.balance_sheet
    price_data = stock.history(period="1d")

    if price_data.empty:
        raise ValueError("Could not retrieve price data.")

    price = price_data["Close"].iloc[-1]

    return {
        "income": income,
        "cashflow": cashflow,
        "balance": balance,
        "price": price,
    }