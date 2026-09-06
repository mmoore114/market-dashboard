# market-dashboard

The local Aperture Workstation now provides Brief, Tape, symbol detail, Sizer and
Rules through React/TypeScript and FastAPI. Start with the
[local setup and snapshot contract](docs/workstation-slice-v1.md).
Development defaults to visibly labeled synthetic fixtures; real snapshot
materialization remains deferred.

Current implementation handoff: [docs/PROJECT_STATE.md](docs/PROJECT_STATE.md).
For new structure/setup work, read the canonical specifications linked there.
The older stage/setup descriptions below describe legacy research or earlier
candidates; they do not override the canonical amendments. The daily Structure
Engine V1 is implemented as a separate pure API; see
[its contract, formulas, and usage](docs/structure-engine-implementation-v1.md).
The separate daily Setup Engine V1 is also implemented as a pure API; see
[its detection, lifecycle, and replay contract](docs/setup-engine-implementation-v1.md).
Strength/Leadership and Group Ranking V1 provide a separate experimental
5/21-session rotation pulse and 63/126/252-session composite; see
[the pure API and point-in-time group contract](docs/leadership-engine-implementation-v1.md).
Market Regime V1 adds five independent sleeves, explicit UNKNOWN evidence and
confirmed-state hysteresis; see [its pure API and timing contract](docs/regime-engine-implementation-v1.md).
Decision & Risk V1 composes these contracts into direction-aware extension,
earnings gates, WATCH/TRADE/ACT evidence and per-idea sizing; see
[its formulas, timing and pure API](docs/decision-risk-implementation-v1.md).
Production materialization and portfolio-level policies remain separate work.

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
- `wilder_atr_14`: separately named Wilder ATR14, seeded with the arithmetic
  mean of the first 14 true ranges and recursively smoothed thereafter.
- `wilder_atr_percent_14`: `wilder_atr_14 / close * 100`; null when close is
  missing or nonpositive.
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
- `distance_from_sma_200_percent`: percent distance from SMA200.
- `atr_extension_from_sma_20_wilder`: `(close - sma_20) / wilder_atr_14`.
- `atr_extension_from_sma_50_wilder`: `(close - sma_50) / wilder_atr_14`.
- SPY-relative excess returns: ticker return minus SPY return on the same date for 20, 60, and 120-day returns.

Insufficient lookback history remains null. Long-lookback values are not filled with zero.
The existing `atr_14` and `atr_percent_14` retain their simple rolling-mean
semantics; Wilder ATR and extension fields are additive definitions.

## Aperture V1 Rule Contracts

`config/aperture_rules_v1.yaml` contains immutable, versioned V1 candidate
rules. Its thresholds are hypotheses pending point-in-time empirical
validation and do not generate `Act` decisions.

Aperture keeps three memberships separate:

- Market mapping covers eligible liquid diversified or benchmark instruments
  used for tape, sector, industry, theme, breadth, and style context. Benchmark
  exceptions come from the versioned ticker allowlist in the rules file.
- Equity research covers a broader direct-equity cohort for ranks and group
  comparisons.
- Equity trade applies strict direct-equity entry gates, with a separately
  modeled prior-member retention hypothesis.

The existing policy-versioned swing universe remains a broad research and
adjusted-data-planning universe using its current $5 price, $50 million ADV,
observation, and coverage requirements. It is not the stricter Aperture equity
trade universe, and the new evaluator is not connected to that production
builder in Milestone 1.

Universe instrument facts use explicit exchange MICs such as `XNAS`, `XNYS`,
and `ARCX`. Tickers and MICs are normalized to canonical uppercase values;
benchmark status is never supplied by a caller-controlled boolean.

Public Aperture numeric contracts accept finite values or explicit `null` when
a metric is nullable. NaN and positive or negative infinity are rejected.
Snapshot freshness timestamps must include a timezone, and every snapshot
attributes both the named rules version and the deterministic rules
fingerprint.

Structural stage, numeric extension, extension state, tactical/setup state,
regime, action state, reasons, and vetoes are distinct typed contracts. `S2E`
is not a stored structural stage; it is represented as S2 structure plus a
separate extension state when applicable.

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

## Research Layers

The dashboard separates market research into independent layers:

- Market mapping: future sector, industry, and theme rankings, plus breadth and rotation work.
- Leadership: strength relative to the market, multi-window momentum, relative strength versus SPY, and proximity to recent highs.
- Opportunity/tradability: movement and equity liquidity. This layer is directionally neutral and remains separate from leadership and timing.
- Price action: shorter-term daily swing condition and possible timing. It is not Weinstein weekly stage analysis, and named chart patterns are intentionally not hard-coded.
- Future options layer: spreads, open interest, contract volume, usable expirations and strikes, implied volatility, and options liquidity.

### Leadership Score

Leadership Score is a 0 to 100 model using:

- 15% `return_20d_percentile`
- 15% `return_60d_percentile`
- 10% `return_120d_percentile`
- 10% `excess_20d_vs_spy_percentile`
- 15% `excess_60d_vs_spy_percentile`
- 10% `excess_120d_vs_spy_percentile`
- 10% `proximity_20d_high_percentile`
- 10% `proximity_252d_high_percentile`
- 5% `moving_average_structure_score`

Leadership states:

- `Strong Leader`: score >= 80
- `Leader`: score >= 65 and < 80
- `Emerging`: score >= 50 and < 65
- `Neutral`: score >= 35 and < 50
- `Lagging`: score >= 20 and < 35
- `Deteriorating`: score < 20
- `Insufficient Data`: required inputs unavailable

### Price Action State

`price_action_state` is the canonical shorter-term daily swing classifier. `trend_stage` is retained only for backward compatibility and is deprecated for dashboard use.

Price Action State precedence:

1. `Extended`
2. `Bearish Expansion`
3. `Damaged`
4. `Constructive Pullback`
5. `Near Trigger`
6. `Trend Expansion`
7. `Fading`
8. `Bearish`
9. `No Setup`
10. `Insufficient Data`

Directional bias meanings:

- `Long Watch`: constructive long-side conditions to monitor.
- `Put Watch`: weakening or bearish daily conditions to monitor.
- `Neutral`: no directional watchlist bias from the daily classifier.

Entry quality meanings:

- `Actionable`: current state may be close enough for tactical review.
- `Developing`: setup is incomplete or still forming.
- `Avoid`: extended condition where new entries are lower quality.
- `None`: no actionable setup state.

All thresholds are initial transparent research assumptions and should be reviewed against actual workflow outcomes.

The existing `trend_stage`, `price_action_state`, Opportunity Score, and
Leadership Score remain legacy or research outputs. None directly promotes a
symbol to Aperture `Act`.

## Initial Development Phases

1. Establish project structure, configuration, and storage paths.
2. Implement a safe Massive API client and raw data ingestion workflow.
3. Add DuckDB persistence for repeatable local research datasets.
4. Build feature modules for volatility, liquidity, momentum, and trend.
5. Combine features into opportunity rankings.
6. Expand the Streamlit dashboard for research workflows and discretionary review.
