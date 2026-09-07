# Codex Next Task

**Task ID:** AP-CURRENT-BOOTSTRAP-001

**Status:** COMPLETE — real current-state snapshot validated and desktop/mobile smoke passed

**Issued:** 2026-09-07

**Product baseline:** `e678049bb1093db3164fd540d2197aee74c03845`

**Handoff branch:** `codex/current-bootstrap-handoff`

## Outcome

Use the fully published current foundation from AP-CURRENT-FOUNDATION-001 to build,
validate, and locally exercise the first real Aperture Workstation snapshot for the
September 6 decision context:

- market observations through `T=2026-09-04`;
- the recorded evaluation timestamp `E`, which is September 6 in New York;
- next XNYS action session `A=2026-09-08`;
- the explicitly bounded current population selected with evidence known by `E`
  for eligibility on `A`.

The remaining blocker is a representation mismatch, not missing market data.
Implement a versioned current-state bootstrap/replay contract. Do not require
verifiable historical membership merely to calculate today's state, and do not
mislabel current-cohort retrospective calculations as point-in-time historical
membership or backtest evidence.

## Branch and completion protocol

1. Fetch origin and create `codex/current-bootstrap-v1` from the exact remote head
   of this handoff branch. Verify the product baseline is its parent.
2. Target a draft PR to `codex/current-foundation-v1`.
3. Read `AGENTS.md`, `docs/PROJECT_STATE.md`, this file,
   `docs/current-foundation-v1.md`, the universe/leadership/materializer
   contracts, snapshot V2, and the canonical engine decision overlay.
4. Work through the complete milestone autonomously. Do not stop for ordinary
   implementation choices already governed here.
5. Stop only for a material contradiction between authoritative numerical
   contracts, corrupted published inputs/backups, or a destructive/external action
   outside this authorization.
6. At completion update this file and PROJECT_STATE, commit, push, open the draft
   PR, and return only the commit SHA, test totals, PR link, snapshot path/size/
   fingerprint, population/funnel counts, smoke-test result, and genuine blockers.

## Authorization boundary

Authorized:

- code, configuration, documentation, focused regression tests, and contract/schema
  changes required for the bootstrap;
- recoverable publication of the already staged September 8 population schedule;
- building and validating one real normalized `workstation-snapshot-v2` in the
  approved local snapshot location;
- brief loopback startup of the local API and desktop/mobile browser smoke tests
  against that exact snapshot, followed by shutdown;
- full backups and isolated/recoverable simulations needed for the one schedule
  publication;
- one commit, push, and draft PR.

Not authorized:

- new provider acquisition or refetching already published inputs;
- changing any Structure, Setup, Leadership/RS, Regime, Decision/Risk, actionability,
  sizing, or universe threshold/formula;
- inventing, backdating, forward-filling, or imputing prices, membership, market
  cap, reference facts, VIX, or sessions;
- claiming this bounded cohort is the full U.S. market;
- publishing a historical research-membership schedule before September 8;
- making bootstrap results available as historical Time Machine/backtest evidence
  before the bootstrap effective session;
- crosswalk application, raw Deepvue publication, brokerage behavior, hosting,
  PR merging, backup deletion, or `.vscode/settings.json` changes.

No network request should be necessary. If a published artifact fails its recorded
hash or completeness gate, stop rather than reacquire it under this task.

## Current-state bootstrap contract

### Separate calculation identity from historical membership

The bootstrap has two distinct truths:

1. Each symbol's Structure, Setup, feature, and other time-series calculations use
   only that symbol's real observed market history through September 4.
2. The cross-sectional cohort is the population known at evaluation time for
   possible action on September 8.

It is valid to apply the current cohort to its actual historical price series to
calculate the current September 4 state. This is an **as-known-at-E current scan**.
It is not evidence that the cohort, ranks, or denominators were known on earlier
dates.

Preserve these labels and dates in the plan, manifest, snapshot, API, UI, receipts,
and logical fingerprint:

