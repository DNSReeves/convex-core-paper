# Data (not redistributed)

The model is built from a local SQLite warehouse `etf_data.db` of daily ETF OHLCV
and macro series. **The underlying data is licensed from EODHD, FMP, and FRED and is
NOT included in this repository.** Place a rebuilt `etf_data.db` here (`data/etf_data.db`).

## Sources
- **EODHD / FMP** — daily adjusted OHLCV for the ETF universe (equity sectors/factors,
  Treasuries/bills, managed futures, anti-beta, commodities, gold, dollar). Adjusted
  close used as a total-return proxy.
- **FRED** — macro series: `DGS3MO` (90-day T-bill, the risk-free rate), `DGS10`,
  `T10Y2Y`, `T10YIE`, `BAMLH0A0HYM2` / `BAMLC0A0CM` (HY/IG OAS), `VIXCLS`, `DTWEXBGS`,
  `NFCI`, `STLFSI4`.

## Schema (minimum)
- `daily_prices(ticker TEXT, date TEXT, adjusted_close REAL, ...)`
- `macro_series(series_id TEXT, date TEXT, value REAL)`

Read-only access is sufficient; the engine opens the DB in `mode=ro`.

## Reproducing without the raw data
The `results/*.json` artifacts (model curves, benchmark metrics, ablation/attribution,
regime validation) are computed **model outputs**, not vendor data, and reproduce every
table and figure in the paper directly via `report/build_pub_report.py`.
