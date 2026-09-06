# Codex Next Task

**Task ID:** AP-WORKSTATION-SLICE-001

**Status:** READY

**Issued:** 2026-09-06

**Base commit:** `e81994aa9f561439f5c2dd970e5d2d6a4e2358e3`

## Handoff protocol

This file is the single current assignment for VS Code Codex.

1. Read `AGENTS.md`, `docs/PROJECT_STATE.md`, and every authoritative source
   listed below before editing.
2. Build the complete bounded vertical slice autonomously. Preserve all completed
   engine contracts and legacy behavior.
3. Stop only for a material contract contradiction, a required unavailable
   dependency, or an external/destructive action.
4. At completion, mark this task `COMPLETE`, add a concise completion record,
   update `docs/PROJECT_STATE.md`, commit, push, and open a draft PR targeting
   `codex/decision-risk-v1` so it contains only this milestone.
5. Return only the full commit SHA, Python focused/full-suite totals, frontend test
   and build results, PR link, and any genuine blocker. Keep detailed evidence in
   the repository.

Preserve `.vscode/settings.json`, `.env`, credentials, databases, Parquet/CSV
datasets, staged artifacts, generated reports, and unrelated user changes.

## Milestone

Build the first usable local Aperture Workstation vertical slice:

- a versioned snapshot/read-model boundary;
- a small typed FastAPI service;
- a React/TypeScript primary interface;
- Brief, Tape, symbol detail, Sizer, and Rules experiences;
- deterministic synthetic-fixture mode and an explicit local-snapshot mode.

Create and work on:

`codex/workstation-slice-v1`

Base it on this handoff branch after pulling the task commit. This is the first
user-facing product milestone. It remains a local, single-user, decision-support
application. It must not place trades, contact providers, publish data, or claim
that synthetic fixture data is live.

## Authoritative sources

Read and follow:

- `AGENTS.md`
- `docs/PROJECT_STATE.md`
- `docs/architecture_decision.md`, especially repository layout, snapshot/API
  boundaries, frontend decision, testing, and Milestone 3
- `docs/aperture_product_contract.md`, especially product principles, primary
  interface, symbol detail, scoring policy, and risk contract
- all completed Universe, Structure, Setup, Leadership, Regime, and Decision &
  Risk implementation contracts
- `config/aperture_rules_v1.yaml` and its immutable loader
- current diagnostic Streamlit application only as legacy context, not as the
  primary interface design

Do not redesign canonical trading logic in the UI or API. The existing engines
remain the sole authority for states, eligibility, reasons, extension, earnings,
and sizing.

## Architecture freeze

Use the gradual target layout already approved:

- `src/market_dashboard/workstation/` for frozen snapshot/read models,
  projections, fixture construction, and local snapshot loading;
- `api/` for the FastAPI application and entry point;
- `web/` for the React/TypeScript application;
- `tests/` for Python snapshot/API tests;
- colocated frontend tests under `web/`.

Use FastAPI with Pydantic contracts. Add only the Python dependencies required to
run and test the typed local API.

Use React, TypeScript, and Vite for this V1 slice. Use TanStack Query for server
state and TanStack Table or an equivalently focused table primitive for the Tape.
Keep the component layer restrained and owned in-repository; do not import a large
dashboard template or reproduce another trading platform.

The API and UI run as separate local development processes. CORS must default to
the exact local frontend origin(s), never wildcard with credentials. Bind locally
by default. No authentication or remote hosting belongs in this milestone.

## Snapshot and read-model boundary

Create a frozen, extra-field-forbidding `WorkstationSnapshotV1` contract with:

- snapshot ID, schema version, generated-at timestamp, as-of session, action
  session, and explicit mode (`FIXTURE` or `LOCAL_SNAPSHOT`);
- freshness state and machine-readable reasons;
- source, calendar, security-master, exposure, universe, feature, Structure,
  Setup, Leadership, Regime, Decision/Risk, and rules version identities;
