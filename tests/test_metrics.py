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


def test_rebalanced_value_monthly_resets_to_target_weights():
    idx = pd.to_datetime(["2024-01-30", "2024-01-31", "2024-02-01", "2024-02-02"])
    prices = pd.DataFrame({"A": [10, 20, 20, 40], "B": [10, 10, 10, 10]}, index=idx)
    amounts = pd.Series({"A": 50.0, "B": 50.0})
    # Jan 31: A doubles -> 100 + 50 = 150. Feb 1 (new month): rebalance to 75/75.
    # Feb 2: A doubles again -> 150 + 75 = 225 (buy-and-hold would be 200 + 50 = 250)
    v = metrics.rebalanced_value(prices, amounts, "monthly")
    assert v.tolist() == pytest.approx([100.0, 150.0, 150.0, 225.0])
    assert metrics.portfolio_value(prices, amounts).iloc[-1] == pytest.approx(250.0)


def test_rebalanced_value_quarterly_ignores_month_boundaries():
    idx = pd.to_datetime(["2024-01-31", "2024-02-01", "2024-03-29", "2024-04-01", "2024-04-02"])
    prices = pd.DataFrame({"A": [10, 20, 20, 20, 40], "B": [10, 10, 10, 10, 10]}, index=idx)
    amounts = pd.Series({"A": 30.0, "B": 70.0})
    quarterly = metrics.rebalanced_value(prices, amounts, "quarterly")
    buy_hold = metrics.portfolio_value(prices, amounts)
    # no rebalance in February or March, so it matches buy-and-hold until April
    assert quarterly.iloc[:4].tolist() == pytest.approx(buy_hold.iloc[:4].tolist())
    # Apr 1: 130 re-split 30/70 -> A 39, B 91; Apr 2: A doubles -> 78 + 91 = 169
    assert quarterly.iloc[-1] == pytest.approx(169.0)


def test_rebalanced_value_equals_buy_and_hold_without_rebalance_dates():
    prices = pd.DataFrame({"A": [10, 12, 9, 15, 11], "B": [5, 5, 6, 4, 7]}, index=DATES)
    amounts = pd.Series({"A": 60.0, "B": 40.0})  # DATES are all in January 2024
    assert metrics.rebalanced_value(prices, amounts, "monthly").tolist() == pytest.approx(
        metrics.portfolio_value(prices, amounts).tolist())


def test_rebalanced_value_rejects_unknown_freq():
    prices = pd.DataFrame({"A": [10, 11], "B": [5, 5]}, index=DATES[:2])
    with pytest.raises(ValueError):
        metrics.rebalanced_value(prices, pd.Series({"A": 1.0, "B": 1.0}), "weekly")


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


def test_fetch_prices_yahoo_includes_end_date(monkeypatch):
    """yfinance's `end` is exclusive; fetch_prices_yahoo must include the end date."""
    import sys
    import types
    from datetime import date

    calls = {}

    def fake_download(tickers, start, end, **kwargs):
        calls.update(start=start, end=end)
        # like Yahoo, return every trading day from start up to (not including) end,
        # plus one extra row after it to check that nothing past `end` slips through
        idx = pd.bdate_range(start, end)
        cols = pd.MultiIndex.from_product([["Close"], tickers])
        return pd.DataFrame(1.0, index=idx, columns=cols)

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(download=fake_download))
    df = data.fetch_prices_yahoo(["AAA", "BBB"], date(2026, 10, 19), date(2026, 10, 22))
    assert calls == {"start": date(2026, 10, 19), "end": date(2026, 10, 23)}
    assert df.index[0] == pd.Timestamp("2026-10-19")
    assert df.index[-1] == pd.Timestamp("2026-10-22")  # end date included, nothing after
    assert list(df.columns) == ["AAA", "BBB"]
