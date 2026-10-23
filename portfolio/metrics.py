"""Portfolio performance and risk calculations.

All functions are pure (no network access) so they can be unit-tested.
Conventions:
- Prices are a DataFrame indexed by date, one column per ticker (adjusted close).
- Returns are simple daily returns.
- Annualization uses 252 trading days.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def normalize_weights(amounts: dict[str, float]) -> pd.Series:
    """Convert dollar amounts (or raw weights) into weights that sum to 1."""
    s = pd.Series(amounts, dtype=float)
    if (s < 0).any():
        raise ValueError("Amounts/weights cannot be negative.")
    total = s.sum()
    if total <= 0:
        raise ValueError("Total investment must be greater than zero.")
    return s / total


def daily_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Simple daily returns: r_t = P_t / P_{t-1} - 1."""
    return prices.pct_change().dropna(how="all")


def portfolio_value(prices: pd.DataFrame, amounts: pd.Series) -> pd.Series:
    """Buy-and-hold portfolio value.

    Each position buys amount_i / P_i,0 shares on the first date and holds them,
    so weights drift with prices (no rebalancing).
    """
    prices = prices[amounts.index]
    shares = amounts / prices.iloc[0]
    return (prices * shares).sum(axis=1)


def total_return(values: pd.Series) -> float:
    return float(values.iloc[-1] / values.iloc[0] - 1)


def annualized_return(values: pd.Series) -> float:
    """Compound annual growth rate based on number of trading-day observations."""
    n_periods = len(values) - 1
    if n_periods <= 0:
        return float("nan")
    growth = values.iloc[-1] / values.iloc[0]
    return float(growth ** (TRADING_DAYS / n_periods) - 1)


def annualized_volatility(returns: pd.Series) -> float:
    """Sample standard deviation of daily returns x sqrt(252)."""
    return float(returns.std(ddof=1) * np.sqrt(TRADING_DAYS))


def sharpe_ratio(returns: pd.Series, risk_free_annual: float) -> float:
    """Annualized Sharpe ratio using arithmetic excess returns.

    Sharpe = (mean daily excess return x 252) / (daily std x sqrt(252))
    where the daily risk-free rate is risk_free_annual / 252.
    """
    excess = returns - risk_free_annual / TRADING_DAYS
    sd = excess.std(ddof=1)
    if np.isnan(sd) or sd < 1e-12:  # flat series; tolerance absorbs float noise
        return float("nan")
    return float(excess.mean() / sd * np.sqrt(TRADING_DAYS))


def drawdown_series(values: pd.Series) -> pd.Series:
    """Percent decline from the running peak at each date (0 or negative)."""
    running_peak = values.cummax()
    return values / running_peak - 1


def max_drawdown(values: pd.Series) -> float:
    """Largest peak-to-trough decline (a negative number)."""
    return float(drawdown_series(values).min())


def beta(asset_returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """Cov(asset, benchmark) / Var(benchmark), on aligned dates."""
    df = pd.concat([asset_returns, benchmark_returns], axis=1).dropna()
    if len(df) < 2:
        return float("nan")
    var_b = df.iloc[:, 1].var(ddof=1)
    if var_b == 0:
        return float("nan")
    return float(df.iloc[:, 0].cov(df.iloc[:, 1]) / var_b)


def risk_contributions(returns: pd.DataFrame, weights: pd.Series) -> pd.Series:
    """Each holding's percentage contribution to portfolio variance.

    RC_i = w_i * (Cov @ w)_i / (w' Cov w). Contributions sum to 1.
    Shows concentration: a holding can contribute far more risk than its weight.
    """
    w = weights[returns.columns].values
    cov = returns.cov().values
    port_var = w @ cov @ w
    if port_var == 0:
        return pd.Series(np.nan, index=returns.columns)
    rc = w * (cov @ w) / port_var
    return pd.Series(rc, index=returns.columns)


def summarize(values: pd.Series, risk_free_annual: float,
              benchmark_values: pd.Series | None = None) -> dict:
    """Bundle the headline metrics for one value series."""
    rets = values.pct_change().dropna()
    out = {
        "Total return": total_return(values),
        "Annualized return": annualized_return(values),
        "Annualized volatility": annualized_volatility(rets),
        "Sharpe ratio": sharpe_ratio(rets, risk_free_annual),
        "Max drawdown": max_drawdown(values),
    }
    if benchmark_values is not None:
        out["Beta vs benchmark"] = beta(rets, benchmark_values.pct_change().dropna())
    return out
