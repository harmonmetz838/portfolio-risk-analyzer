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
