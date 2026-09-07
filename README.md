# Aperture

Aperture is a local, single-user market-research and trading-decision workstation
for U.S. equity swing and momentum trading. It compresses market evidence into a
transparent daily workflow:

`Market Context -> Groups -> Leadership -> Structure -> Setup -> Actionability -> Risk -> Portfolio Context`

Aperture supports discretionary decisions. It does not place trades, route
orders, or use an AI stock picker.

## Product boundary

Aperture owns deterministic research, classification, prioritization, evidence,
risk sizing, journaling, and benchmarking. Deepvue remains the chart-review,
drawing, replay, and alerting workspace. Aperture must not grow a competing chart
engine.

The primary interface is React/TypeScript backed by a typed FastAPI boundary.
Python remains the calculation, ingestion, validation, and materialization layer.
Streamlit is retained only for legacy diagnostics and administration.

## Current status

The first real bounded `LOCAL_SNAPSHOT` is implemented and browser-verified on
branch `codex/current-bootstrap-v1` at commit
`401e1b0afd6ad2a4678af4f1040014b5c9b568e9`.

Snapshot decision context:

- market evidence through September 4, 2026;
- evaluated September 6, 2026 in New York;
- first action/population session September 8, 2026;
- 75 research members, 49 strict-trade members, and 25 market-mapping members;
- 66 `NONE`, 9 `WATCH`, 0 `TRADE`, and 0 `ACT`;
- current-cohort bootstrap, not pre-bootstrap historical membership evidence.

Groups currently reports missing published membership. Deepvue taxonomy and theme
captures exist as verified local bootstrap sources but are not runtime dependencies
and were not consumed by this snapshot.

## Read this first

The authoritative reading order is:

1. [`AGENTS.md`](AGENTS.md) - repository rules and safety boundaries.
2. [`docs/APERTURE_CURRENT_AUTHORITY.md`](docs/APERTURE_CURRENT_AUTHORITY.md) - current product truth, settled target decisions, runtime divergences, and document precedence.
3. [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md) - concise implementation and data status.
4. [`docs/CODEX_NEXT_TASK.md`](docs/CODEX_NEXT_TASK.md) - active assignment, or an explicit statement that none is authorized.
5. [`docs/LEGACY_BOUNDARY.md`](docs/LEGACY_BOUNDARY.md) - preserved legacy code and prohibited uses.

Historical design documents, milestone receipts, archived specifications, and
session reports are evidence. They do not override the current authority file.

## Current product grammar

Structure states:

- `NEUTRAL`
- `EMERGING`
- `UPTREND`
- `DETERIORATING`
- `DECLINE`

Setup families:

- `EP`
- `CONTRACTION`
- `TREND_PULLBACK`
- `RANGE`

Setup lifecycle:

- `FORMING`
- `NEAR_TRIGGER`
- `TRIGGERED`
- `RESOLVED`
- `FAILED`
- `STALE`

`RECLAIM` is evidence, not a setup family. Multiple setup families may coexist.
Structure, setup, leadership, extension, regime, actionability, sizing, and
portfolio context remain independent.

## Local development

Requirements:

- Python 3.11 or newer;
- Node/npm for the React application;
- a local `.env` containing `MASSIVE_API_KEY` only when an explicitly authorized
  ingestion job requires it;
- local market data and snapshots, which must never be committed.

Install and run Python tests:

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

Run the React/FastAPI Workstation using the documented local snapshot procedure:

- [`docs/workstation-slice-v1.md`](docs/workstation-slice-v1.md)
- [`docs/current-bootstrap-v1.md`](docs/current-bootstrap-v1.md)
- [`docs/workstation-snapshot-v2.md`](docs/workstation-snapshot-v2.md)

Generated DuckDB databases, Parquet data, provider exports, snapshots, receipts,
backups, secrets, and machine-specific paths remain local and uncommitted.

## Architecture

```text
Approved providers and local source artifacts
  -> Python ingestion and validation
  -> DuckDB and Parquet research storage
  -> pure versioned features and engines
  -> dated snapshot materialization
  -> typed FastAPI service
  -> React Aperture interface
  -> Deepvue chart-review handoff
```

Canonical calculations live in Python. The UI may format evidence and perform
documented what-if sizing, but it must not independently recreate Structure,
Setup, Leadership, Regime, or Actionability logic.

## Versioning and safety

- Form signals using evidence available at session `T`; evaluate fills no earlier
  than `T+1`.
- Do not silently change formulas, thresholds, labels, or historical outputs.
- Semantic changes require new engine and threshold versions.
- Preserve explicit nulls and reason codes; never convert missing evidence to zero.
- Keep provider credentials server-side.
- Use feature branches and pull requests. Do not merge as part of an implementation
  task unless the user explicitly authorizes it.

The original Market Dashboard scores, stages, Streamlit workflow, and related tests
remain in the repository for compatibility and research history. They are not the
active Aperture decision path. See [`docs/LEGACY_BOUNDARY.md`](docs/LEGACY_BOUNDARY.md).
