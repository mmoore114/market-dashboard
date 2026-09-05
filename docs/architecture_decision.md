# Architecture Decision: Aperture Hybrid Application

> Read [PROJECT_STATE.md](PROJECT_STATE.md) for current progress and work order.
> This proposal is not a claim that the frontend/API layout is implemented.
> Engine contracts and foundation reconciliation now precede engine coding.

Status: proposed foundation decision  
Decision scope: primary application architecture and division of responsibilities

## Decision

Use the existing Python repository as the research, data, and rules engine. Add a React and TypeScript application as the primary user interface. Introduce a small typed API boundary between them.

Retain Streamlit only for internal diagnostics, data inspection, and administrative workflows where it is useful. Do not make Streamlit the primary Aperture experience.

## Why

The existing repository already has meaningful production-oriented work:

- Massive.com clients and ingestion;
- DuckDB and Parquet storage;
- a security master;
- versioned exposure classification;
- recoverable publication;
- universe construction;
- adjusted-history planning;
- feature calculations;
- transparent ranking and price-action tests.

The Aperture V1 prototype demonstrated that the target experience benefits from:

- dense tables;
- persistent navigation;
- filter chips;
- a responsive stock drawer;
- interactive sizing;
- compact state badges;
- mobile-aware layout;
- smooth transitions across Brief, Tape, Groups, Book, Sizer, and Rules.

React is a better fit for that interface than a large Streamlit application. Rewriting the tested Python engine in TypeScript would add risk without a product benefit.

## High-level shape

Massive.com and approved event sources
-> Python ingestion and validation
-> DuckDB and Parquet research storage
-> pure versioned feature and state modules
-> snapshot/materialization layer
-> typed local API
-> React Aperture interface

Deepvue remains an adjacent chart-review and alerting tool, not an application dependency.

## Repository layout target

A gradual target layout:

- app/
  - existing Streamlit diagnostic entry point
- api/
  - API application entry point
- web/
  - React and TypeScript application
- config/
  - versioned policies and research configurations
- docs/
  - contracts, decisions, handoffs, and research definitions
- src/market_dashboard/
  - data ingestion and storage
  - universes and classification
  - feature calculations
  - regime, groups, strength, stages, setups, sizing, and outcomes
  - snapshot orchestration
- tests/
  - unit, integration, point-in-time, and contract tests

Do not perform a large mechanical relocation before a feature requires it.

## Backend boundaries

### Ingestion

Responsible for:

- Massive.com and approved provider clients;
- retries, throttling, and bounded jobs;
- raw response normalization;
- adjusted daily bars;
- reference and event data.

Ingestion must not contain UI decisions.

### Classification and universes

Responsible for:

- provider security facts;
- immutable economic-exposure policies;
- research, mapping, and trade-universe membership;
- point-in-time membership and reason codes;
- hysteresis when enabled by a versioned rule.

### Features

Pure or near-pure calculations for:

- volatility and range;
- volume and liquidity;
- returns and momentum;
- moving averages and slopes;
- benchmark-relative and residual strength;
- group aggregates;
- extension;
- gap and earnings-event behavior.

### States and setups

Keep separate modules for:

- market regime;
- structural stage;
- tactical price-action state;
- setup detection;
- action promotion and vetoes;
- position sizing and portfolio heat.

### Snapshot layer

Builds a dated, reproducible view for the UI.

Each snapshot should include:

- as-of session and data freshness;
- universe and policy versions;
- regime and sleeve reasons;
- group ranks;
- per-symbol component metrics;
- structural, extension, setup, and action states;
- vetoes and human-readable reasons;
- sizing inputs, not broker instructions.

## API boundary

Use a small typed HTTP API, with FastAPI as the leading candidate because it fits the Python stack and can expose OpenAPI types.

Initial endpoints or equivalent contracts:

- health and data freshness;
- current market brief;
- ranked tape with filters;
- groups and group constituents;
- symbol detail;
- sizer calculation;
- positions and journal;
- rules and version metadata.

The API should return explicit nulls and reason codes. It must not convert missing long-lookback data to zero.

The UI must not calculate canonical states independently. Display-only formatting and what-if sizing are acceptable when they use the same documented contract.

## Frontend decision

Preferred stack:

