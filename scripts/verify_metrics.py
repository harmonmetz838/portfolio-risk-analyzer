"""Independent cross-check of the app's metrics against live data.

Part 1 (independent): downloads daily prices straight from Yahoo's chart API
with `requests` (not yfinance) and computes total return, annualized volatility
and max drawdown with plain Python. Nothing from portfolio/ is used here.

Part 2 (second source): checks SPY's closes against Nasdaq's historical-price
API, and rebuilds SPY's total return from Nasdaq closes plus Yahoo's dividend
history, to check Yahoo's dividend adjustment. Stooq was tried first but serves
a JavaScript bot check instead of data.

Part 3 (comparison): runs portfolio/metrics.py on the same prices, and runs the
app's own pipeline (portfolio/data.py via yfinance, with the same start/end
dates a user would type into the sidebar), then prints a side-by-side table.

Run:  python scripts/verify_metrics.py      (needs internet)
"""

from __future__ import annotations

import math
import sys
import warnings
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

TICKERS = ["SPY", "AAPL", "MSFT"]
START, END = date(2023, 10, 24), date(2026, 10, 22)  # both inclusive
TRADING_DAYS = 252
NY = ZoneInfo("America/New_York")
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
TIMEOUT = 30


# ---------------------------------------------------------------- downloads
def yahoo_chart(ticker: str) -> dict:
    """Daily close, adjusted close and dividends from Yahoo's chart API."""
    period1 = int(datetime.combine(START, time(0), NY).timestamp())
    period2 = int(datetime.combine(END + timedelta(days=1), time(0), NY).timestamp())
    resp = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
                        params={"period1": period1, "period2": period2, "interval": "1d",
                                "events": "div,split"},
                        headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    result = resp.json()["chart"]["result"][0]
    days = [datetime.fromtimestamp(ts, NY).date() for ts in result["timestamp"]]
    close = result["indicators"]["quote"][0]["close"]
    adj = result["indicators"]["adjclose"][0]["adjclose"]
    divs = {datetime.fromtimestamp(int(ts), NY).date(): d["amount"]
            for ts, d in result.get("events", {}).get("dividends", {}).items()}
    rows = [(d, c, a) for d, c, a in zip(days, close, adj)
            if START <= d <= END and c is not None and a is not None]
    return {"dates": [r[0] for r in rows], "close": [r[1] for r in rows],
            "adj": [r[2] for r in rows], "dividends": divs}


def nasdaq_closes(ticker: str, assetclass: str) -> dict[date, float]:
    """Unadjusted daily closes from Nasdaq's historical-price API."""
    resp = requests.get(f"https://api.nasdaq.com/api/quote/{ticker}/historical",
                        params={"assetclass": assetclass, "fromdate": START.isoformat(),
                                "todate": END.isoformat(), "limit": "5000"},
                        headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    rows = resp.json()["data"]["tradesTable"]["rows"]
    return {datetime.strptime(r["date"], "%m/%d/%Y").date():
            float(r["close"].replace("$", "").replace(",", "")) for r in rows}


# ---------------------------------------------------------------- metrics from scratch
def total_return(prices: list[float]) -> float:
    return prices[-1] / prices[0] - 1


def annualized_volatility(prices: list[float]) -> float:
    """Sample std (n - 1) of simple daily returns x sqrt(252)."""
    rets = [b / a - 1 for a, b in zip(prices, prices[1:])]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) * math.sqrt(TRADING_DAYS)


def max_drawdown(prices: list[float]) -> float:
    peak, worst = prices[0], 0.0
    for p in prices:
        peak = max(peak, p)
        worst = min(worst, p / peak - 1)
    return worst


def from_scratch(prices: list[float]) -> dict[str, float]:
    return {"Total return": total_return(prices),
            "Annualized volatility": annualized_volatility(prices),
            "Max drawdown": max_drawdown(prices)}


