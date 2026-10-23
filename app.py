"""Portfolio Risk Analyzer -- Streamlit app.

Run:  streamlit run app.py
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from portfolio import data, metrics

st.set_page_config(page_title="Portfolio Risk Analyzer", page_icon="📊", layout="wide")

DEFAULT_HOLDINGS = pd.DataFrame(
    {"Ticker": ["AAPL", "MSFT", "SPY"], "Amount": [4000.0, 3500.0, 2500.0]}
)
PERIODS = {"1 year": 365, "3 years": 3 * 365, "5 years": 5 * 365}
PCT_ROWS = ["Total return", "Annualized return", "Annualized volatility", "Max drawdown"]
PORTFOLIO_COLOR = "#F28C28"  # orange
BENCHMARK_COLOR = "#8C8C8C"  # gray
BUY_HOLD_COLOR = "#7A3E00"  # dark orange, buy-and-hold when a rebalanced portfolio is shown
REBALANCE_OPTIONS = {"Buy and hold (no rebalancing)": None,
                     "Rebalance monthly": "monthly", "Rebalance quarterly": "quarterly"}


# ---------------------------------------------------------------- helpers
def get_finnhub_key() -> str:
    """API key from Streamlit secrets or environment; never hard-coded."""
    try:
        key = st.secrets.get("FINNHUB_API_KEY", "")
    except Exception:  # no secrets.toml present
        key = ""
    return key or os.environ.get("FINNHUB_API_KEY", "")


@st.cache_data(ttl=3600, show_spinner=False)
def load_prices(source: str, tickers: tuple[str, ...], start: date, end: date) -> pd.DataFrame:
    if source == "sample":
        return data.load_sample_prices(list(tickers), start, end)
    return data.fetch_prices_yahoo(list(tickers), start, end)


@st.cache_data(ttl=3600, show_spinner=False)
def load_risk_free() -> tuple[float, str]:
    return data.fetch_risk_free_rate()


@st.cache_data(ttl=300, show_spinner=False)
def load_quotes(tickers: tuple[str, ...], key: str) -> pd.DataFrame:
    return data.fetch_finnhub_quotes(list(tickers), key)


def fmt_metric(name: str, value: float) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "n/a"
    return f"{value:.2%}" if name in PCT_ROWS else f"{value:.2f}"


# ---------------------------------------------------------------- sidebar
st.sidebar.header("1. Data")
source_label = st.sidebar.radio(
    "Price source",
    ["Live (Yahoo Finance)", "Sample data (synthetic, offline)"],
    help="Sample data is simulated and is NOT real market data. Use it only "
         "if you have no internet connection.",
)
source = "sample" if source_label.startswith("Sample") else "live"

if source == "live":
    period_label = st.sidebar.selectbox("Lookback period", list(PERIODS) + ["Custom"], index=1)
    if period_label == "Custom":
        start = st.sidebar.date_input("Start", date.today() - timedelta(days=3 * 365))
        end = st.sidebar.date_input("End", date.today())
    else:
        end = date.today()
        start = end - timedelta(days=PERIODS[period_label])
else:
    start = st.sidebar.date_input("Start", date(2023, 1, 1),
                                  min_value=date(2021, 1, 4), max_value=date(2025, 12, 31))
    end = st.sidebar.date_input("End", date(2025, 12, 31),
                                min_value=date(2021, 1, 4), max_value=date(2025, 12, 31))
    st.sidebar.caption("Sample tickers: AAPL, MSFT, NVDA, JNJ, XOM, TLT, GLD, SPY")

benchmark = st.sidebar.text_input("Benchmark ticker", "SPY").strip().upper()
rebalance_label = st.sidebar.radio(
    "Rebalancing", list(REBALANCE_OPTIONS),
    help="Rebalancing resets holdings to the target weights at the start of each "
         "month or quarter. Buy and hold lets weights drift with prices.")
rebalance = REBALANCE_OPTIONS[rebalance_label]

st.sidebar.header("2. Risk-free rate")
use_fred = st.sidebar.checkbox("Use latest 3-month T-bill yield (FRED)", value=(source == "live"))
manual_rf = st.sidebar.number_input("Manual risk-free rate (%)", 0.0, 20.0, 4.0, 0.1) / 100

st.sidebar.header("3. Finnhub (optional)")
finnhub_key = get_finnhub_key()
if not finnhub_key:
    finnhub_key = st.sidebar.text_input(
        "Finnhub API key", type="password",
        help="Free key from finnhub.io. Used only for latest quotes; kept in this "
             "session only. Better: put it in .streamlit/secrets.toml.")
else:
    st.sidebar.success("Finnhub key loaded from secrets/environment.")

# ---------------------------------------------------------------- header
st.title("📊 Portfolio Risk Analyzer")
st.markdown(
    "Investors often underestimate how much risk comes from **concentration** in a "
    "few holdings. Enter a portfolio below to measure its return, volatility, "
    "Sharpe ratio and maximum drawdown, see which holdings drive its risk, and "
    "compare it with a benchmark."
)
if source == "sample":
    st.warning("⚠️ **Sample mode:** prices are synthetic (simulated) and do not reflect "
               "real market history. Switch to Live for real data.")

# ---------------------------------------------------------------- inputs
st.subheader("Portfolio")
c1, c2 = st.columns([2, 1])
with c2:
    input_mode = st.radio("Enter positions as", ["Dollar amounts", "Weights (%)"])
    st.caption("Add or delete rows in the table. At least 3 holdings are required. "
               "Change the numbers to see how risk shifts with the allocation.")
with c1:
    default = DEFAULT_HOLDINGS.copy()
    if input_mode == "Weights (%)":
        default["Amount"] = [40.0, 35.0, 25.0]
    holdings = st.data_editor(
        default, num_rows="dynamic", width="stretch", key=f"holdings_{input_mode}",
        column_config={
            "Ticker": st.column_config.TextColumn(required=True),
            "Amount": st.column_config.NumberColumn(
                "Amount ($)" if input_mode == "Dollar amounts" else "Weight (%)",
                min_value=0.0, required=True),
        },
    )

# ---------------------------------------------------------------- validate inputs
holdings = holdings.dropna()
holdings["Ticker"] = holdings["Ticker"].astype(str).str.strip().str.upper()
holdings = holdings[holdings["Ticker"] != ""]
holdings = holdings.groupby("Ticker", sort=False, as_index=False)["Amount"].sum()
holdings = holdings[holdings["Amount"] > 0]

if len(holdings) < 3:
    st.error("Enter at least three holdings with amounts greater than zero.")
    st.stop()
if start >= end:
    st.error("The start date must be before the end date.")
    st.stop()
if not benchmark:
    st.error("Enter a benchmark ticker (e.g. SPY).")
    st.stop()
if input_mode == "Weights (%)" and abs(holdings["Amount"].sum() - 100) > 0.01:
    st.info(f"Weights add up to {holdings['Amount'].sum():.1f}%, so they were rescaled to 100%.")

tickers = data.clean_tickers(holdings["Ticker"].tolist())
all_tickers = data.clean_tickers(tickers + [benchmark])

# ---------------------------------------------------------------- load data
with st.spinner("Downloading prices..."):
    try:
        raw_prices = load_prices(source, tuple(all_tickers), start, end)
        prices, missing = data.align_prices(raw_prices)
    except data.DataError as exc:
        st.error(str(exc))
        st.stop()

if benchmark in missing:
    st.error(f"No price data found for benchmark '{benchmark}'. Check the ticker.")
    st.stop()
if missing:
    st.warning("No data found for: " + ", ".join(missing) + ". These tickers were "
               "removed (check spelling; some symbols need an exchange suffix, e.g. SHOP.TO).")
valid = [t for t in tickers if t not in missing]
if len(valid) < 3:
    st.error("Fewer than three holdings have price data. Fix or replace the tickers above.")
    st.stop()

first_dates = raw_prices[all_tickers].apply(lambda s: s.first_valid_index())
if prices.index[0] > pd.Timestamp(start) + pd.Timedelta(days=7):
    late = first_dates[first_dates == first_dates.max()].index.tolist()
    st.info(f"Analysis starts {prices.index[0]:%Y-%m-%d}, the first date with prices for "
            f"every ticker (limited by {', '.join(late)}).")

# risk-free rate
rf, rf_note = manual_rf, f"manual input ({manual_rf:.2%})"
if use_fred:
    try:
        rf, rf_date = load_risk_free()
        rf_note = f"FRED DGS3MO, {rf:.2%} as of {rf_date}"
    except data.DataError as exc:
        st.warning(f"{exc} Using the manual rate of {manual_rf:.2%} instead.")

# ---------------------------------------------------------------- calculations
amounts = holdings.set_index("Ticker")["Amount"].loc[valid]
weights = metrics.normalize_weights(amounts.to_dict())
invest = float(amounts.sum()) if input_mode == "Dollar amounts" else 10_000.0
dollars = weights * invest

port_prices = prices[valid]
buy_hold_val = metrics.portfolio_value(port_prices, dollars)
port_val = (metrics.rebalanced_value(port_prices, dollars, rebalance) if rebalance
            else buy_hold_val)
bench_val = prices[benchmark] / prices[benchmark].iloc[0] * invest
asset_rets = metrics.daily_returns(port_prices)

port_stats = metrics.summarize(port_val, rf, bench_val)
bench_stats = metrics.summarize(bench_val, rf, bench_val)
risk_contrib = metrics.risk_contributions(asset_rets, weights)
end_weights = (port_prices.iloc[-1] * dollars / port_prices.iloc[0])
end_weights = end_weights / end_weights.sum()

# ---------------------------------------------------------------- latest quotes
if finnhub_key:
    st.subheader("Latest quotes (Finnhub)")
    try:
        quotes = load_quotes(tuple(valid + [benchmark]), finnhub_key)
        if quotes.empty:
            st.info("Finnhub returned no quotes for these symbols.")
        else:
            st.dataframe(quotes.style.format({"Price": "${:,.2f}", "Change": "{:+.2f}",
                                              "Change %": "{:+.2%}", "Prev close": "${:,.2f}"}),
                         hide_index=True, width="stretch")
    except data.DataError as exc:
        st.warning(str(exc))

# ---------------------------------------------------------------- KPIs
st.subheader(f"Results: {prices.index[0]:%b %d, %Y} – {prices.index[-1]:%b %d, %Y}")
st.caption(f"{len(prices)} trading days · risk-free rate: {rf_note} · "
           f"{rebalance_label.lower()} · ${invest:,.0f} invested")

k = st.columns(5)
for col, name in zip(k, ["Annualized return", "Annualized volatility", "Sharpe ratio",
                         "Max drawdown", "Beta vs benchmark"]):
    p, b = port_stats[name], bench_stats[name]
    delta = None
    if name != "Beta vs benchmark" and not (np.isnan(p) or np.isnan(b)):
        diff = p - b
        delta = f"{diff:+.2%} vs {benchmark}" if name in PCT_ROWS else f"{diff:+.2f} vs {benchmark}"
    # lower volatility is better, so flip the color for it
    col.metric(name, fmt_metric(name, p), delta,
               delta_color="inverse" if name == "Annualized volatility" else "normal")

# ---------------------------------------------------------------- charts row 1
series_colors = {"Portfolio": PORTFOLIO_COLOR, benchmark: BENCHMARK_COLOR}
port_label = f"Portfolio ({rebalance} rebalancing)" if rebalance else "Portfolio"
left, right = st.columns(2)
with left:
    st.markdown("**Growth of the portfolio vs benchmark**")
    growth = {port_label: port_val}
    if rebalance:
        growth["Portfolio (buy and hold)"] = buy_hold_val
    growth[benchmark] = bench_val
    fig = px.line(pd.DataFrame(growth),
                  labels={"value": "Value ($)", "index": "", "variable": ""},
                  color_discrete_map={port_label: PORTFOLIO_COLOR, benchmark: BENCHMARK_COLOR,
                                      "Portfolio (buy and hold)": BUY_HOLD_COLOR})
    fig.update_traces(line_dash="dash", selector=dict(name="Portfolio (buy and hold)"))
    fig.update_layout(height=380, legend=dict(orientation="h", y=1.08), margin=dict(t=30))
    st.plotly_chart(fig, width="stretch")
with right:
    st.markdown("**Drawdown (decline from previous peak)**")
    dd = pd.DataFrame({"Portfolio": metrics.drawdown_series(port_val),
                       benchmark: metrics.drawdown_series(bench_val)})
    fig = px.line(dd, labels={"value": "Drawdown", "index": "", "variable": ""},
                  color_discrete_map=series_colors)
    fig.update_layout(height=380, yaxis_tickformat=".0%",
                      legend=dict(orientation="h", y=1.08), margin=dict(t=30))
    st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------- charts row 2
left, right = st.columns(2)
with left:
    st.markdown("**Allocation: starting weight vs share of risk**")
    end_label = "Ending weight (buy and hold)" if rebalance else "Ending weight"
    alloc = pd.DataFrame({"Starting weight": weights, end_label: end_weights,
                          "Share of portfolio risk": risk_contrib}).reset_index(names="Ticker")
    long = alloc.melt(id_vars="Ticker", var_name="Measure", value_name="Share")
    fig = px.bar(long, x="Ticker", y="Share", color="Measure", barmode="group")
    fig.update_layout(height=380, yaxis_tickformat=".0%", legend_title="",
                      legend=dict(orientation="h", y=1.1), margin=dict(t=30))
    st.plotly_chart(fig, width="stretch")
with right:
    st.markdown("**Correlation of daily returns**")
    corr = asset_rets.corr()
    fig = go.Figure(go.Heatmap(z=corr.values, x=corr.columns, y=corr.index,
                               zmin=-1, zmax=1, colorscale="RdBu_r",
                               text=np.round(corr.values, 2), texttemplate="%{text}"))
    fig.update_layout(height=380, margin=dict(t=30))
    st.plotly_chart(fig, width="stretch")

st.markdown("**Allocation pie (starting weights)**")
fig = px.pie(values=weights.values, names=weights.index, hole=0.45)
fig.update_layout(height=320, margin=dict(t=10, b=10))
st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------- tables
st.subheader("Metrics table")
table = pd.DataFrame({"Portfolio": port_stats, benchmark: bench_stats})
for t in valid:
    v = prices[t] / prices[t].iloc[0] * invest
    table[t] = pd.Series(metrics.summarize(v, rf, bench_val))
st.dataframe(table.apply(lambda row: [fmt_metric(row.name, x) for x in row], axis=1),
             width="stretch")

# ---------------------------------------------------------------- interpretation
st.subheader("What the numbers say")
notes = []
pv, bv = port_stats["Annualized volatility"], bench_stats["Annualized volatility"]
notes.append(f"The portfolio's annualized volatility is **{pv:.1%}** versus **{bv:.1%}** for "
             f"{benchmark}, i.e. it has been **{'more' if pv > bv else 'less'} volatile** "
             "than the benchmark.")
ps, bs = port_stats["Sharpe ratio"], bench_stats["Sharpe ratio"]
if not (np.isnan(ps) or np.isnan(bs)):
    sharpe_note = (f"Its Sharpe ratio is **{ps:.2f}** vs **{bs:.2f}**, a "
                   f"**{'better' if ps > bs else 'worse'} risk-adjusted return** than the "
                   "benchmark over this period.")
    if ps < 0 and bs < 0:
        sharpe_note += (" Both are negative: neither beat the risk-free rate, so the "
                        "comparison says little.")
    notes.append(sharpe_note)
notes.append(f"The worst peak-to-trough loss was **{port_stats['Max drawdown']:.1%}** "
             f"(benchmark: {bench_stats['Max drawdown']:.1%}).")
top = risk_contrib.idxmax()
notes.append(f"**{top}** is {weights[top]:.0%} of the starting portfolio but contributes "
             f"**{risk_contrib[top]:.0%} of its risk** (variance). Holdings whose risk share "
             "is well above their weight are where concentration risk sits.")
avg_corr = corr.where(~np.eye(len(corr), dtype=bool)).stack().mean()
notes.append(f"Average pairwise correlation between holdings is **{avg_corr:.2f}**. "
             "The closer to 1, the less diversification benefit the portfolio gets.")
b = port_stats["Beta vs benchmark"]
if not np.isnan(b):
    notes.append(f"A beta of **{b:.2f}** means the portfolio has tended to move about "
                 f"{b:.2f}% for each 1% move in {benchmark}.")
for n in notes:
    st.markdown(f"- {n}")

# ---------------------------------------------------------------- methodology
with st.expander("Methodology, data sources and limitations"):
    st.markdown(f"""