- complete current regime/sleeve evidence;
- explicit funnel counts for NONE/WATCH/TRADE/ACT;
- group summaries needed by Brief and symbol context;
- one canonical per-symbol/direction record retaining component values, setup
  evidence, every gate, veto/reason codes, and sizing context;
- a deterministic logical fingerprint excluding only generation timestamps.

Define compact versioned API view models projected from that canonical snapshot.
The projection may omit nested implementation detail from list responses but must
never recalculate, rename, merge, or contradict canonical engine states. Preserve
explicit nulls and reasons. Missing is never zero, false, neutral, or clear.

Snapshot loading rules:

- `FIXTURE` is the default development mode and uses a committed deterministic,
  fully synthetic fixture constructed without importing from `tests/`;
- fixture rows must cover NONE, WATCH, TRADE, ACT, Green/Yellow/Red context,
  established and new-rotation strength, each setup family, earnings veto/unknown,
  extension refusal, missing-data reasons, and capital-constrained sizing;
- every fixture response and UI surface must visibly say `SYNTHETIC FIXTURE`;
- `LOCAL_SNAPSHOT` loads only an explicitly configured local JSON snapshot file,
  validates the complete frozen contract and fingerprint, and performs no database
  query or fallback;
- missing, malformed, stale, wrong-version, or wrong-fingerprint local snapshots
  fail closed with typed health/freshness evidence; never silently fall back to the
  fixture while labeled local/live;
- do not implement DuckDB/Parquet materialization in this milestone.

No runtime mode may read proprietary Deepvue exports or staging directories.

## Typed API V1

Provide versioned routes under `/api/v1`:

- `GET /health` — service, mode, snapshot availability, as-of/action sessions,
  freshness, version, and reason codes;
- `GET /brief` — regime sleeves, funnel counts, leading/weakening group context,
  ACT candidates, data freshness, and explicit unavailable portfolio-heat status;
- `GET /tape` — typed paginated/sorted/filterable candidate rows;
- `GET /symbols/{symbol}` — exact-symbol detail with checklist, component
  evidence, all setup instances, vetoes, price/volume context, and sizing context;
- `POST /sizer` — a what-if calculation that calls the existing canonical sizing
  function with snapshot regime/earnings context and caller entry/stop/equity/
  buying power; it must not duplicate sizing math;
- `GET /rules` — effective human-readable thresholds plus exact rule/version
  metadata and `experimental_uncalibrated` status.

Tape query behavior must be explicit and tested:

- stable exact-symbol tie-break ordering;
- sort allowlist rather than arbitrary field access;
- filters for action state, Structure state, setup family, minimum RS composite,
  minimum RS rotation, group, and veto presence;
- bounded page size and deterministic pagination metadata;
- invalid filters/sorts return typed 4xx responses;
- exact case-sensitive MarketDataSymbol path resolution.

Return a versioned error envelope with machine-readable code, human message, and
optional field details. Do not expose stack traces, local absolute paths, secrets,
environment values, or raw file contents.

Generate and check in the OpenAPI document deterministically. Generate or validate
frontend API types from it so contract drift fails tests. Do not maintain a second
handwritten set of contradictory transport types.

## React Workstation V1

Create a polished, dense, responsive interface intended primarily for the user's
Chromebook/desktop browser, with a useful compact mobile fallback.

Use a restrained dark terminal/workstation visual language with accessible text,
focus states, and labels in addition to color. Do not use generic oversized cards,
marketing-page styling, gradients everywhere, or fake candlestick charts.

Persistent navigation must expose:

- Brief
- Tape
- Sizer
- Rules

Groups, Book, and Journal may appear only as clearly disabled future destinations;
do not fabricate those workflows.

### Brief

Render:

- current confirmed regime and five separately visible sleeves;
- as-of/action sessions and data freshness;
- Watch/Trade/Act funnel counts;
- leading and weakening groups supplied by the snapshot;
- compact ACT review queue with symbol, setup(s), strength, extension, group, and
  first visible veto/status context;
- portfolio heat as `Unavailable — portfolio context not implemented`, never 0%.

### Tape

Build a dense sortable/filterable table showing at minimum:

