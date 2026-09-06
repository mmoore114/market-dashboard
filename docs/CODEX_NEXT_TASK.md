# Codex Next Task

**Task ID:** AP-FOUNDATION-AUTHORITY-001

**Status:** READY

**Issued:** 2026-09-06

**Product baseline:** `ccf31f8f95f090830d2a2f3ff52a173b24c064d2`

**Handoff branch:** `codex/foundation-authority-handoff`

## Goal

Implement the reviewed calendar, adjusted-volume, and source-provenance authority
decisions needed by the local materializer. Produce verified staged evidence and
an exact recoverable migration/publication plan, but do not mutate production or
build a real workstation snapshot.

This milestone should eliminate conceptual ambiguity, not bypass missing data.
The remaining QQQE, spot, identity, and Aperture schedule inputs stay deferred to
later bounded acquisition/publication work.

## Branch and completion protocol

1. Fetch origin and create `codex/foundation-authority-v1` from the current remote
   head of the handoff branch above. Verify ancestry from the product baseline.
2. Target a draft PR to `codex/foundation-reconciliation-v1`.
3. Read `AGENTS.md`, `docs/PROJECT_STATE.md`, this file,
   `docs/foundation-reconciliation-v1.md`, `docs/local-materializer-v1.md`, the
   adjusted-ingestion code/contracts, and snapshot V2 before editing.
4. Complete the bounded milestone autonomously unless a destructive action or
   materially contradictory authoritative contract is encountered.
5. Update this file and `docs/PROJECT_STATE.md`, run verification, commit, push,
   and open the draft PR. Return only the commit SHA, test totals, PR link,
   authority/migration results, remaining blockers, and next bounded action.

## Explicit authority

Authorized:

- code, tests, documentation, immutable source-contract configuration, and a
  direct pinned dependency on `exchange-calendars==4.13.2`;
- installation of that exact PyPI package and only its resolver-required Python
  dependencies when not already available locally;
- no-market-data network access strictly necessary for that package installation;
- read-only inspection of production inputs and existing private staged evidence;
- generation of calendar, provenance, comparison, and migration-simulation
  artifacts only in the existing nonproduction workstation staging workspace;
- isolated migration/recovery simulations using copied fixtures;
- one commit, push, and draft PR for this milestone.

Not authorized:

- unbounded provider access, any endpoint/identity outside the conditional staging
  authority below, or any fetch before its prerequisites pass;
- production DuckDB, Parquet, manifest, calendar, master, exposure, universe, or
  workstation snapshot writes;
- applying a schema migration or publishing a provenance/calendar artifact;
- VIX, security-master, market-cap, taxonomy, earnings, or other acquisition
  outside the exact conditional scope below;
- security-master publication, exposure rebuild, Aperture schedule publication,
  crosswalk application, real snapshot build, production API startup, merge,
  brokerage behavior, or `.vscode/settings.json` changes.

## Conditional bounded current-data authority

Current data may be fetched only if the offline calendar, adjusted-volume writer,
path safety, and staging validator pass first and the exact missing range is
resolved deterministically. A fetch is optional; do not perform it merely because
it is authorized.

If those gates pass, one staged Massive adjusted-aggregate update is authorized:

- endpoint only: `GET /v2/aggs/ticker/{ticker}/range/1/day/{from}/{to}`;
- `adjusted=true`, `sort=asc`, `limit=50000`;
- symbols only: the exact tickers in the existing reviewed 100-symbol adjusted-
  backfill plan, plus deduplicated SPY, QQQ, IWM, RSP, and QQQE;
- for existing symbols, start at the first missing session after verified local
  coverage; for absent QQQE, no earlier than 2024-01-02;
- end at the last completed XNYS session established by the pinned calendar;
- maximum 125 total HTTP attempts and 25,000 returned records;
- every failed request counts; one attempt per request with no automatic retry;
- reject redirects, cross-origin URLs, unexpected pagination, schema/basis
  disagreement, or any cap breach before writing the affected page;
- write exact provider-returned values only beneath a new explicit staging
  subdirectory; never invoke the existing immediate production writer;
- preserve sanitized per-request receipts and completed evidence after failure;
- validate the complete staged candidate offline with exact keys, fractional
  volume, session coverage, hashes, and logical fingerprints.

No spot/VIX request is authorized until its exact non-security provider identity,
dataset, endpoint, and entitlement are reviewed. No security-master refetch is
needed. A successful staged bar fetch still does not authorize database/Parquet
publication, universe construction, exposure rebuild, or a real snapshot build.

## Reviewed authority decisions

Implement these decisions exactly:

1. Calendar implementation: `exchange-calendars==4.13.2`, calendar `XNYS`.
   Record the package version, XNYS identity, timezone, ordered sessions, regular
   and early closes, generation range, artifact hash, and deterministic command.
   Do not infer sessions from observed bars.
2. Massive adjusted aggregate endpoint semantics: `adjusted=true` means adjusted
   for splits. It is not a dividend-total-return series. Preserve this distinction
   explicitly in the source contract.