**Data**
- Prices: daily adjusted closes (splits/dividends included) from Yahoo Finance via `yfinance`
  {'*(currently using the synthetic sample dataset instead)*' if source == 'sample' else ''}.
- Risk-free rate: FRED series DGS3MO (3-month Treasury), latest value, or a manual input.
- Latest quotes (optional): Finnhub `/quote` endpoint.

**Calculations** (252 trading days per year)
- Portfolio value: buy-and-hold (shares bought on day 1 and never rebalanced), or
  rebalanced back to the starting weights at the close of the first trading day of
  each month/quarter, with no trading costs.
- Annualized return: (V_end / V_start)^(252 / N) − 1.
- Annualized volatility: standard deviation of daily returns × √252.
- Sharpe ratio: mean daily excess return / std of daily excess return × √252.
- Maximum drawdown: largest % fall from a running peak.
- Beta: Cov(portfolio, benchmark) / Var(benchmark), daily returns.
- Risk contribution: wᵢ(Σw)ᵢ / (w′Σw), using starting weights.

**Limitations**
- Past performance does not predict future returns; all metrics are historical.
- A single, current risk-free rate is applied to the whole period.
- Volatility and Sharpe assume returns are roughly normal; they understate tail risk.
- Ignores taxes, fees and trading costs; dividends are treated as reinvested (adjusted prices).
- Only dates where every ticker traded are used, which can shorten the history.
- Yahoo Finance data is unofficial and occasionally incomplete.

*Educational tool only — not investment advice.*
""")
