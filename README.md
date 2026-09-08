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

The real V2 Workstation now includes 312 Groups with explicitly labeled current-
cohort analysis: 11 sectors, 25 groups, 75 industry paths, 170 sub-industry paths,
and 31 themes. The last completed price session remains visible independently of
membership capture dates and evaluation time. Historical membership and historical
group rotation are not inferred from current captures.

The verified current snapshot contains 75 research and 49 trade members, with
63 NONE / 12 WATCH / 0 TRADE / 0 ACT. Missing VIX/earnings evidence stays explicit.
See [daily refresh and its completion receipt](docs/current-refresh-v2.md).

## Launch and refresh

From the installed repository, with private configuration at
`${XDG_CONFIG_HOME:-$HOME/.config}/aperture/refresh.json`:

```bash
.venv/bin/python scripts/aperture.py launch
.venv/bin/python scripts/aperture.py refresh
.venv/bin/python scripts/aperture.py status
```

`launch` catches up when necessary, then starts the local Workstation at
`http://127.0.0.1:5173`; Ctrl-C stops both services. `refresh` acquires only required
bounded inputs, verifies a new snapshot and activates it atomically. Failed refreshes
preserve the last successful artifact and report its age/usability. An ongoing
exchange session is never treated as completed. Old snapshots keep their expiry.

The supported user-systemd timer checks every 15 minutes and on Linux startup,
with persistent catch-up. The command derives its actual due time from pinned
XNYS close plus a 45-minute availability buffer, including early closes and DST.
The laptop cannot refresh while ChromeOS suspends Linux or Linux is stopped;
catch-up runs after resume. Always-on operation requires an always-on host.
Install on a configured Linux machine with:

```bash
.venv/bin/python scripts/install_aperture_timer.py
systemctl --user list-timers aperture-refresh.timer
```

Current membership can be reused under a separately published operator policy:
14 calendar days for hierarchy and 7 for themes, with warnings 3 and 2 days before
expiry. Age always starts at the original capture date; reuse is not a Deepvue
reconfirmation. Status now reports both source ages, last attempt/failure, missing
inputs, active refresh lock and scheduler dispatch separately from the next
eligible refresh attempt. It is read-only and handles damaged status metadata
without hiding the retained snapshot.

See [membership maintenance and policy publication](docs/membership-maintenance-v1.md)
for defaults, expiry boundaries and the command to register a newly verified
capture. No daily manual approval is needed within the explicit policy interval.

Private path configuration, source receipts, credentials, current snapshots and
backups stay outside Git. Membership validity and provider availability remain
independent requirements; consult the refresh receipt for exact missing inputs.

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
