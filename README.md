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

## Initial Development Phases

1. Establish project structure, configuration, and storage paths.
2. Implement a safe Massive API client and raw data ingestion workflow.
3. Add DuckDB persistence for repeatable local research datasets.
4. Build feature modules for volatility, liquidity, momentum, and trend.
5. Combine features into opportunity rankings.
6. Expand the Streamlit dashboard for research workflows and discretionary review.