3. Provider aggregate `v` is numeric, and the provider-returned fractional values
   written to the existing Parquet files are the authoritative representation of
   those observed rows. The current DuckDB `BIGINT` values are a lossy rounded
   derivative, not an alternative canonical source.
4. Canonical adjusted volume must preserve the provider-returned numeric value as
   `DOUBLE` end to end. Never round, truncate, cast to integer, or silently choose
   between copies. Transaction count remains integral.
5. This decision establishes representation authority; it does not authenticate
   missing historical provider receipts or declare the existing database repaired
   or published.

Authoritative references reviewed 2026-09-06:

- `https://massive.com/docs/rest/stocks/aggregates/custom-bars`
- `https://github.com/gerrymanoim/exchange_calendars`
- `https://github.com/gerrymanoim/exchange_calendars/releases/tag/4.13.2`

## Calendar implementation

- Add a narrow adapter that converts the pinned XNYS schedule into the existing
  frozen `CalendarV1` without changing that contract.
- Preserve timezone-aware actual closes and correctly identify early closes.
- Reject unsupported calendar identity/version, duplicate or unordered sessions,
  naive or non-UTC-convertible closes, out-of-range requests, and a package-version
  mismatch.
- Generate and independently validate a candidate calendar in staging covering
  all sessions required to assess the current bar history and candidate T/T+1.
- Bind calendar logical fingerprint and bytes to the candidate provenance evidence.
  The staged calendar is not production publication.

## Adjusted-volume and provenance implementation

- Change new `daily_bars` table creation and new writes so `volume` is `DOUBLE`.
- Add schema checks that fail closed when an existing table remains `BIGINT`; do
  not auto-alter it from ordinary ingestion or materialization.
- Preserve fractional volume through API mapping, pandas, Parquet, DuckDB, hashing,
  comparison, features, and replay. Audit every downstream integer assumption.
- Record sanitized response-level evidence needed for future ingestion receipts,
  including endpoint class, requested/returned adjusted flag, source version,
  requested and observed bounds, and artifact fingerprints. Do not persist keys,
  authorization headers, query strings, or raw responses.
- Define a versioned provenance profile stating split-adjusted price, no dividend
  total-return adjustment, and matching provider-returned split-adjusted numeric
  volume. Unsupported publication/observation facts remain UNKNOWN.
- Re-evaluate the staged candidate manifest field by field. Do not relabel it as a
  complete `ManifestV1` unless every required field has verifiable evidence.

## Recoverable migration simulation

Implement an explicit offline plan/simulate/validate workflow for a future
`daily_bars.volume BIGINT -> DOUBLE` correction.

- Plan mode opens no files/databases, performs no network calls, and writes nothing.
- Simulation uses copies only and creates a replacement table/database outside
  production. Load exact Parquet volume values by `(ticker,date)`, require identical
  keys and all non-volume fields, and reject missing/extra/duplicate rows.
- Verify all 63,279 current keys and all 11,607 fractional values can be restored,
  with full DuckDB/Parquet field equality and deterministic fingerprints.
- Exercise pending, complete, interrupted/recovery-required, verified recovery,
  identical rerun/no-op, and changed-input rejection states.
- Produce exact backup, maintenance-window, apply, verification, and rollback
  commands for later approval. Do not expose an executable production apply mode
  under this task.

## Rules-date and forward-target handling

The separate `APERTURE_RULES_AFTER_CANDIDATE_T` result is correct, not a formula
bug. `aperture-rules-v1` must not be projected before its 2026-08-25 effective
date. Retain it as a timing constraint and state that a real target T must be a
valid XNYS session on or after that date with master, exposure, universe, bars,
benchmarks, and spot evidence valid for the same point in time.

Do not use the unpublished 2026-09-05 security master, project July 26 identity
backward, or invent a feasible T/T+1 pair.

## Reconciliation and acceptance

Rerun the existing offline reconciliation using the pinned calendar and reviewed
authority profile. Report separately:

- calendar finding disposition;
- volume representation authority versus still-unapplied production correction;
- provenance fields established and fields still UNKNOWN;
- exact migration simulation row/mismatch/fingerprint results;
- original eight-finding conservation and any separate findings;
- remaining prerequisites for an identity-valid post-2026-08-25 target;
- the next minimal acquisition/publication milestone.

Tests must cover the pin/version gate, known XNYS holidays and early closes,
timezone conversion, deterministic calendar generation, fractional volume
round-trips, existing BIGINT refusal, response metadata sanitization, migration
state/recovery/no-op/rejection behavior, zero market-data calls, no production
writes, protected-file preservation, and unchanged engine/snapshot semantics.

Run focused tests, the full Python suite, applicable frontend/browser and
schema/type synchronization checks, and `git diff --check`.

Do not build a real workstation snapshot in this milestone. Success means calendar
and representation authority are deterministic and the real correction/acquisition
boundary is ready for one later reviewed action.
