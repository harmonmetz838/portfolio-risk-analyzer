"""Generate data/sample_prices.csv: SYNTHETIC daily prices for offline demos.

The series are simulated with correlated geometric Brownian motion (fixed seed,
so the file is reproducible). Drift and volatility values are rough,
illustrative assumptions -- these are NOT real prices for these tickers.

Run:  python scripts/make_sample_data.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

# ticker: (annual drift, annual volatility, starting price)
ASSETS = {
    "AAPL": (0.15, 0.28, 150.0),
    "MSFT": (0.14, 0.26, 300.0),
    "NVDA": (0.30, 0.50, 40.0),
    "JNJ":  (0.05, 0.16, 160.0),
    "XOM":  (0.08, 0.30, 100.0),
    "TLT":  (0.00, 0.15, 100.0),
    "GLD":  (0.06, 0.15, 170.0),
    "SPY":  (0.10, 0.18, 400.0),
}
# loading of each asset on a common "market" factor (rest is idiosyncratic)
MARKET_LOADING = {"AAPL": 0.8, "MSFT": 0.8, "NVDA": 0.7, "JNJ": 0.5,
                  "XOM": 0.5, "TLT": -0.2, "GLD": 0.1, "SPY": 0.98}


def main(seed: int = 42) -> None:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2021-01-04", "2025-12-31")
    n, dt = len(dates), 1 / 252
    market = rng.standard_normal(n)
    prices = {}
    for t, (mu, sigma, p0) in ASSETS.items():
        b = MARKET_LOADING[t]
        z = b * market + np.sqrt(1 - b ** 2) * rng.standard_normal(n)
        log_ret = (mu - 0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * z
        log_ret[0] = 0.0
        prices[t] = p0 * np.exp(np.cumsum(log_ret))
    df = pd.DataFrame(prices, index=dates).round(2)
    df.index.name = "Date"
    out = Path(__file__).resolve().parent.parent / "data" / "sample_prices.csv"
    out.parent.mkdir(exist_ok=True)
    df.to_csv(out)
    print(f"Wrote {len(df)} rows x {df.shape[1]} tickers to {out}")


if __name__ == "__main__":
    main()
