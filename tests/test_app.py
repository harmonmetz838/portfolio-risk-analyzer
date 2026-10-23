"""Smoke tests: run the Streamlit app headlessly in offline sample mode.

Network access is blocked for every test here, so they pass without internet
and fail if the app tries to download anything in sample mode.

Run:  python -m pytest
"""

import socket
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    attempts = []

    def blocked(*args, **kwargs):
        attempts.append(args)
        raise OSError("network access is blocked in tests")

    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)  # no live quotes
    yield
    assert not attempts, f"app tried to use the network: {attempts[:3]}"


def run_sample_app():
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["source"] = "Sample data (synthetic, offline)"  # before the first run
    at.run()
    return at


def test_app_runs_in_sample_mode():
    at = run_sample_app()
    assert not at.exception
    assert not at.error
    assert len(at.metric) == 5
    assert any("Sharpe" in m.label for m in at.metric)


def test_bad_benchmark_shows_error_not_crash():
    at = run_sample_app()
    at.sidebar.text_input[0].set_value("NOTATICKER").run()
    assert not at.exception
    assert any("benchmark" in e.value.lower() for e in at.error)


def test_bad_dates_show_error():
    from datetime import date
    at = run_sample_app()
    at.sidebar.date_input[0].set_value(date(2025, 6, 1))
    at.sidebar.date_input[1].set_value(date(2025, 1, 1)).run()
    assert not at.exception
    assert any("start date" in e.value.lower() for e in at.error)


def test_rebalancing_option_runs():
    at = run_sample_app()
    at.sidebar.radio[1].set_value("Rebalance quarterly").run()
    assert not at.exception
    assert not at.error
    assert len(at.metric) == 5


def run_live_app_offline(monkeypatch):
    """Live mode with the downloads replaced by fakes; returns (app, requested ranges)."""
    from datetime import date

    import numpy as np
    import pandas as pd
    import streamlit as st

    from portfolio import data

    requests = []

    def fake_prices(tickers, start, end):
        requests.append((start, end))
        idx = pd.bdate_range(start, end)
        rng = np.random.default_rng(0)
        walk = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, (len(idx), len(tickers))), axis=0))
        return pd.DataFrame(walk, index=idx, columns=tickers)

    monkeypatch.setattr(data, "fetch_prices_yahoo", fake_prices)
    monkeypatch.setattr(data, "fetch_risk_free_rate", lambda: (0.04, date(2026, 1, 1)))
    st.cache_data.clear()  # make sure the fakes are actually called
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    return at, requests


def test_preset_period_ends_yesterday(monkeypatch):
    from datetime import date, timedelta
    at, requests = run_live_app_offline(monkeypatch)
    assert not at.exception and not at.error
    today = date.today()
    # default preset "3 years": same days as before the fix, never today's partial prices
    assert requests[-1] == (today - timedelta(days=3 * 365), today - timedelta(days=1))


def test_custom_range_requests_chosen_end_date(monkeypatch):
    from datetime import date, timedelta
    at, requests = run_live_app_offline(monkeypatch)
    at.sidebar.selectbox[0].set_value("Custom").run()
    end_input = at.sidebar.date_input[1]
    assert end_input.value == date.today() - timedelta(days=1)  # default end is yesterday
    assert end_input.max == date.today() - timedelta(days=1)    # today can't be chosen
    at.sidebar.date_input[0].set_value(date(2023, 10, 24))
    end_input.set_value(date(2026, 10, 22)).run()
    assert not at.exception and not at.error
    assert requests[-1] == (date(2023, 10, 24), date(2026, 10, 22))