- React;
- TypeScript;
- Vite or TanStack Start after a focused scaffold decision;
- a typed query/cache layer;
- a restrained component system;
- virtualized or efficiently paged dense tables;
- responsive stock detail drawer;
- local preferences for display settings only.

Do not place API keys in frontend code or browser storage.

## UI information architecture

### Brief

- regime and sleeve summary;
- funnel counts;
- leading and weakening groups;
- Act list;
- book heat and data freshness.

### Tape

- sortable/filterable table;
- structure, extension, setup, strength, group, action, and veto columns;
- row selection opens symbol detail;
- compact mobile fallback.

### Groups

- sector, industry, and theme rank;
- median and breadth statistics;
- persistence and change in rank;
- constituent leaders.

### Symbol detail

- transparent checklist;
- price and volume context;
- component metrics;
- stop and sizing preview;
- documented handoff to visual review.

### Book and Journal

- planned and actual risk;
- R multiples;
- next action;
- portfolio heat;
- trade rationale and outcome;
- benchmark comparison.

### Rules

- rendered from versioned configuration and code metadata where practical;
- shows effective dates and hypothesis/validated status.

## Data and metric versioning

Every material output should be attributable to:

- data as-of date;
- security-master snapshot;
- exposure-policy version;
- universe-policy version;
- feature-definition version;
- state-machine version;
- setup-definition version;
- regime version;
- scoring version if used.

Do not reuse a column name when its mathematical definition changes.

## Authentication and deployment

The first production target is a local single-user application on the Chromebook/Linux environment.

Initial priorities:

- server-side secrets;
- no public exposure of local market datasets;
- deterministic local builds;
- safe backup of code through GitHub;
- no requirement for multi-user authentication.

Hosting and remote access are later decisions and require an explicit security review.

## Testing strategy

### Unit tests

- formulas and missing-data behavior;
- exact threshold boundaries;
- state precedence;
- reason codes;
- sizing refusals;
- version selection.

### Integration tests

- ingestion to storage;
- storage to snapshot;
- snapshot to API;
- API contract to frontend fixtures.

### Research tests

- point-in-time membership;
- signal T close and fill T+1 or later;
- transaction-cost assumptions;
- benchmark alignment;
- walk-forward and out-of-sample evaluation;
- sensitivity to threshold changes.

### UI tests

- dense desktop table;
- mobile navigation and drawer;
- filter persistence;
- null and stale-data states;
- accessibility of state colors and labels.

## Sequencing decision

### Milestone 0: finish the existing data milestone

From the documented stopping point:

1. build and validate exposure-policy-v3 locally;
2. prove v2 remains unchanged;
3. rebuild the policy-versioned swing universe;
4. rebuild and validate the adjusted-backfill plan;
5. identify the corrected next unfilled rank range;
6. run a bounded dry run;
7. obtain explicit approval before real ingestion.

### Milestone 1: freeze rule contracts

- add versioned configurations;
- resolve the two-universe model;
- add Wilder ATR without changing existing ATR;
- separate structural stage from extension and tactical state;
- define snapshot schemas and reason codes.

### Milestone 2: empirical feature layer

- true 3M/6M/12M returns;
- QQQ residual strength;
- sector/industry medians and persistence;
- RMV and contraction;
- gap and volume-character features;
- earnings-event fields.

### Milestone 3: first usable vertical slice

- typed API;
- Brief;
- Tape;
- symbol detail;
- sizer;
- fixture and live-snapshot modes.

### Milestone 4: decision workflow

- regime;
- group pages;
- Watch/Trade/Act;
- vetoes;
- Book and portfolio heat.

### Milestone 5: learning system

- journal;
- benchmark comparison;
- setup cohorts;
- rejected-candidate tracking;
- walk-forward reports.

## Consequences

Benefits:

- preserves tested Python work;
- supports the preferred terminal-quality interface;
- keeps canonical logic in one place;
- allows Deepvue to remain the specialized charting tool;
- supports gradual delivery.

Costs:

- introduces a frontend and API boundary;
- requires contract tests and type synchronization;
- adds local process orchestration;
- requires discipline to prevent duplicate calculations.

These costs are acceptable because interface quality and long-term maintainability are central product requirements.
