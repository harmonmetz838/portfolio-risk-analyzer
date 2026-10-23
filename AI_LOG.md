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
