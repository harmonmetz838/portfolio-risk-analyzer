"""Unit tests for portfolio calculations, using small hand-checkable examples.

Run:  python -m pytest
"""

import numpy as np
import pandas as pd
import pytest

from portfolio import data, metrics

DATES = pd.bdate_range("2024-01-01", periods=5)


def test_normalize_weights():
    w = metrics.normalize_weights({"A": 4000, "B": 3500, "C": 2500})
    assert w.round(4).tolist() == [0.40, 0.35, 0.25]
    with pytest.raises(ValueError):
        metrics.normalize_weights({"A": 0, "B": 0})
    with pytest.raises(ValueError):
        metrics.normalize_weights({"A": -1, "B": 2})


def test_buy_and_hold_value():
    prices = pd.DataFrame({"A": [10, 20], "B": [50, 50]}, index=DATES[:2])
    amounts = pd.Series({"A": 100.0, "B": 100.0})
    # A doubles: 10 shares -> $200; B flat -> $100
    assert metrics.portfolio_value(prices, amounts).tolist() == [200.0, 300.0]


def test_max_drawdown():
    v = pd.Series([100, 120, 90, 130, 104], index=DATES)
    # worst fall: 120 -> 90 = -25%  (130 -> 104 is only -20%)
    assert metrics.max_drawdown(v) == pytest.approx(-0.25)


def test_annualized_return_one_year():
    idx = pd.bdate_range("2024-01-01", periods=253)  # 252 return periods = 1 year
    v = pd.Series(np.linspace(100, 110, 253), index=idx)
    assert metrics.annualized_return(v) == pytest.approx(0.10)


def test_volatility_and_sharpe_match_formula():
    rng = np.random.default_rng(0)
    r = pd.Series(rng.normal(0.0005, 0.01, 1000))
    assert metrics.annualized_volatility(r) == pytest.approx(r.std() * np.sqrt(252))
    rf = 0.04
    expected = (r - rf / 252).mean() / r.std() * np.sqrt(252)
    assert metrics.sharpe_ratio(r, rf) == pytest.approx(expected)


def test_sharpe_zero_volatility_is_nan():
    assert np.isnan(metrics.sharpe_ratio(pd.Series([0.01] * 10), 0.0))


def test_beta():
    rng = np.random.default_rng(1)
    bench = pd.Series(rng.normal(0, 0.01, 500))
    assert metrics.beta(2 * bench, bench) == pytest.approx(2.0)
    assert metrics.beta(bench, bench) == pytest.approx(1.0)


def test_risk_contributions_sum_to_one_and_equal_for_identical_assets():
    rng = np.random.default_rng(2)
    rets = pd.DataFrame(rng.normal(0, 0.01, (500, 3)), columns=list("ABC"))
    rc = metrics.risk_contributions(rets, pd.Series({"A": 0.5, "B": 0.3, "C": 0.2}))
    assert rc.sum() == pytest.approx(1.0)
    same = pd.DataFrame({"A": rets["A"], "B": rets["A"]})
    rc2 = metrics.risk_contributions(same, pd.Series({"A": 0.5, "B": 0.5}))
    assert rc2.tolist() == pytest.approx([0.5, 0.5])


def test_clean_tickers():
    assert data.clean_tickers([" aapl", "MSFT", "aapl", ""]) == ["AAPL", "MSFT"]


def test_align_prices_drops_empty_and_short():
    idx = pd.bdate_range("2024-01-01", periods=40)
    df = pd.DataFrame({"A": range(40), "B": [np.nan] * 40}, index=idx, dtype=float)
    aligned, missing = data.align_prices(df)
    assert missing == ["B"] and list(aligned.columns) == ["A"]
    with pytest.raises(data.DataError):
        data.align_prices(df.iloc[:10])


def test_sample_dataset_loads():
    from datetime import date
    df = data.load_sample_prices(["AAPL", "SPY", "FAKE"], date(2023, 1, 1), date(2023, 12, 31))
    assert df["AAPL"].notna().all() and df["FAKE"].isna().all()
