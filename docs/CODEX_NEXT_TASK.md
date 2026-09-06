# Codex Next Task

**Task ID:** AP-LOCAL-MATERIALIZER-001

**Status:** COMPLETE

**Issued:** 2026-09-06

**Base commit:** `64ff541ce99d7735e0c3cccc28d3dc9f13809d1b`

## Handoff protocol

This file is the single current assignment for VS Code Codex.

1. Read `AGENTS.md`, `docs/PROJECT_STATE.md`, the Workstation V2 contract, every
   completed engine contract, and the existing data/storage documentation before
   editing.
2. Implement the complete bounded offline materializer and run its read-only
   readiness audit against the actual local repository data.
3. Work autonomously unless contracts materially contradict, a destructive write
   is required, or provider/publication authority would be required.
4. At completion, mark this task `COMPLETE`, add a concise completion record,
   update `docs/PROJECT_STATE.md`, commit, push, and open a draft PR targeting
   `codex/workstation-snapshot-v2` so it contains only this milestone.
5. Return only the full commit SHA, focused/full test totals, frontend regression
   results, draft PR link, readiness status, staged snapshot path if one was safely
   produced, and genuine blockers. Keep detailed evidence in the repository or
   explicit local audit workspace.

Preserve `.vscode/settings.json`, `.env`, credentials, production databases,
Parquet/CSV datasets, staged security-master artifacts, generated provider
reports, and unrelated user changes.

## Milestone

Implement the offline local-data-to-Workstation materialization boundary:

```text
verified published local inputs
-> point-in-time engine replay/orchestration
-> normalized workstation-snapshot-v2
-> strict validation
-> existing FastAPI/React Workstation
```

Create and work on:

`codex/local-materializer-v1`

This milestone does not fetch or publish market data. It makes the completed
engines and Workstation executable against explicitly selected, verified local
inputs, and produces an exact readiness report when those inputs are insufficient.

## Authoritative sources

Read and follow:

- `AGENTS.md`
- `docs/PROJECT_STATE.md`
- `docs/architecture_decision.md`, especially ingestion, features, states,
  snapshot and API boundaries
- `docs/aperture_product_contract.md`
- `docs/workstation-slice-v1.md`
- `docs/workstation-snapshot-v2.md`
- every completed Structure, Setup, Leadership, Regime, and Decision/Risk
  implementation contract
- security identity, security-master, exposure, universe, adjusted-history,
  taxonomy/theme and publication documentation
- existing builders, validators, schemas, manifests and immutable configuration

Existing engine formulas and state semantics are frozen. Orchestration may adapt
verified data into those contracts; it must not create alternative calculations.

## CLI and modes

Add `scripts/materialize_workstation_snapshot.py` with explicit modes:

- `plan`
- `audit`
- `build`
- `validate`

### Plan

Plan mode must open no database, make no network request, and write nothing. It
validates arguments and path safety, resolves the requested input/output plan,
names every required/optional source, computes a deterministic plan fingerprint,
and prints the exact next command.

### Audit

Audit mode may read only explicitly supplied files and open DuckDB strictly
read-only. It must not create a WAL, temporary production table, checkpoint, or
modified access timestamp where avoidable. It writes only a deterministic
readiness report and receipt into an explicit audit workspace outside production
data directories.

Audit must distinguish:

- `HARD_BLOCKER`: unsafe identity/provenance, contradictory or corrupt data,
  missing required foundational input, invalid publication state, or an engine
  replay that cannot be represented honestly;
- `EVIDENCE_GAP`: missing optional decision context that can be represented as
  UNKNOWN/refused without corrupting the snapshot, such as absent earnings
  coverage, group membership, or caller trade proposal;
- `READY`: verified input for its declared use.

Evidence gaps may reduce promotion but do not automatically block a truthful
snapshot. Hard blockers do.

### Build

Build mode requires the exact successful audit receipt and plan fingerprint. It
rechecks all source hashes before and after reading, makes no network request,
opens production inputs read-only, and writes only to an explicit standalone
staging output outside repository production/staging-provider directories.

Build must use a same-directory temporary file, fsync where supported, validate
the complete result, and atomically rename to the requested `.json` target. A
failure preserves a sanitized receipt and never leaves a file labeled valid.

Do not mutate DuckDB, Parquet, manifests, exposure, universe, taxonomy, themes,
security master, event sources, or existing Workstation artifacts.

### Validate

Validate mode is fully offline and accepts only a standalone V2 snapshot plus its
receipt. It verifies hashes, normalized evidence integrity, fingerprint, row and
funnel counts, version alignment, field-level engine parity evidence, size limit,
and successful strict `SnapshotStore` loading. It writes no production data.

## Explicit materialization plan

Use a frozen, extra-field-forbidding `MaterializationPlanV1` and
`MaterializationReadinessV1`. Require explicit paths and versions for:

- the local DuckDB or Parquet market-data source;
- a source/provenance manifest;
- exchange-session calendar;
- security-master snapshot/publication evidence;
- exposure classification snapshot/publication evidence;
- dated research/trade universe snapshot;
- adjusted daily bars;
- optional published taxonomy and theme membership;
- optional standardized earnings/event evidence and coverage;
- optional caller decision proposals containing account equity, buying power,
  exact symbol/direction, proposed entry and proposed stop;
- requested as-of session, action session, and output freshness deadline.

Do not discover arbitrary files by scanning the repository. Configuration may
provide defaults, but the resolved plan must record exact absolute targets,
logical versions, artifact hashes, row/date bounds and table/partition names.
Diagnostics and receipts must sanitize credentials, query strings, environment
values and proprietary row contents.

## Source and publication gates

Require exact-case security identity and the existing ReferenceTicker to
MarketDataSymbol compatibility boundary. Never uppercase or casefold a provider
identity as an automatic join.

Accept only publication states explicitly documented as complete. Bind downstream
inputs to their exact security-master, exposure-policy and universe-policy
versions. Reject pending/recovery-required states, duplicate keys, unexplained
case collisions, mismatched dates, or same-version contradictory artifacts.

The unresolved September nanosecond/microsecond security-master publication issue
remains a blocker to using that unpublished artifact. Do not read the staged
provider artifact as production and do not repair or publish it here. Audit may
truthfully use an earlier complete published snapshot only for an as-of session
within its valid identity interval and must report its age.

Taxonomy/theme data is context only when it comes from a completed, dated local
publication with exact symbol reconciliation. Never read raw Deepvue exports,
infer parent hierarchies, apply crosswalk proposals, or silently drop unmatched
members. Missing group context becomes explicit UNKNOWN where the engine allows;
contradictory membership is a hard blocker.

## Market data and calendar gates

Require a caller-supplied provenance manifest that explicitly attests:

- provider/dataset identity;
- split-adjusted price basis;
- dividend treatment;
- matching split-adjusted volume convention;
- exchange-calendar identity and artifact hash;
- observation/fetch/publication timestamps and covered date range.

Do not infer adjusted semantics from a table name or `adjusted=true` memory. Reject
mixed bases, duplicate symbol/session rows, nonfinite/invalid OHLCV, dates outside
the supplied calendar, future observations, and contradictory DuckDB/Parquet
copies. Never forward-fill prices, synthesize sessions, or turn missing history
into zero.

Audit exact coverage for the research universe and required market series:

- SPY, QQQ and IWM;
- RSP and QQQE;
- VIX or an explicitly versioned equivalent spot-volatility series using its
  non-security identity;
- every exact equity research member needed for cross-sectional ranks and
  breadth.

Derive warmup requirements from the completed feature/engine contracts rather
than inventing a new fixed lookback. Report per-engine and per-symbol valid/missing
session counts, first/last dates, gaps, insufficient histories, and denominator
coverage.

## Engine orchestration

Create a deterministic orchestration layer under
`src/market_dashboard/workstation/materialization/`.

For an explicit as-of T and exact action session T+1, use only evidence available
at completed T close. Replay enough prior exchange sessions to establish:

- shared Wilder ATR, moving averages, returns, volume and setup features;
- Structure state and hysteresis;
- Setup instances, frozen geometry and lifecycle;
- 5/21/63/126/252-session Leadership components, RS composite, rotation and group
  ranks across the exact point-in-time research population;
- all five Regime sleeves, aggregate hysteresis and T+1 eligibility;
- direction-aware extension, earnings evidence, Watch/Trade/Act gates and sizing;
- normalized `workstation-snapshot-v2` through the reviewed V2 materializer.

Call the existing pure engines and adapters. Do not duplicate their formulas in
SQL, the orchestrator, API or TypeScript. SQL/Polars may select and reshape verified
inputs only.

Process symbol histories in bounded batches or streams; do not expand and retain
the full duplicated V1 evidence population for every symbol simultaneously. Use
the normalized V2 boundary and remain within documented local memory/size limits.

Preserve point-in-time membership revisions. A symbol that lacks required history
must retain explicit insufficient-data evidence where the engine contract permits;
do not remove it merely to improve coverage. If an engine contract requires a
complete population or history that cannot be formed, report a hard blocker or
UNKNOWN exactly as that contract specifies.

## Earnings and trade proposals

The materializer performs no event lookup. Standardized caller-supplied event
records and explicit complete/fresh calendar coverage are the only way to produce
earnings `CLEAR`. Missing, stale or incomplete evidence remains `UNKNOWN` and
blocks ACT without blocking the entire snapshot.

Do not invent entry prices or convert setup invalidation into a trade stop.
Decision proposals are optional exact symbol/direction inputs. Without a proposal,
entry, stop, account equity and buying power remain null and sizing is refused;
the symbol may reach no higher than TRADE. The interactive Sizer remains available
for discretionary what-if work.

If a proposal is supplied, validate its as-of/action session, provenance and exact
identity. Account equity is the risk denominator and buying power remains only a
capital constraint.

## Snapshot semantics