- calculation mode: `CURRENT_STATE_BOOTSTRAP`;
- market-as-of session: September 4;
- evaluation timestamp: the already recorded September 6 New York decision time;
- action/population-effective session: September 8;
- population scope: bounded initial covered population;
- historical-membership status: `UNKNOWN_BEFORE_BOOTSTRAP`.

### Population and ranks

Use the validated staged action population without changing its rules:

- 75 research members;
- 49 strict trade members;
- 25 market-mapping members.

Publish it recoverably with first effective session September 8. Do not create
earlier dated membership rows.

For the September 4 snapshot:

- compute current cross-sectional ranks and group/breadth denominators over the
  explicitly identified current research cohort using only observations dated on
  or before September 4;
- label them as current-cohort/evaluation-time results;
- do not persist or expose them as historical point-in-time ranks for dates before
  September 8;
- preserve excluded, ineligible, and UNKNOWN reasons rather than silently shrinking
  a denominator;
- retain the existing bounded-population warnings in every applicable surface.

Any current-cohort retrospective series required solely to warm up an existing
formula must carry the same bootstrap label and may support only the current
snapshot. It must not be reused as historical membership evidence.

### Sparse per-symbol calendar alignment

Replace the shared-dense-index assumption at the materializer boundary; do not
change engine mathematics.

- XNYS remains the canonical market calendar and defines T, A, session distances,
  lifecycle timing, and freshness.
- Each symbol retains its actual dated observations and may begin after the common
  history start.
- Leading dates before a symbol's first observation are explicit
  `NOT_YET_OBSERVED`, not missing bars.
- Missing internal XNYS observations remain explicit `MISSING_OBSERVATION`.
- Never synthesize OHLCV, shift a symbol onto another date, compress calendar time,
  forward-fill, or drop a symbol merely to make indices equal.
- Adapt sparse dated histories into the pure engines while preserving their
  existing lookback and session semantics. If a required value cannot be computed
  honestly across a gap, emit the existing UNKNOWN/refused evidence for that
  symbol/component.
- The five stocks and all 914 reported absent slots must remain accounted for.
  A symbol-level UNKNOWN must not veto unrelated valid symbols or the entire
  snapshot unless an existing canonical global gate explicitly requires it.

Add deterministic reason/evidence counts for not-yet-observed, internal missing,
insufficient-history, and valid-current outcomes.

## Materialization and Workstation acceptance

1. Revalidate all published input hashes and completion states without rewriting
   the completed foundation.
2. Simulate schedule first publication, interruption/recovery, and identical no-op
   on copies. Then publish the exact staged September 8 schedule recoverably with
   a verified pre-write backup and independent post-close comparison.
3. Build one real `workstation-snapshot-v2` for T/E/A above. A missing September 4
   VIXCLS observation remains the canonical Volatility UNKNOWN evidence and does
   not veto other valid sleeves or the snapshot.
4. Validate full schema, evidence references, canonical engine parity, three-clock
   bindings, population accounting, denominators, bytes, and logical fingerprint.
5. Enforce the 24 MiB materializer target and 32 MiB loader ceiling without dropping
   records.
6. Start the loopback API against that exact file only long enough to verify health,
   Brief, Tape, Groups/detail, Sizer, Rules, and explicit Time Machine refusal
   before September 8. Run desktop and mobile browser smoke tests, then shut it down.
7. The Workstation must visibly show `LOCAL_SNAPSHOT`,
   `CURRENT_STATE_BOOTSTRAP`, market September 4, evaluated September 6 New York,
   action September 8, bounded population scope, source/rules fingerprints,
   freshness/UNKNOWN evidence, and funnel/denominator counts.
8. Do not call this a historically reproducible snapshot before the bootstrap
   effective boundary. It is a truthful current decision snapshot with reproducible
   source evidence.

## Verification

Add focused tests for:

- current-state versus historical-replay provenance;
- no pre-September-8 membership publication;
- current-cohort rank/denominator labeling;
- sparse leading and internal calendar gaps;
- no imputation, date shifting, silent symbol dropping, or denominator shrinkage;
- symbol-level UNKNOWN isolation;
- all five affected stocks and 914 absent slots remaining accounted for;
- stable formulas and exact pure-engine parity;
- schedule publication recovery/no-op;
- snapshot validation, size, clocks, API metadata, and Time Machine refusal;
- zero provider requests and preservation of all completed foundation artifacts,
  backups, Git state, and settings.

Run focused tests, then the complete Python suite once. Run frontend component and
desktop/mobile browser tests, OpenAPI/schema/type synchronization, TypeScript
typecheck, production build, lint/format, and `git diff --check`.

Success means a real, loadable local current-state snapshot and verified Workstation
smoke result. Do not reopen completed master, bars, calendar, exposure, feature, or
source-publication work unless its preserved validation evidence actually fails.


## AP-CURRENT-BOOTSTRAP-001 completion — September 7 UTC / September 6 New York

Built and independently validated the first real LOCAL_SNAPSHOT as
CURRENT_STATE_BOOTSTRAP. T is September 4; the preserved E is September 7
01:53:42.451047 UTC (September 6 in New York); A is September 8. This is a current
cohort calculation with UNKNOWN_BEFORE_BOOTSTRAP historical membership, not
historical point-in-time ranks or backtest evidence.

The exact first-action schedule is complete, with 101 covered symbols, 75 research,
49 strict trade and 25 mapping members. No membership was published before A.
First publication, staged/published interruption recovery and identical no-op
passed on real-candidate copies before publication. A full verified database backup
and candidate copy remain retained. The production database did not change.

The snapshot contains 75 records and 1,865,976 bytes (below 24 MiB/32 MiB limits).
Logical fingerprint:
`d10b6c0b62d403755aa7be08e8c378fb7b694c3c1254cbfcc2ff282b899b8012`.
Byte SHA256:
`6b2c93aad6ce62a8963eb30035c2ec533faea47d1d47212526efc4efaac2c898`.
Canonical funnel: NONE 66, WATCH 9, TRADE 0, ACT 0. All 75 current Structure
outputs are valid; insufficient-history outcomes are zero. All five sparse
histories and 914 leading NOT_YET_OBSERVED slots are accounted for; internal
MISSING_OBSERVATION slots are zero. Canonical current rank denominators are 75.

Volatility remains UNKNOWN for the missing September 4 VIXCLS observation.
Breadth/internals retain their existing minimum-count and absent-group UNKNOWN
reasons; thresholds were not weakened for this bounded cohort. Groups explicitly
reports absent published membership. These are valid component evidence outcomes,
not whole-snapshot blockers. No provider acquisition, price imputation, crosswalk
application, raw Deepvue publication or trading behavior was introduced.

Observed verification: 87 focused Python tests, then the single full run of
2,871 passing tests. Final sparse-count validation passed all seven bootstrap
regressions; final API denominator projection passed 34 snapshot/API regressions.
Frontend: 13 component tests, synchronized API types, TypeScript checking,
production build and lint/format passed. Real desktop 1366px and mobile 390px
browser smoke: two tests passed against the exact snapshot, including health,
Brief, Tape/detail, Groups/detail refusal, Sizer, Rules and explicit pre-September-8
Time Machine refusal. Temporary loopback services shut down after testing.
OpenAPI/schema checks and whitespace checks passed.

All 1,348 protected prework files retain their hashes, including completed
foundation artifacts, prior staging/receipts/backups, environment and user settings.
The 114 bound foundation/backup/schedule hashes were independently rechecked.
Zero provider requests. The standalone snapshot, exact paths, receipts, source
records and browser evidence remain private and uncommitted. See
[current-bootstrap-v1.md](current-bootstrap-v1.md) for the versioned contract and
registry compatibility boundary. No remaining milestone blocker.
