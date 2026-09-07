# Codex Next Task

**Task ID:** AP-CURRENT-FOUNDATION-001

**Status:** READY — approved end-to-end current-foundation milestone

**Issued:** 2026-09-07

**Product baseline:** `f1250d733ec9f2192fd7c361b8c3cbbccccc226c`

**Handoff branch:** `codex/current-foundation-handoff`

## Outcome

Advance Aperture from verified engine/UI/materializer code to the first truthful
real local Workstation V1 snapshot for the initial covered population. Complete
the remaining foundation work in one autonomously sequenced milestone instead of
requesting approval after each ordinary implementation, staging, validation, or
recoverable publication step.

The deterministic V1 product logic is already built. Reuse the existing Structure,
Setup, Leadership/RS, Regime, Decision/Risk, snapshot V2, API, React Workstation,
identity, publication, reconciliation, and materializer contracts. Do not redesign
them, add a new scoring model, or expand test matrices merely for reassurance.

## Branch and completion protocol

1. Fetch origin and create `codex/current-foundation-v1` from the current remote
   head of this handoff branch. Verify ancestry from the product baseline.
2. Target a draft PR to `codex/foundation-authority-v1`.
3. Read `AGENTS.md`, `docs/PROJECT_STATE.md`, this file, the completed foundation
   contracts, publication contracts, universe rules, and materializer contract.
4. Execute all authorized phases below without returning for routine approvals.
   Each phase must validate before the next phase can consume it.
5. Stop only for a material contract contradiction, unavailable credential or
   entitlement, a cap/safety failure, inability to obtain exclusive maintenance,
   or evidence that would make the resulting snapshot dishonest.
6. At completion update this file and `docs/PROJECT_STATE.md`, commit, push, open
   the draft PR, and return the commit SHA, test totals, PR link, published input
   versions, snapshot status/path/date, and only genuine remaining blockers.

## Authorization boundary

This assignment explicitly authorizes:

- code, configuration, tests, and documentation needed for this milestone;
- bounded Massive and FRED data retrieval described below using already configured
  credentials where required;
- isolated staging, full backups, exclusive-maintenance production corrections,
  recoverable publication, exposure/universe/feature rebuilding, and creation of
  a real local Workstation snapshot when every gate passes;
- deterministic offline validation after every network or production phase;
- one commit, push, and draft PR.

It does not authorize:

- unbounded discovery or downloading the full U.S. market history;
- use of raw Deepvue exports, applying any of the 23 proposed crosswalks, or
  changing the exact 29-record non-security disposition;
- overwriting the immutable July or September staged source artifacts;
- weakening point-in-time, identity, publication, coverage, or freshness gates;
- brokerage connectivity, order placement, portfolio automation, cloud hosting,
  PR merging, or `.vscode/settings.json` changes.

Preserve exact backups until the user separately chooses to remove them. Never
log credentials, authorization headers, cookies, environment contents, full query
strings, proprietary rows, or unsanitized provider errors.

## Execution policy

- Start with source hashes, Git state, current production schema, backup presence,
  staging inventory, credential-presence checks, and exclusive-maintenance plan.
- Reuse the proven plan/stage/validate/publish/recover patterns. Production writes
  require fresh preflight hashes, complete backup, no active WAL/readers/writers,
  atomic or transactional application, post-close independent validation, and a
  tested rollback path.
- A failed or incomplete phase cannot feed the next phase. Preserve its evidence
  and continue with independent work that remains safe; stop only when nothing
  useful in this milestone can progress.
- Prefer a working, explainable V1 over additional abstraction. Add only focused
  boundary/regression tests needed by changed behavior, then run the complete
  suite once at the end.

## Phase 1 — certify the corrected adjusted-bar foundation

Revalidate the completed production correction recorded in PROJECT_STATE:

- `daily_bars.volume` is DOUBLE;
- 63,279 existing rows and 11,607 fractional values exactly match all 100 original
  Parquet copies;
- ticker/date uniqueness and all non-volume fields agree;
- the verified full backup remains readable and matches its recorded pre-change
  hash;
- the seven other tables and protected files remain unchanged.

Create fresh post-correction source evidence rather than resealing historical
pre-correction receipts. Preserve the old receipts as immutable history.

## Phase 2 — exact September security-master publication

Use the immutable validated 2026-09-05 staged artifact. Do not refetch it or change
its Parquet bytes, exact-case identities, compatibility projection, exclusions,
collision evidence, Deepvue reconciliation, or unapplied crosswalk reports.

Fix the nanosecond/microsecond `last_updated_utc` publication mismatch with an
explicit exact-precision schema/serialization contract. Add real-artifact tests
and repeat isolated first-publication, identical no-op, interruption/recovery,
changed-same-date rejection, July preservation, and DuckDB/Parquet full-field
agreement simulations.

If every simulation passes, publish that exact September artifact using the
existing confirmed, recoverable publication protocol during exclusive maintenance.
Back up the complete database and affected partition state first. Independently
verify after closing the publishing connection:

- 13,155 exact reference rows;
- unchanged logical fingerprint
  `7d22fab5f8dbffea1c9254124e9c2731006648391519e55543f6058c77c7112b`;
- unchanged Parquet SHA-256
  `d3bd5b75665c646e109e22514839da6771b49070f4ed2998b5e879cdb16fc8fc`;
- exact field-level DuckDB/Parquet agreement;
- July logical content and bytes unchanged;
- complete publication state.

Do not apply crosswalks or publish exposure as a side effect.

