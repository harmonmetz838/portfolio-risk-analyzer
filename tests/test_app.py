"""Smoke tests: run the Streamlit app headlessly in offline sample mode.

Run:  python -m pytest
"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def run_sample_app():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.sidebar.radio[0].set_value("Sample data (synthetic, offline)").run()
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
