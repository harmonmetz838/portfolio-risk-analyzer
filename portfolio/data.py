"""Data retrieval: historical prices, risk-free rate, latest quotes.

Sources
- Yahoo Finance (via the yfinance library): daily adjusted closing prices.
- FRED series DGS3MO (3-Month Treasury, constant maturity): risk-free rate.
- Finnhub /quote (optional, needs a free API key): latest price and daily change.
- data/sample_prices.csv: synthetic offline dataset used only when the user
  chooses "Sample data" (e.g. no internet). It is NOT real market data.

Every function raises DataError with a readable message instead of crashing,
so the app can show the message to the user.
"""

from __future__ import annotations

import io
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

SAMPLE_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_prices.csv"
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FINNHUB_QUOTE_URL = "https://finnhub.io/api/v1/quote"
TIMEOUT = 15


class DataError(Exception):
    """A user-facing data problem (bad ticker, API down, not enough history)."""


def clean_tickers(raw: list[str]) -> list[str]:
    """Upper-case, strip and de-duplicate tickers, preserving order."""
    seen, out = set(), []
    for t in raw:
        t = t.strip().upper()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def align_prices(prices: pd.DataFrame, min_rows: int = 30) -> tuple[pd.DataFrame, list[str]]:
    """Drop tickers with no data, keep dates where every ticker has a price.

    Returns (aligned_prices, list_of_tickers_with_no_data).
    """
    missing = [c for c in prices.columns if prices[c].dropna().empty]
    prices = prices.drop(columns=missing).dropna(how="any").sort_index()
    if len(prices) < min_rows:
        raise DataError(
            f"Only {len(prices)} days of overlapping price history were found; "
            f"at least {min_rows} are needed. Choose a longer period or tickers "
            "with longer trading histories."
        )
    return prices, missing


def fetch_prices_yahoo(tickers: list[str], start: date, end: date) -> pd.DataFrame:
    """Daily adjusted closing prices from Yahoo Finance, start and end inclusive."""
    import yfinance as yf  # imported here so sample mode works without it

    try:
        # yfinance treats `end` as exclusive, so ask for one day more
        raw = yf.download(tickers, start=start, end=end + timedelta(days=1),
                          auto_adjust=True, progress=False, threads=True)
    except Exception as exc:  # network errors, rate limits, etc.
        raise DataError(f"Could not reach Yahoo Finance: {exc}") from exc

    if raw is None or raw.empty:
        raise DataError("Yahoo Finance returned no data. Check the tickers, the "
                        "date range, and your internet connection.")

    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if not isinstance(close, pd.DataFrame):
        close = close.to_frame()
    if list(close.columns) == ["Close"]:  # single ticker, flat columns
        close.columns = tickers[:1]
    close.index = pd.to_datetime(close.index).tz_localize(None)
    close = close.loc[pd.Timestamp(start):pd.Timestamp(end)]
    # ensure every requested ticker has a column, even if empty
    close = close.reindex(columns=tickers)
    if close.dropna(how="all").empty:
        raise DataError("Yahoo Finance returned no prices for any ticker. Check the "
                        "tickers and your internet connection, or try again later.")
    return close


def load_sample_prices(tickers: list[str], start: date, end: date) -> pd.DataFrame:
    """Prices from the bundled synthetic dataset."""
    if not SAMPLE_PATH.exists():
        raise DataError("Sample dataset not found. Run scripts/make_sample_data.py.")
    df = pd.read_csv(SAMPLE_PATH, index_col=0, parse_dates=True)
    df = df.loc[pd.Timestamp(start):pd.Timestamp(end)]
    return df.reindex(columns=tickers)


def fetch_risk_free_rate() -> tuple[float, str]:
    """Latest 3-Month Treasury yield from FRED, as a decimal (0.045 = 4.5%).

    Uses FRED's public CSV download, which needs no API key.
    Returns (rate, observation_date).
    """
    try:
        resp = requests.get(FRED_CSV_URL, params={"id": "DGS3MO"}, timeout=TIMEOUT)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
    except Exception as exc:
        raise DataError(f"Could not download the risk-free rate from FRED: {exc}") from exc

    if df.shape[1] < 2:
        raise DataError("Unexpected FRED response format.")
    values = pd.to_numeric(df.iloc[:, 1], errors="coerce")  # FRED uses "." for missing
    valid = values.dropna()
    if valid.empty:
        raise DataError("FRED returned no valid observations for DGS3MO.")
    idx = valid.index[-1]
    return float(valid.iloc[-1]) / 100.0, str(df.iloc[idx, 0])


def fetch_finnhub_quotes(tickers: list[str], api_key: str) -> pd.DataFrame:
    """Latest price and daily change for each ticker from Finnhub's free /quote endpoint.

    Tickers Finnhub can't price (returns c == 0) are skipped. Never raises for a
    single bad ticker; raises DataError only if the key is rejected.
    """
    rows = []
    headers = {"X-Finnhub-Token": api_key}  # header keeps the key out of URLs/logs
    for t in tickers:
        try:
            resp = requests.get(FINNHUB_QUOTE_URL, params={"symbol": t},
                                headers=headers, timeout=TIMEOUT)
        except requests.RequestException:
            continue
        if resp.status_code in (401, 403):
            raise DataError("Finnhub rejected the API key (or this symbol needs a paid plan).")
        if resp.status_code == 429:
            raise DataError("Finnhub rate limit reached; wait a minute and retry.")
        if not resp.ok:
            continue
        q = resp.json() or {}
        if not q.get("c"):
            continue
        rows.append({
            "Ticker": t,
            "Price": q.get("c"),
            "Change": q.get("d"),
            "Change %": (q.get("dp") or 0) / 100.0,
            "Prev close": q.get("pc"),
        })
    return pd.DataFrame(rows)