## Phase 3 — calendar, provenance, and current market inputs

Publish a versioned local `CalendarV1` from pinned
`exchange-calendars==4.13.2`, calendar `XNYS`, with ordered sessions, aware closes,
early closes, source version, bytes hash, and logical fingerprint. Do not derive
sessions from bars.

Create a new post-correction provenance/publication manifest bound to exact source
artifacts and retrieval receipts. The reviewed source profile is:

- Massive custom daily stock aggregates with `adjusted=true`;
- split-adjusted prices, not dividend total return;
- provider-returned split-adjusted numeric volume preserved as DOUBLE;
- transaction counts integral;
- calendar bound to the published XNYS artifact.

Unknown historical facts remain UNKNOWN, but newly retrieved inputs must have
complete observed/fetch/publication timestamps and hashes. Do not invent historical
attestations.

After offline plan validation, update the initial covered population:

- exact symbols from the reviewed existing 100-symbol adjusted-backfill plan;
- required market ETFs SPY, QQQ, IWM, RSP, and QQQE, deduplicated;
- for covered existing symbols, fetch only missing sessions after verified local
  maxima; for absent QQQE, fetch from 2024-01-02;
- end at the latest completed XNYS session at execution time;
- Massive endpoint only:
  `GET /v2/aggs/ticker/{ticker}/range/1/day/{from}/{to}` with
  `adjusted=true`, `sort=asc`, `limit=50000`;
- at most 125 total HTTP attempts and 25,000 returned rows; one attempt per request,
  failures count, no automatic retry, no redirects or unexpected pagination.

Stage exact results first. Validate identities, response adjusted flags, sessions,
keys, OHLCV, fractional volume, coverage, hashes, and source receipts offline.
Publish only the exact validated staged increment through a recoverable path, then
prove complete DuckDB/Parquet equality. Preserve prior history.

For spot volatility, implement and use the versioned non-security source:

- canonical Aperture identity `$VIX`;
- provider/dataset `Federal Reserve Bank of St. Louis FRED / VIXCLS`;
- source is Cboe Market Statistics;
- daily close, not a security, ETF, futures contract, or intraday proxy;
- retrieve only 2024-01-02 through the latest available observation;
- maximum two HTTP attempts and 1,000 returned observations, no automatic retry;
- record source observation date, retrieval timestamp, covered sessions, missing
  values, licensing/source attribution, artifact hash, and freshness.

FRED lag must remain explicit. It may support a premarket snapshot using the last
completed T only when the observation was available before evaluation time. Never
forward-fill a missing VIX session or substitute VXX/VIXY/VX futures.

## Phase 4 — aligned exposure, population, and features

Rebuild and recoverably publish exposure-policy-v3 against the completed September
master. Preserve exact-case reference identity and use the compatibility boundary;
do not apply proposed mappings.

Build the first dated Aperture research/trade schedule from only the explicitly
covered initial population. Apply the immutable `aperture-universe-v1` rules as
written: price, market-cap, ADV20-dollar, ADR20, exposure/type, and all identity
requirements. Obtain market-cap/reference facts only for the covered candidates
when missing, using `GET /v3/reference/tickers/{ticker}`:

- maximum 110 HTTP attempts and 110 returned records;
- one attempt per exact ticker, no retry or redirect;
- stage and validate before publication;
- retain source/as-of timestamps and explicit missing fields.

Do not claim this 100-symbol covered population is the complete U.S. equity market.
Its scope and all leadership/breadth denominators must be labeled exactly. If the
existing engine contract cannot truthfully represent a bounded initial population,
stop schedule/snapshot publication and report that single contract blocker rather
than changing formulas.

Rebuild derived feature tables from the corrected and updated bars through a
temporary/candidate path with DOUBLE volume. Verify formulas and row-level parity
against the existing pure engines before recoverable publication. Preserve old
feature outputs until replacement validates; do not silently migrate legacy
fields or thresholds.

## Phase 5 — first real local Workstation snapshot

Select the latest T only when all inputs are valid at completed T close and the
next XNYS action session T+1 is known. T must be on or after the immutable Aperture
rules effective date 2026-08-25. The 2026-09-05 master cannot justify T=2026-09-04;
its first possible later session is 2026-09-08.

If the necessary post-September-5 completed session or source observations are not
yet available, finish all preceding ready work and report only the exact clock/data
wait. Do not weaken timing rules.

When a valid T exists, run materializer plan and audit. With zero hard blockers,
build and validate one real normalized `workstation-snapshot-v2` in the authorized
local staging location. Enforce the 24 MiB materializer target and 32 MiB loader
ceiling without dropping records. Start the local API only long enough to verify
health, Brief, Tape, Groups/detail, Sizer, and Rules against that exact snapshot;
run desktop/mobile browser smoke checks and shut it down afterward.

The result must visibly identify LOCAL_SNAPSHOT mode, as-of/action sessions,
freshness, initial-population scope, source/rules fingerprints, denominators,
UNKNOWN/refused evidence, funnel counts, bytes, and logical fingerprint. Do not
call a stale, partial, or historical artifact live/current.

## Verification and report

Run focused tests for changed code, then one complete Python suite; run frontend
component/browser tests, schema/OpenAPI/type synchronization, TypeScript typecheck,
production build, lint/format, and `git diff --check` where applicable. Prove
production/staging/settings preservation around every operation and report exact
intentional production changes separately.

Success is the first fully validated real local snapshot, or completion of every
safe prerequisite with one irreducible external/time blocker. Do not stop merely
because an intermediate planned phase completed.