# ---------------------------------------------------------------- SPY second source
def cross_check_spy(spy: dict) -> None:
    print("## SPY: Yahoo vs Nasdaq\n")
    nasdaq = nasdaq_closes("SPY", "etf")
    yahoo = dict(zip(spy["dates"], spy["close"]))
    common = sorted(set(yahoo) & set(nasdaq))
    only_y, only_n = sorted(set(yahoo) - set(nasdaq)), sorted(set(nasdaq) - set(yahoo))
    diffs = [abs(yahoo[d] - nasdaq[d]) for d in common]
    worst = max(common, key=lambda d: abs(yahoo[d] - nasdaq[d]))
    off = [str(d) for d in common if abs(yahoo[d] - nasdaq[d]) > 0.01]
    print(f"- Trading days: Yahoo {len(yahoo)}, Nasdaq {len(nasdaq)}, in both {len(common)}"
          f" (only Yahoo: {only_y or 'none'}, only Nasdaq: {only_n or 'none'})")
    print(f"- Unadjusted close, |Yahoo - Nasdaq|: mean ${sum(diffs) / len(diffs):.4f}, "
          f"max ${max(diffs):.4f} on {worst} "
          f"(Yahoo {yahoo[worst]:.4f}, Nasdaq {nasdaq[worst]:.2f}); "
          f"days differing by more than 1 cent: {len(off)} ({', '.join(off) or 'none'})")

    # total return with dividends reinvested at the ex-date close, using Nasdaq prices
    shares = 1.0
    for d in common[1:]:
        if d in spy["dividends"]:
            shares += shares * spy["dividends"][d] / nasdaq[d]
    rebuilt = shares * nasdaq[common[-1]] / nasdaq[common[0]] - 1
    price_only = nasdaq[common[-1]] / nasdaq[common[0]] - 1
    adj = dict(zip(spy["dates"], spy["adj"]))
    yahoo_adj = adj[common[-1]] / adj[common[0]] - 1
    n_divs = sum(1 for d in spy["dividends"] if common[0] < d <= common[-1])
    print(f"- Total return, Nasdaq closes + {n_divs} Yahoo dividends reinvested: {rebuilt:.4%}")
    print(f"- Total return, Yahoo Adj Close: {yahoo_adj:.4%} "
          f"(difference {(yahoo_adj - rebuilt) * 1e4:+.2f} bp)")
    print(f"- Price-only return (Nasdaq, no dividends): {price_only:.4%}\n")


# ---------------------------------------------------------------- app comparison
def app_results(yahoo: dict[str, dict]) -> tuple[dict, dict, str]:
    """metrics.py on the same prices, and the app's full pipeline via yfinance."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import pandas as pd
    from portfolio import data, metrics

    def summarize(s: pd.Series) -> dict[str, float]:
        return {"Total return": metrics.total_return(s),
                "Annualized volatility": metrics.annualized_volatility(s.pct_change().dropna()),
                "Max drawdown": metrics.max_drawdown(s)}

    same = {t: summarize(pd.Series(y["adj"], index=pd.to_datetime(y["dates"])))
            for t, y in yahoo.items()}
    # silence yfinance's pandas deprecation noise; import it first, because on import
    # yfinance adds its own filter that would take priority over this one
    import yfinance  # noqa: F401
    warnings.filterwarnings("ignore", message="The inplace keyword", category=DeprecationWarning)
    prices, _ = data.align_prices(data.fetch_prices_yahoo(TICKERS, START, END))
    pipeline = {t: summarize(prices[t]) for t in TICKERS}
    span = f"{prices.index[0]:%Y-%m-%d} to {prices.index[-1]:%Y-%m-%d}, {len(prices)} days"
    return same, pipeline, span, prices.index[-1].date()


def main() -> None:
    yahoo = {t: yahoo_chart(t) for t in TICKERS}
    first = yahoo["SPY"]["dates"]
    print(f"# Metric cross-check, {first[0]} to {first[-1]} ({len(first)} trading days)\n")
    cross_check_spy(yahoo["SPY"])

    scratch = {t: from_scratch(y["adj"]) for t, y in yahoo.items()}
    same, pipeline, span, app_last = app_results(yahoo)
    print("## Side by side\n")
    print("A = from scratch (Yahoo chart API Adj Close, plain Python)")
    print("B = portfolio/metrics.py on the same prices as A")
    print(f"C = the app's pipeline: portfolio/data.py via yfinance + metrics.py ({span})\n")
    print("| Ticker | Metric | A: scratch | B: metrics.py | B − A (bp) | C: app | C − A (bp) |")
    print("|---|---|---:|---:|---:|---:|---:|")
    for t in TICKERS:
        for m in scratch[t]:
            a, b, c = scratch[t][m], same[t][m], pipeline[t][m]
            print(f"| {t} | {m} | {a:.4%} | {b:.4%} | {(b - a) * 1e4:+.4f} "
                  f"| {c:.4%} | {(c - a) * 1e4:+.2f} |")

    # C should equal the from-scratch numbers on C's own (shorter) date range
    gap = max(abs(from_scratch([p for d, p in zip(y["dates"], y["adj"]) if d <= app_last])[m]
                  - pipeline[t][m]) for t, y in yahoo.items() for m in scratch[t])
    print(f"\nFrom scratch on Yahoo chart prices through {app_last} vs C: "
          f"largest difference {gap * 1e4:.2f} bp")


if __name__ == "__main__":
    main()