- exact symbol and price;
- Structure;
- RS composite, 1-week/5-session rotation, 1-month/21-session rotation context,
  `RS_rotation`, and `rotation_delta` where supplied;
- sub-industry and group rank;
- setup families/statuses;
- extension ATR;
- decision state;
- earnings status;
- veto/reason indicator.

Filters must survive navigation within the session. Selecting a row opens a
responsive symbol detail drawer or route without losing Tape state.

### Symbol detail

Show the transparent funnel rather than a master opportunity score:

- every Watch/Trade/Act gate with pass/fail/unknown and reason;
- Structure, strength/rotation, sub-industry, regime, extension, earnings, and
  setup evidence as separate sections;
- all setup instances without choosing a primary setup;
- current sizing evidence and an obvious path to the Sizer what-if;
- a clearly labeled manual `Review chart in Deepvue` handoff affordance that does
  not scrape, embed, or require Deepvue. If no safe documented deep link exists,
  provide a copy-symbol/manual-review interaction instead of inventing one.

### Sizer

Provide an interactive form for exact symbol, direction, account equity, available
buying power, proposed entry, and proposed stop. Submit to `POST /sizer` and render
all canonical results: base/allowed risk, stop distance dollars/percent/ATR, full
and pilot shares, capital-constrained shares, costs, planned risk, unused risk,
and every refusal reason. Never calculate an authoritative share count solely in
the browser.

### Rules

Render live API rule/version metadata and human-readable current hypotheses for
universe, strength/rotation, group gate, regime, extension, earnings, and sizing.
Clearly label uncalibrated hypotheses. Do not hardcode a visually different copy
of the formulas that can drift from the API response.

## State, accessibility, and failure behavior

Every view must provide designed loading, empty, unavailable, stale, and error
states. No blank white page or infinite spinner. A local-snapshot failure must
leave the shell usable while clearly blocking research content.

Meet practical keyboard navigation and semantic-label requirements. State chips
must include text; red/green alone cannot convey meaning. Respect reduced motion.
Avoid tooltips as the only place a reason is available.

Local UI preferences may persist filters, table density, and drawer state only.
Never store credentials, provider data, portfolio values, or snapshot payloads in
browser storage.

## Verification

Add Python tests covering at minimum:

- frozen snapshot and API schemas, deterministic fingerprints, and explicit nulls;
- fixture coverage for every required representative state;
- strict local-snapshot validation and no fixture fallback under a local label;
- health, Brief, Tape, symbol, Sizer, Rules, and error endpoints;
- all Tape filters, stable sorts, pagination bounds, and exact-case symbols;
- Sizer delegation to canonical sizing and refusal propagation;
- OpenAPI determinism/type synchronization;
- no network/provider access, no database access, no production/staged writes,
  and no input mutation;
- complete regressions for all existing engines.

Add frontend tests covering at minimum:

- route rendering and navigation;
- fixture-mode banner and freshness display;
- regime sleeves and funnel counts;
- Tape sorting/filtering, persistence, and row-to-detail flow;
- explicit null/unknown/veto rendering;
- Sizer request/results/refusals;
- loading, empty, stale, API-error, and unavailable-snapshot states;
- keyboard-accessible interactions and labels;
- API contract/type drift.

Run:

- focused Python tests;
- `.venv/bin/python -m pytest`;
- frontend unit/component tests;
- TypeScript typecheck;
- production frontend build;
- lint/format checks for both stacks;
- `git diff --check`.

Document exact local development commands, fixture/local-snapshot selection,
snapshot/API contracts, route behavior, screenshots or rendered-state evidence,
and the boundary for the later real materializer.

## Deferred work

Do not implement real DuckDB/Parquet snapshot materialization, data ingestion,
provider/event retrieval, security-master publication, exposure publication,
portfolio positions/heat, Book, Journal, outcomes, backtests, remote hosting,
authentication, broker connections, or order execution.

The September security-master nanosecond/microsecond publication mismatch remains
a separate deferred blocker and does not block this fixture-backed vertical slice.
