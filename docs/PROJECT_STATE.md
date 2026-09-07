# Aperture Project State

Updated: 2026-09-07

Current product authority: `docs/APERTURE_CURRENT_AUTHORITY.md`

Working prototype baseline: `401e1b0afd6ad2a4678af4f1040014b5c9b568e9`

## Current outcome

Aperture has a working local React/TypeScript Workstation backed by FastAPI and a
real normalized `LOCAL_SNAPSHOT`. The snapshot was built as a truthful
`CURRENT_STATE_BOOTSTRAP` using market evidence through September 4, an evaluation
on September 6 New York time, and September 8 as the first action/population
session.

Validated snapshot facts:

- 75 equity-research members;
- 49 strict equity-trade members;
- 25 market-mapping members;
- funnel: 66 `NONE`, 9 `WATCH`, 0 `TRADE`, 0 `ACT`;
- size: 1,865,976 bytes;
- logical fingerprint:
  `d10b6c0b62d403755aa7be08e8c378fb7b694c3c1254cbfcc2ff282b899b8012`;
- Python, frontend, schema/type, build/lint, and desktop/mobile browser verification
  passed at the recorded baseline;
- snapshot and retained backups remain local and uncommitted.

The Workstation services were stopped cleanly after verification. The prototype
can be relaunched from the retained local snapshot.

## Implemented layers

- Massive-backed security and adjusted daily-bar foundation;
- DuckDB/Parquet storage with provider-preserving fractional volume;
- versioned exposure and universe policies;
- pinned XNYS exchange calendar and source provenance;
- deterministic Structure and Setup V1 engines;
- Leadership/RS and group-ranking engine;
- five-sleeve Market Regime engine;
- Decision/Risk, actionability, and sizing engine;
- normalized snapshot V2 and offline materializer;
- typed FastAPI service;
- React Workstation surfaces: Brief, Tape, symbol detail, Groups, Sizer, Rules;
- current-state bootstrap and Time Machine refusal before historical membership is
  available.

## Known product gaps

- The current snapshot does not contain published group membership, so Groups
  presents explicit missing evidence.
- Deepvue sub-industry and theme captures are verified bootstrap sources but remain
  local and are not runtime dependencies.
- Earnings/catalyst coverage is incomplete.
- The initial population is bounded, not the full U.S. equity research universe.
- Book, Journal, benchmark learning, and routine daily refresh remain future work.
- The current UI needs user-driven workflow and visual refinement.
- Aperture intentionally does not include charts; Deepvue handles chart review.

## Engine alignment status

`AP-ENGINE-ALIGNMENT-001` is implemented and verified on the V2 branch. Runtime V1
remains reproducible and is still the default materializer selection. V2 is an
explicit coherent `structure-engine-v2` / `setup-engine-v2` pair; no production
source data or existing snapshot was relabeled.

- Structure V2 uses the verified final Word SMA20/SMA50 model, median-ATR slopes,
  ten-session persistence, confirmation/retention hysteresis, and transitional-only
  D50 shock overrides. EMA10/SMA200 are context only.
- Setup V2 uses Word closing-dispersion contraction, robust 20-session range,
  mature-trend-only pullbacks, and 40/60-session pre-trigger limits.
- Prior-session geometry, stable version-scoped birth identities, failure-first
  ordering, terminal non-reactivation, corporate-action quarantine, and corrected
  replay are retained.
- Materialization, normalized evidence, decision/regime context, symbol detail,
  and Rules explicitly carry the selected engine identities.

A separate `ENGINE_VERSION_COMPARISON` snapshot was built from the verified retained
inputs. It has 75 valid current Structure records and funnel 63 NONE / 12 WATCH /
0 TRADE / 0 ACT, versus the preserved V1 funnel 66 / 9 / 0 / 0. Structure changes:
28 of 75; active setup sets change for 63 symbols. The eight-symbol, 126-session
sample has 362 differing states out of 1,008 observations and 69 V2 transitions
versus 56 V1 transitions. This is not a claim of reduced churn or predictive lift.

Comparison snapshot bytes: 2,146,854. Logical fingerprint:
`e7e2b78be213dbf51919012bbc4ddbf34ee4e58ce495be8d50c45246aa386a73`.
The original evidence/evaluation/action clocks are unchanged. The comparison
retains expiry at 2026-09-08 00:00 UTC and must be refused as stale afterward.

Verification: 2,910 Python tests passed, four optional real-artifact tests skipped;
13 frontend component tests and two desktop/mobile comparison browser tests
passed. TypeScript, production build, scoped lint/format, schema/type sync and
whitespace checks passed. Both services stopped, and all 1,383 protected baseline
files—including settings, source data, original snapshots and backups—remained
byte-identical. No provider requests or production publications occurred.

See [the implementation contract](engine-alignment-v2.md) for material source
ambiguities and selected interpretations, and
[the completion receipt](engine-alignment-v2-receipt.md) for final evidence and
limitations. Book, Journal, routine refresh, full-universe coverage, group
membership, earnings completeness and broader calibration remain outside scope.

## Repository and data safety

- GitHub is the code source of truth.
- Work on feature branches and use draft pull requests.
- Do not merge without explicit authorization.
- Preserve `.vscode/settings.json` and unrelated user changes.
- Never commit credentials, provider exports, databases, Parquet data, snapshots,
  receipts, backups, or machine-specific paths.
- Historical V1 code, outputs, tests, and milestone evidence remain preserved.

## History

The complete cumulative project-state record through the first real bootstrap is
preserved at `docs/history/PROJECT_STATE-through-current-bootstrap-v1.md`.
Historical task receipts and implementation documents remain available under
`docs/`; consult them only when routed by a current task or when auditing provenance.

## Next work

Engine alignment is complete; no additional engine changes, refresh, production
switch, or merge is authorized merely by this status file. See
`docs/CODEX_NEXT_TASK.md` for the completed assignment and delivery boundary.
