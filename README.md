# market-dashboard

Market Dashboard is a Python research repository for equity discovery, ranking, and discretionary market research. The project is intended to collect market data, persist local research datasets, compute opportunity features, and expose a Streamlit dashboard for exploration.

## Planned Architecture

- `app/`: Streamlit entry points and runnable dashboard apps.
- `config/`: YAML configuration for data, scoring, and dashboard behavior.
- `data/`: Local raw, processed, and DuckDB-backed research storage. Data files are ignored by git.
- `src/market_dashboard/data/`: API clients and storage utilities.
- `src/market_dashboard/features/`: Volatility, liquidity, momentum, and trend feature calculations.
- `src/market_dashboard/rankings/`: Opportunity scoring and ranking logic.
- `src/market_dashboard/dashboard/`: Shared dashboard components.
- `tests/`: Pytest coverage for project setup and core behavior.

## Setup

1. Create a Python 3.11 or newer virtual environment.
2. Install the project with development dependencies:

   ```powershell
   pip install -e ".[dev]"
   ```

3. Create a local `.env` file from `.env.example` and set `MASSIVE_API_KEY`.
4. Run tests:

   ```powershell
   pytest
   ```

5. Start the placeholder dashboard:

   ```powershell
   streamlit run app/dashboard.py
   ```

## Security

The Massive API key belongs only in a local `.env` file. Never commit `.env`, copied environment files, API keys, database files, raw data, processed data, or exported parquet files.

## Daily Bar Ingestion

The test-universe ingestion script reads `config/settings.yaml` and retrieves adjusted daily bars for the configured tickers. By default, it requests about 400 calendar days ending today.

```powershell
python scripts/ingest_test_universe.py
```

Optional date and ticker overrides:

```powershell
python scripts/ingest_test_universe.py --start 2025-01-01 --end 2025-12-31 --tickers SPY QQQ
```

Parquet files are written one file per ticker under `data/processed/daily_bars/`. DuckDB is stored at `data/database/market_dashboard.duckdb`.

Within each ingestion batch, rows are deduplicated by `ticker` and `date`. When writing Parquet, new rows are merged with existing ticker files and replace older rows for the same `ticker` and `date`. DuckDB uses the same key: existing `ticker`/`date` rows are deleted before inserting the latest batch rows, so reruns do not create duplicates.

Validate local daily-bar storage with:

```powershell
python scripts/validate_daily_storage.py
```

The validation script reports per-ticker row counts and date ranges, duplicate `ticker`/`date` groups, required OHLCV null counts, and DuckDB-vs-Parquet row-count agreement. Generated market data is local research output and must not be committed to Git.

## Equity Features

Build daily feature history and the latest equity snapshot from local DuckDB `daily_bars`:

```powershell
python scripts/build_equity_features.py
```

Validate generated feature tables:

```powershell
python scripts/validate_equity_features.py
```

The feature build reads `daily_bars`, writes historical rows to `daily_equity_features`, and writes one latest row per ticker to `latest_equity_snapshot`. Generated DuckDB feature data stays in `data/database/market_dashboard.duckdb`, which is ignored by Git.

Feature definitions:

- `true_range`: max of `high - low`, `abs(high - previous_close)`, and `abs(low - previous_close)`.
- `atr_14`: 14-day rolling mean of `true_range`.
- `atr_percent_14`: `atr_14 / close * 100`.
- `adr_percent_20`: 20-day rolling mean of `(high - low) / close * 100`.
- `dollar_volume`: `close * volume`.
- `average_volume_20`: 20-day rolling mean of `volume`.
- `average_volume_50`: 50-day rolling mean of `volume`.
- `average_dollar_volume_20`: 20-day rolling mean of `dollar_volume`.
- `relative_volume_20`: `volume / average_volume_20`.
- `return_5d_percent`, `return_20d_percent`, `return_60d_percent`, `return_120d_percent`: percent change over 5, 20, 60, and 120 trading rows per ticker.
- `high_20d`: 20-day rolling high.
- `high_252d`: 252-day rolling high.
- `distance_from_20d_high_percent`: `(close - high_20d) / high_20d * 100`.
- `distance_from_252d_high_percent`: `(close - high_252d) / high_252d * 100`.
- `ema_9`: 9-day exponential moving average of `close`.
- `sma_20`, `sma_50`, `sma_200`: 20, 50, and 200-day simple moving averages of `close`.
- SPY-relative excess returns: ticker return minus SPY return on the same date for 20, 60, and 120-day returns.

Insufficient lookback history remains null. Long-lookback values are not filled with zero.

Trend-stage precedence:

1. `Extended`: `close` is more than 12% above `sma_20` and `sma_20 > sma_50`.
2. `Confirmed Leader`: `close > sma_20 > sma_50 > sma_200`.
3. `Emerging Leader`: `close > sma_20` and `close > sma_50`, but full alignment is absent.
4. `Pullback in Uptrend`: `sma_20 > sma_50` and `sma_50 < close <= sma_20`.
5. `Fading`: `close < sma_20` and `close >= sma_50`.
6. `Bearish Trend`: `close < sma_50` and `sma_50 < sma_200`.
7. `Unclassified`: anything else or insufficient history.

`Pullback in Uptrend` uses `sma_50 < close <= sma_20` so `Fading` remains reachable at `close == sma_50`.

## Opportunity Score

Eligibility:

- `close >= 10`
- `average_dollar_volume_20 >= 50,000,000`
- `adr_percent_20 >= 2`

Eligible stocks are scored using percentile ranks from the latest snapshot:

- 40% ADR percentile
- 25% average-dollar-volume percentile
- 20% 20-day momentum percentile
- 15% 60-day excess-return-vs-SPY percentile

Percentiles are calculated only across eligible rows with available data for that component. Ineligible rows receive an `eligibility_reason` and no score. Eligible rows missing required scoring inputs also receive no score and a clear reason.

This is an initial transparent research model for ranking and review. It is not a trading recommendation.

## Initial Development Phases

1. Establish project structure, configuration, and storage paths.
2. Implement a safe Massive API client and raw data ingestion workflow.
3. Add DuckDB persistence for repeatable local research datasets.
4. Build feature modules for volatility, liquidity, momentum, and trend.
5. Combine features into opportunity rankings.
6. Expand the Streamlit dashboard for research workflows and discretionary review.
