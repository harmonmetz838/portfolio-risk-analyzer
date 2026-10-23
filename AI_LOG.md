# AI Coding Agent Log

## 2026-10-23 — Distinct portfolio/benchmark colors and line-based drawdown chart

**Prompt**

> In app.py, give the portfolio and benchmark clearly different colors in all charts (e.g. orange vs gray), and make the drawdown chart use lines instead of overlapping filled areas.

**Changes** (commit `580c624`, `app.py`)

- Added `PORTFOLIO_COLOR` (orange, `#F28C28`) and `BENCHMARK_COLOR` (gray, `#8C8C8C`) constants.
- Applied them through `color_discrete_map` to both charts that show the portfolio and benchmark: growth of the portfolio vs benchmark, and drawdown.
- Switched the drawdown chart from `px.area` with `fill="tozeroy"` to `px.line`.
- Left the allocation, correlation and pie charts unchanged, since they show individual holdings rather than the portfolio vs benchmark.

**Verification**

- Automated: `.venv/bin/python -m pytest` passed all 14 tests.
- Manual: I checked the charts in the browser.

## 2026-10-23 — Monthly/quarterly rebalancing option

**Prompt**

> Add a sidebar option to rebalance the portfolio monthly or quarterly back to target weights, in addition to buy-and-hold. Show both on the growth chart and add unit tests for the rebalancing calculation.

**Changes** (commit `e92cce5`)

- `portfolio/metrics.py`: added `rebalanced_value(prices, amounts, freq)` for `"monthly"` or `"quarterly"` rebalancing. At the close of the first trading day of each new month/quarter, the total value is re-split by the starting (target) weights. No trading costs.
- `app.py`:
  - Added a "Rebalancing" sidebar option: buy and hold (default), monthly, or quarterly.
  - With rebalancing on, the growth chart shows the rebalanced portfolio (solid orange) next to buy-and-hold (dashed dark orange) and the benchmark (gray).
  - KPIs, the drawdown chart, the metrics table, the interpretation and the results caption follow the selected option.
  - The allocation chart's ending-weight bar stays buy-and-hold and is labelled "Ending weight (buy and hold)" when rebalancing is on.
  - Added the rebalancing rule to the methodology section.
- `README.md`: added the rebalancing feature and formula.
- Tests:
  - `tests/test_metrics.py`: four unit tests with hand-checked values (monthly reset, quarterly ignores month ends, no rebalance dates equals buy-and-hold, unknown frequency raises an error).
  - `tests/test_app.py`: a smoke test that the quarterly option runs without errors.

**Verification**

- Automated: `.venv/bin/python -m pytest` passed all 19 tests.
- Manual: I checked it in the browser. Monthly and quarterly both show the rebalanced line next to buy-and-hold, and they stay close as expected.

## 2026-10-23 — App tests run fully offline

**Prompt**

> The app tests try to download live data before switching to sample mode, so they depend on the internet. Make the tests run fully offline, then run them and commit with a log entry.

**Changes** (commit `5018d19`)

- `app.py`: gave the "Price source" radio `key="source"` so tests can choose sample mode before the app's first run. No change for users.
- `tests/test_app.py`:
  - `run_sample_app()` sets `session_state["source"]` to sample mode before the first `run()`, instead of running once in live mode and then switching.
  - New autouse `no_network` fixture: blocks `socket.getaddrinfo` and `socket.socket.connect`, clears `FINNHUB_API_KEY` so live quotes can't load, and fails a test if it tried to use the network.

**Verification**

- Before the fix, a run with network blocked showed the app tests making 4 connection attempts to Yahoo Finance. They passed only because nothing checked the first (live-mode) run.
- After the fix, `.venv/bin/python -m pytest` passed all 19 tests with network blocked. The 17 yfinance deprecation warnings are gone because yfinance no longer runs.
- Check that the guard works: temporarily restoring the old live-mode first run made all 4 app tests fail with "app tried to use the network".

## 2026-10-23 — Independent metric cross-check (automated, run by Claude Code)

**Prompt**

> Independently verify the app's numbers. Without using the app's own functions in portfolio/, write a short standalone script that downloads SPY, AAPL and MSFT adjusted closes for Oct 24, 2023 – Oct 22, 2026 and computes, from scratch, each ticker's total return, annualized volatility and max drawdown. If possible, cross-check SPY's prices against a second source (e.g. Stooq). Compare the results with what portfolio/metrics.py produces and show me a side-by-side table. Explain any differences. Save the script as scripts/verify_metrics.py, add an AI_LOG.md entry saying this was an automated cross-check run by Claude Code, and commit.

**Changes** (commit `9e7aef8`)

- New `scripts/verify_metrics.py` (needs internet; run with `.venv/bin/python scripts/verify_metrics.py`):
  - Downloads daily prices from Yahoo's chart API with `requests`, not yfinance, and computes the three metrics in plain Python, without `portfolio/`.
  - Cross-checks SPY against Nasdaq's historical-price API. Stooq was tried first but serves a JavaScript bot check instead of data.
  - Compares the results with `portfolio/metrics.py` on the same prices, and with the app's own pipeline (`portfolio/data.py` via yfinance, using the same start/end dates a user would enter).

**Verification**

This was an automated cross-check run by Claude Code on 2026-10-23, not a manual check. Results for 2023-10-24 to 2026-10-22 (752 trading days):

| Ticker | Metric | From scratch | metrics.py, same prices | App pipeline |
|---|---|---:|---:|---:|
| SPY | Total return | 86.99% | 86.99% | 89.23% |
| SPY | Annualized volatility | 15.25% | 15.25% | 15.24% |
| SPY | Max drawdown | -18.76% | -18.76% | -18.76% |
| AAPL | Total return | 103.49% | 103.49% | 101.02% |
| AAPL | Annualized volatility | 26.84% | 26.84% | 26.85% |
| AAPL | Max drawdown | -33.36% | -33.36% | -33.36% |
| MSFT | Total return | 61.34% | 61.34% | 65.02% |
| MSFT | Annualized volatility | 26.30% | 26.30% | 26.28% |
| MSFT | Max drawdown | -34.50% | -34.50% | -34.50% |

- **`metrics.py` formulas:** match the from-scratch numbers exactly (0.0000 bp difference on every metric).
- **App pipeline:** stops at 2026-10-21 (751 days) because yfinance treats `end` as exclusive, so the end date entered in the sidebar is left out. That one missing day explains every difference in the last column: on the same 751 days, the from-scratch numbers match the app to 0.00 bp. Not fixed yet.
- **SPY second source (Nasdaq):** same 752 trading days. Unadjusted closes agree to within 1 cent on every day except 2026-04-20 (Yahoo 708.72, Nasdaq 710.14). It isn't known which source is right that day.
- **Dividend adjustment:** rebuilding SPY's total return from Nasdaq closes plus Yahoo's 12 dividends gives 86.99%, within 0.5 bp of Yahoo's Adj Close. The price-only return is 80.34%, so dividends add about 6.7 points.
- `.venv/bin/python -m pytest` still passes all 19 tests.