Produce `mode=LOCAL_SNAPSHOT` only. Freshness may be `FRESH` only when the explicit
freshness deadline and every required source attestation support it. Historical or
stale materializations remain valid evidence artifacts but must be labeled STALE
and will be refused by the current live Workstation routes.

Retain all exact records rather than only Watch/Trade/Act names. Funnel totals must
reconcile to records. Shared context must be stored once through V2 normalization.
Enforce the 24 MiB materializer target and 32 MiB loader ceiling; if the exact
research population cannot fit, fail with measured component sizes rather than
dropping records.

Record plan, source and rules fingerprints, source artifact hashes, row/session/
symbol counts, per-engine coverage, evidence-gap counts, funnel counts, output
bytes/hash, logical fingerprint, timings and peak-memory diagnostics in receipts.
Timestamps must not affect logical fingerprints.

## Actual local audit and conditional staged build

After mocked/synthetic implementation tests pass:

Use this explicit audit/build workspace:

`/home/mattcarmenmoore/aperture-staging/workstation-local-snapshot-v1`

1. Run `plan` against the actual configured local paths with no database access.
2. Run one read-only `audit` against the laptop's actual local data.
3. Preserve and report every readiness result; do not repair inputs in this task.
4. If and only if there are zero hard blockers, run one `build` into that same
   explicit workspace.

5. Validate that exact staged snapshot offline and start the API against it only
   long enough for automated health/Brief/Tape/detail/Sizer/Rules smoke tests.
6. Do not label or report it current/live unless all freshness requirements pass.
7. If any hard blocker exists, do not build; return the exact next bounded data
   action needed. Do not fetch, publish, rewrite, or retry anything automatically.

Before and after, hash/prove production data, staged security-master evidence,
Git state and `.vscode/settings.json` unchanged.

## Verification

Add focused tests covering at minimum:

- all four modes and path-safety boundaries;
- plan mode zero database/network/write behavior;
- strictly read-only audit and source hash preservation;
- hard-blocker versus evidence-gap classification;
- publication/version/identity/case/provenance gates;
- calendar, basis, duplicate, OHLCV and coverage failures;
- point-in-time replay with no T+1 leakage or future mutation;
- Structure/Setup/Leadership/Regime/Decision orchestration parity with direct
  pure-engine calls;
- missing history, group, event and proposal behavior;
- normalized V2 streaming/batching, deterministic fingerprints and size limits;
- atomic staged output and interrupted-build cleanup;
- strict validation and API smoke behavior;
- sanitized errors and receipts;
- zero provider access and no production/staged-source mutation;
- complete existing Python and frontend regressions.

Run focused and full Python suites, frontend component/browser regressions,
OpenAPI/snapshot-schema/type synchronization, TypeScript typecheck, production
build, lint/format checks, and `git diff --check`.

Document the source contract, CLI examples, replay/dataflow, blocker semantics,
receipt format, operating limits and exact boundary to future ingestion.

## Deferred work

Do not fetch provider data, publish/fix the security master, rebuild exposure or
universes, apply crosswalks, import raw Deepvue data, retrieve events, mutate
production storage, implement portfolio/Book/Journal, host remotely, authenticate,
connect brokers, or place orders.


## AP-LOCAL-MATERIALIZER-001 completion record — 2026-09-06

Implemented on `codex/local-materializer-v1` from exact handoff
`866b15a09773c56dcbf72530bf077b9def9355e9`. The four-mode offline boundary,
strict source/readiness contracts, canonical point-in-time replay, normalized
streaming output, receipt-bound validation and no-clobber atomic publication are
complete. [Source contract, commands, limits and audit evidence](local-materializer-v1.md).

Observed verification: **46 materializer focused tests** and **93 workstation
focused tests passed**; final full Python suite **2,780 passed**. **11 frontend
component tests** and **two desktop/mobile Chromium tests passed**. TypeScript,
production build, OpenAPI/snapshot-schema/type synchronization, Python/frontend
lint/format and whitespace checks passed. The existing Starlette TestClient
httpx deprecation warning remains nonblocking.

The one actual read-only audit returned **8 HARD_BLOCKER findings** and five
optional evidence gaps. No real snapshot was built. Missing selected calendar,
provenance and spot inputs, bars/legacy-universe cross-store disagreement, the
legacy universe contract, master/as-of identity timing and mandatory benchmark
coverage prevent materialization. Per-engine denominators cannot be certified
without the missing calendar and actual Aperture research membership.

All 337 protected files (112,487,134 bytes), including September staged evidence,
production data, environment file and user VS Code settings, retained their
hashes. Git status/diff were identical across the actual audit. Private reports
and preservation proof remain in the authorized workspace; no licensed data,
source artifact, credential or machine settings is included in the commit.

Next bounded data action: separately scoped offline foundation reconciliation
of source copies, an authoritative exchange calendar and reviewed provenance,
and an identity-valid published Aperture research/trade schedule for a selected
T, followed by exact missing benchmark/spot/research coverage assessment. No
repair, publication, fetch, crosswalk application or automatic retry is authorized
by this completed task. Do not consume the unpublished September master.
