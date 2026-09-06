# Aperture — authoritative project state

Current milestone: AP-LEADERSHIP-001 complete; pure Strength/Leadership and Group Ranking V1 with independent one-week/one-month rotation, alongside preserved Structure and Setup engines.
Read `CODEX_NEXT_TASK.md` immediately after this file for the current assignment.

## Read first

Read `AGENTS.md`, this file, and both canonical engine specifications before
engine work. Current instructions and explicit amendments supersede older
session summaries. Historical checkpoints remain evidence of prior work.

- [Structure contract](structure-state-engine-v1.md)
- [Setup contract](setup-classification-engine-v1.md)
- [Blocking specification decisions](engine-spec-open-issues.md)
- [Approved V1 engine decisions](engine-spec-decisions-v1.md)
- [Foundation and taxonomy audit](data-foundation-gap-report.md)
- [Deepvue audit status](deepvue_audit.md)

The engine specifications are complete recovered documents. The explicit owner
authorization and exact resolutions in `engine-spec-decisions-v1.md` make them
implementation-ready. Codex must use that decision overlay rather than infer
from conflicting recovered prose.

## Verified repository baseline

- Repository: `mmoore114/market-dashboard`.
- Foundation branch: `codex/aperture-foundation`.
- Inspected baseline: `d1192f66ecd9c5bd7142264db7d44096cf8be29b`.
- User confirmed laptop HEAD and origin match that commit.
- User's only reported local change is `.vscode/settings.json`; preserve it.
- Current code is Python under `src/market_dashboard/`, with `config`, `scripts`,
  `tests`, and a Streamlit diagnostic placeholder. No React/FastAPI monorepo is
  implemented. React/TypeScript plus a typed Python API remains the proposed
  interface direction; do not mechanically relocate the repository.

## Previously completed, as recorded in the August checkpoint

- Exposure-policy-v3 publication: 13,023 securities; v2 preserved.
- Corrected research/backfill universe: 1,787 instruments (1,424 common stocks,
  363 diversified ETFs); distinct from stricter equity-trade membership.
- Adjusted history: 63,279 rows, 100 tickers, 2024-01-02 through 2026-07-24.
- Original ranks 1–50 preserved; authorized v3 ranks 51–100 completed.
- Milestone 1 and hardening completed; checkpoint reports 314 passing tests.
- Milestone 2 was not started.

These are recorded validation results, not a fresh inspection of the laptop's
databases. No new ingestion or data-validation run occurred in this documentation
milestone. Dates are historical coverage, not a claim of current market freshness.

## Confirmed product decisions

- Preserve the vocabulary Market Context, Structure Engine, Setup Engine,
  Evidence Object, Decision Queue and Time Machine.
- Deterministic research and decision support remain separate from probabilistic
  AI. No brokerage execution.
- Structure: NEUTRAL, EMERGING, UPTREND, DETERIORATING, DECLINE. BASE is obsolete
  as a state name; this is not a linear-only transition graph.
- Setup: EP, CONTRACTION, TREND_PULLBACK, RANGE. Multiple objects are allowed;
  RECLAIM is evidence, with no primary/secondary setup ranking.
- Lifecycle includes RESOLVED; STALE is pre-trigger only. EP resolves after five
  following sessions without failure. Trigger references are committed by T-1.
- Keep structure, setup, leadership, extension, regime, actionability, sizing
  and portfolio context separate. Setup invalidation is not a trade stop.
- Existing configured thresholds remain versioned hypotheses. Do not replace
  them with remembered values from conversations.
- Massive is the market-data/security foundation. Aperture should own its dated
  classification and theme membership records, with Deepvue as a bootstrap and
  chart-review reference, not a required runtime dependency. Sub-industry CSV
  transfer and dated theme membership capture are verified; parent hierarchy
  remains unverified.

## Current milestone additions

- Completed authenticated Deepvue all-stock export inspection: 11,370 unique
  symbols, 5,462 meaningful Sub-Industry classifications, 164 labels, and two
  internally ambiguous group ranks.
- Added a dry-run-by-default Deepvue taxonomy normalizer and dated DuckDB/Parquet
  publisher. Raw proprietary exports remain local and uncommitted.
- Verified all 31 Theme Tracker lists as a dated many-to-many snapshot: 30
  populated themes plus Bitcoin with zero displayed stocks. Added a dry-run by
  default theme normalizer and dated DuckDB/Parquet publisher; raw captures stay
  local and uncommitted.
- Closed S1-S6 and U1-U8 with exact formulas, timing, precedence, missing-data,
  identity, and lifecycle rules in `engine-spec-decisions-v1.md`.

## Prior documentation milestone

- Preserved both full source specifications verbatim in `docs/reference/`.
- Added canonical copies with NEUTRAL, RESOLVED and trigger-timing amendments.
- Registered mathematical, lifecycle, feature and migration blockers.
- Added a repository-grounded foundation report and Deepvue audit status.
- Added reading precedence to AGENTS and notices on older design documents.
- No engine code, immutable config, market data or machine settings changed.

Documentation validation: archived source files were compared byte-for-byte to
the recovered originals. The authored/canonical diff passes whitespace checks.
The unmodified archives retain Markdown two-space hard breaks, which standard
`git diff --check` reports as trailing whitespace; this is an intentional source
preservation exception. Python tests were not rerun for this documentation-only
change; the 314 result above remains the recorded baseline.

## Next work

The historical sequence below is superseded by `CODEX_NEXT_TASK.md` and the
engine completion records at the end of this file. Production publication and
subsequent product layers require their own next assignments.

1. Perform read-only local data inventory/validation through laptop Codex using
   the existing scripts. Confirm actual files, dates, adjustment policy and
   shared feature definitions before any new data build.
2. Pull the feature branch on the laptop, export the current all-stock Deepvue
   CSV locally, run the taxonomy importer in dry-run mode, reconcile coverage to
   the local Massive security-master snapshot, then explicitly publish.
3. Reconcile the verified Deepvue theme snapshot to the local Massive security
   master, review unmatched symbols, then explicitly publish the dated snapshot.
4. Implement the approved shared features and engine contracts on a feature
   branch with boundary, state-path and no-look-ahead tests, preserving legacy
   outputs and version identities.

Real ingestion still requires a bounded dry run and separate explicit approval.
Use a pull request. Do not merge into main as part of this documentation task.

## Laptop taxonomy validation correction — 2026-09-05

Fixed missing-value handling in the taxonomy importer for Python/pandas null
representations. Missing sub-industry values remain unclassified and null in
storage; only the fingerprint payload uses the canonical empty string. Existing
classification rules, ranks, schemas and source records are unchanged.

Validation: 16 focused taxonomy tests and all 333 full-suite tests passed.
The local taxonomy dry run succeeded for 11,370 unique symbols: 5,462 classified,
5,908 unclassified, 164 groups, 5,465 ranked symbols, 162 consistent group ranks
and two ambiguous group ranks. Every fingerprint was deterministic, non-null and
64 hexadecimal characters; all classifications and ranks matched the prior audit.
The theme dry run also passed (31 themes, 1,794 memberships, 1,323 tickers).

Reconciliation against the dated 2026-07-26 Massive master remains unchanged:
11,085 taxonomy tickers matched and all 285 unmatched records were preserved for
review. Themes matched 1,792 memberships across 1,321 tickers; STLN and VMRK remain
unmatched. Neither reconciliation has ambiguous master ticker keys. The snapshot
date gap remains relevant; no aliases or identity explanations were inferred.

All 294 inventoried data files remained unchanged. Publication, ingestion,
engine implementation and PR merging remain paused. The previously reported
adjusted-volume DuckDB/Parquet discrepancy and partial feature snapshot remain
open; this correction does not resolve those separate inventory findings.

## Local reference-error diagnostic correction

The bounded reconciliation lookup was a temporary script, separate from the
tracked paginated reference client. Its HTTP-error branches discarded provider
response bodies. A reusable pure reference-error capture helper and mocked tests
now cover bounded JSON/plain-text diagnostics, malformed/oversized bodies, secret
and query redaction, and unchanged successful responses. The temporary lookup
uses the helper; no real lookup or retry was run for this correction.

Diagnostics preserve the requested ticker, HTTP status, optional provider error
code, sanitized message, endpoint path and UTC capture time. Messages are capped
at 1,024 characters and codes at 128; bodies above 65,536 bytes receive a safe
summary. Raw bodies, headers, credentials and query strings are not stored.
Previously discarded provider error messages remain unavailable until a separately
authorized diagnostic retry. No URL-encoding defect has been established.

NXH to BBBY remains flagged for its exchange difference and SEPQ to TUGN for its
CIK mismatch. The other 21 dual-FIGI matches remain proposals only. No master,
crosswalk, snapshot or historical classification was changed. Network retries,
publication, engine implementation and Git publication remain paused.

Verification: 13 focused mocked tests passed; full suite 346 passed. Repository
whitespace checks passed. Data, source CSV and machine-settings fingerprints
remained unchanged; no commit or push was performed.

## Staged security-master refresh implementation — 2026-09-05

Implemented the locally approved four-mode workflow described in
[security-master-refresh.md](security-master-refresh.md). `plan` stages a bounded
scope and immutable local inputs offline. `fetch` is the sole network boundary,
with fixed reference-only scope, request/page budgets, no retries/redirects,
first-page schema checks and preserved completed-page evidence. `validate` is
offline and binds page, input, report and candidate hashes to a validation receipt.
`publish` is offline, explicitly confirmed, independent of exposure publication
and recoverable through pending/complete/recovery_required states. The existing
immediate-publication ingestion CLI is unchanged.

Publication protects July 26's exact logical content and original Parquet bytes,
checks every DuckDB/Parquet field, makes identical same-date content a no-op and
requires the old logical fingerprint for an explicitly authorized revision.
Existing readers do not enforce the new publication state: use a maintenance
window through completion/recovery. This remains an operational approval condition.

The exact versioned Deepvue disposition preserves all 29 observed non-security
records in source snapshots while excluding them from security matching and
coverage denominators. Local-only verification reproduced 11,370 total rows,
29 non-security records, 11,341 security candidates, 5,462 classified security
candidates and 5,879 unclassified security candidates. No broad symbol rules or
source-normalization changes were introduced.

All 23 crosswalk entries remain unapplied proposals. NXH to BBBY is quarantined
for exchange review; SEPQ to TUGN is quarantined for CIK review. TUNG is not a
mapping candidate. STLN to TOI and VMRK to EQR remain proposals. The 231 previously
identified supported current/new securities will be assessed against the actual
new dated response by exact ticker, without appending prior lookup evidence or
applying historical aliases. FIGI collisions, unknown codes and all unmatched
records remain explicit review outputs.

Observed validation: 58 focused tests passed, followed by all 391 tests. Tests
explicitly prohibited HTTP/socket calls in plan, validation, publication and
publication recovery and observed zero network calls. Fetch behavior was tested
only with mocked responses. The offline local plan succeeded with ceilings of
20 requests and 20,000 records; July's 13,023 records imply an estimate of 14
pages. Offline validation of that unfetched plan correctly exited 2 because fetch
evidence does not exist. No real fetch was performed. All 294 inventoried data
files and machine settings remained unchanged. Whitespace checks passed.

Next approval checkpoint: review the bounded plan and approve reference fetch
only. Inspect complete validation/reconciliation outputs before separately
approving publication. No production publication, crosswalk application,
ingestion, exposure/universe rebuilding, engine work, commit, push or PR merge
was performed for this implementation.

## Exact-case provider identity correction — 2026-09-05

The approved 14-request bulk fetch returned 13,155 exact tickers. Its first
validation rejected 404 mixed-case provider symbols. This local correction reuses
that immutable fetch; no additional provider request was made.

The master builder now preserves ticker strings exactly and rejects every exact
snapshot/ticker duplicate. Case-insensitive collisions are explicit diagnostics,
never keys or automatic mappings. The 404 mixed-case rows retain their actual
types: 354 PFD, 30 SP and 20 RIGHT. TPC/TpC and BCPC/BCpC coexist as distinct rows.
See [the complete compatibility audit](security-master-case-audit.md).

Offline revalidation succeeded for all 13,155 rows with zero exact duplicates.
Logical fingerprint: `7d22fab5f8dbffea1c9254124e9c2731006648391519e55543f6058c77c7112b`.
Deepvue security reconciliation remains 11,325 exact matches and 16 unmatched;
29 source-native non-security records are preserved and excluded. All 23 mapping
proposals remain unapplied, including NXH/BBBY and SEPQ/TUGN quarantines.

Validation success does not authorize publication. Both public master publication
paths block mixed-case snapshots until compatibility is established for exposure
registries/classification, daily/flat bars, feature keys, universe models and
legacy Deepvue importers/diagnostics. The legacy ingestion CLI itself is unchanged;
its shared store now blocks before writing an incompatible snapshot. No reader
semantics or immutable exposure policy results were changed.

Verification: 80 focused tests and all 397 full-suite tests passed. HTTP/socket
calls were blocked during the actual offline revalidation and observed zero calls.
All 30 previously hashed staging artifacts remained unchanged. All 294 production
files, July's exact logical content and Parquet bytes, and machine settings were
preserved. Whitespace checks passed. No publication, mapping application,
ingestion, engine work, commit, push or PR merge occurred.

## Reference/market-data compatibility boundary — 2026-09-05

Implemented `reference-to-market-data-v1` with distinct immutable ReferenceTicker
and MarketDataSymbol types and explicit snapshot-scoped conversion. The reference
master is unchanged. Mixed-case references receive no automatic market-data
symbol; every member of a case-insensitive collision group is excluded from the
consumer projection. Exclusion is not an invalid-reference classification.

See [the identity-boundary contract and complete reader migration map](security-identity-boundary.md).
Exposure classification now projects complete reference inputs before applying
uppercase-domain policies. Swing-universe and exposure-validation joins use a
connection-local projected master. Deepvue importers preserve source symbol case;
reference reconciliation remains exact, with versioned non-security dispositions
and separate unapplied crosswalks. Existing bar/feature/trading uppercase-domain
normalization and invariants remain unchanged.

Legacy master ingestion no longer automatically publishes exposure classifications.
Both master publication paths consult the unsafe-reader registry and block
ambiguous conversion. No identified unsafe reference readers remain in the
audited repository paths; the current snapshot remains blocked by TPC/TpC and
BCPC/BCpC ambiguity. No operator confirmation or revision flag bypasses this gate.

Offline revalidation: all 13,155 reference rows preserved; 12,749 compatible
projection rows; 406 projection exclusions. Exclusions are 402 mixed-case-only
rows (353 PFD, 29 SP, 20 RIGHT) and four ambiguous rows (2 CS, 1 PFD, 1 SP).
Reference types remain 354 mixed-case PFD, 30 mixed-case SP and 20 mixed-case RIGHT.
Deepvue remains 11,325 exact matches, 16 unmatched security candidates and 29
excluded non-security source records. All crosswalks remain unapplied.

Reference logical fingerprint unchanged:
`7d22fab5f8dbffea1c9254124e9c2731006648391519e55543f6058c77c7112b`.
Reference Parquet SHA-256 unchanged:
`d3bd5b75665c646e109e22514839da6771b49070f4ed2998b5e879cdb16fc8fc`.

Validation: 195 focused tests and all 405 full-suite tests passed. The actual
revalidation blocked HTTP/socket calls and observed zero calls. Original raw
staging pages/provenance and copied inputs, July's exact logical content and
Parquet bytes, all 294 production files, and machine settings remained unchanged.
Whitespace checks passed. No network, publication, crosswalk application,
ingestion, engine work, commit, push or merge occurred in this milestone.

## Exact-case precedence refinement — 2026-09-05

Compatibility policy `reference-to-market-data-v2-exact-precedence` supersedes the
v1 collision exclusion rule. An exact uppercase ReferenceTicker converts to its
own MarketDataSymbol even if a mixed-case neighbor exists. TPC and BCPC therefore
convert exactly; TpC and BCpC remain reference-only. Both collision groups remain
reported. No reference row, key or stored identifier is rewritten.

Reverse resolution checks exact identity first, including exact mixed-case
reference requests. Every non-exact request returns AMBIGUOUS_NO_EXACT_IDENTITY
and no reference; casefold candidates are diagnostic only, even when only one
candidate exists. No crosswalk or alias is applied.

Offline revalidation produced the expected 13,155 reference rows, 12,751
compatible symbols and 404 explicit mixed-case exclusions (354 PFD, 30 SP,
20 RIGHT). Ambiguous automatic conversions: zero. Retained case-insensitive
collision groups: two. No audited identity-compatibility publication blocker
remains. Production publication still requires separate approval and the existing
publication/recovery operational checks; compatibility is not authorization.

The exact reference logical fingerprint and Parquet SHA-256 remain unchanged:
`7d22fab5f8dbffea1c9254124e9c2731006648391519e55543f6058c77c7112b`
and `d3bd5b75665c646e109e22514839da6771b49070f4ed2998b5e879cdb16fc8fc`.
Original staged pages, fetch provenance and copied inputs remain unchanged.
July's logical content and Parquet bytes, all 294 production files, and machine
settings were verified unchanged. Actual revalidation blocked HTTP/socket calls
and observed zero calls. Deepvue remains 11,325 exact security matches, 16
unmatched candidates and 29 excluded non-security records; all crosswalks remain
unapplied proposals.

Legacy master ingestion remains decoupled from exposure publication and now
explicitly prints `exposure publication: not performed (disabled; separate
workflow required)`. Master CLI success no longer implies exposure freshness;
existing automations must use a separately authorized exposure workflow. The
CLI regression test verifies no exposure-store publication call.

Verification for the final refinement: 198 focused tests and all 408 complete-suite
tests passed; tracked and untracked whitespace checks passed. The accumulated
implementation is ready for a single reviewed source/configuration/documentation/
test commit, excluding machine settings and all staged data/reports. No network,
publication, exposure publication, crosswalk application, ingestion, engine work,
commit, push or merge occurred.

## AP-STRUCTURE-001 — complete

Implemented the approved Structure Engine V1 on `codex/structure-engine-v1`,
branching from the pulled handoff task commit `b846d2a`. The pure calculation API
has five exact states, frozen thresholds and transition rules, explicit versioned
input/evidence schemas, full reason/measurement output and a bar adapter requiring
250 prior sessions. The decision overlay governs initialization, persistence,
strict equality counts, BROKEN_UP and every shock path.

The adapter consumes uppercase market-data symbols without normalizing reference
identities; reference access uses explicit compatibility conversion. It preserves
the existing EMA9/simple ATR and all legacy state histories. No setup families,
regime, leadership, actionability, risk, sizing or opportunity scores were added.
See [implementation formulas, transitions and synthetic examples](structure-engine-implementation-v1.md).

Observed verification: 176 focused tests passed, including all 149 new structure
tests and 27 existing feature/identity regression tests. The complete suite
passed 557 tests. Whitespace checks passed. Network calls are forbidden by the
bar-adapter acceptance fixtures; no provider client or production builder ran.
Protected production/staging files and `.vscode/settings.json` matched their
pre-work SHA-256 inventories. Only source, tests and documentation are included
in the milestone commit; no market data, credentials or generated reports.

The September security-master publication issue is explicitly **deferred**:
Parquet retains nanosecond `last_updated_utc` values while DuckDB TIMESTAMP loses
precision in 13,146 rows. Staged validation does not authorize publication.
No security-master publication, exposure build or crosswalk application occurred;
all 23 mapping proposals remain unapplied. No snapshot, raw data, or July
partition was changed. No merge occurred. Setup implementation and empirical
universe-wide structure calibration remain separate future work.


## AP-SETUP-001 completion record

Implemented on `codex/setup-engine-v1` from handoff commit `68b0b93`.
Engine/feature/threshold identities are `setup-engine-v1`, `setup-features-v1`
and `setup-thresholds-v1`. Frozen input, instance, evidence and output contracts
cover EP, CONTRACTION, TREND_PULLBACK and RANGE in both directions. The pure
adapter consumes unchanged Structure Engine evidence and the exact reference to
market-data compatibility boundary.

Implemented stable identity, committed T-1 geometry, failure-first lifecycle
processing, independent observation clocks, geometry/reference replacement,
terminal retention, rejected EP diagnostics and corporate-action quarantine.
The owner clarified that an unobservable failure session requires corrected-data
replay rather than a later inferred resolution; that clarification is recorded
in the authoritative decisions file.

Representative paths: EP TRIGGERED at age zero resolves after five following
sessions, with day-five failure taking precedence. Contraction and range may
coexist at the same pivot, trigger independently and resolve after eight following
sessions. Two consecutive contraction predicate losses stale the untriggered
instance. A deeper MA replaces an untriggered pullback with a new ID; terminal
instances remain non-reactivatable. Detailed formulas and evidence are in
[the implementation contract](setup-engine-implementation-v1.md).

Final verification: **485 focused tests passed** (336 setup tests and all 149
Structure Engine tests), followed by **893 complete-suite tests passed**.
`git diff --check` passed. Every setup test blocks socket/httpx requests. All
336 protected production/staging/settings files matched their pre-work SHA-256
inventory. Structure Engine source/tests and legacy source/output contracts were
unchanged. No proprietary data, reports, credentials or machine settings are
included in the commit.

No unresolved AP-SETUP-001 decision remains. The separate security-master
nanosecond/microsecond publication blocker remains deferred. No provider request,
production data write, exposure build, crosswalk application or PR merge occurred.
Production materialization and empirical setup calibration remain separately scoped.

Exact milestone file inventory:

- `README.md`
- `docs/CODEX_NEXT_TASK.md`
- `docs/PROJECT_STATE.md`
- `docs/engine-spec-decisions-v1.md`
- `docs/setup-engine-implementation-v1.md`
- `src/market_dashboard/aperture/setup.py`
- `src/market_dashboard/aperture/setup_contracts.py`
- `src/market_dashboard/aperture/setup_detection.py`
- `src/market_dashboard/features/setup_features.py`
- `tests/setup_fixtures.py`
- `tests/test_setup_detection.py`
- `tests/test_setup_features.py`
- `tests/test_setup_lifecycle.py`


## AP-LEADERSHIP-001 completion record

Implemented on `codex/leadership-engine-v1` from exact handoff commit
`28be4e88acc49610e04749f9487c1dbdc6bf3e40`, with draft PR base
`codex/setup-engine-v1`. The new opt-in layer is explicitly experimental and
uncalibrated. It preserves legacy Leadership Score and 20/60/120 SPY features.

Individual evidence contains fractional 5/21/63/126/252-session returns and
independent average-rank percentiles, the .50/.30/.20 slow composite, the .40/.60
5/21-session rotation pulse and its delta, sample-covariance QQQ beta/residual
strength, closing-high distances and optional Structure/Setup/legacy context.
Every denominator and dated research-universe identity remains visible. Missing
components never cause weight renormalization or a substitute universe.

Explicit effective snapshots support SUB_INDUSTRY, many-to-many THEME, and
separately supplied SECTOR/INDUSTRY membership. Group metrics preserve missing
coverage, valid context denominators and distinct triggered-member counts.
Independent median-based leadership and rotation ranks enforce five-valid-member
and 60%-coverage gates. Both have five-/twenty-session changes and top-quintile
streaks, with no forward fill across missing exchange-session outputs.

The pure adapters use the existing exact reference-identity boundary and the
versioned 29-record non-security disposition. Mixed-case identities remain
preserved without automatic conversion. Crosswalk proposals are never read as
mappings or applied. No current taxonomy is projected backwards in time.
The caller supplies the calendar, dated universe, complete boundary and source
metadata; the pure layer performs no data loading or production materialization.

Formula version: `leadership-formulas-v1`; threshold version:
`leadership-thresholds-v1`. Rules fingerprint:
`30178a5ec7822b97a2341f74b5965f1db3997c72a181f02eb421ded492923485`.
[The implementation contract](leadership-engine-implementation-v1.md) documents
schemas, exact formulas, examples, adapter responsibilities and missing-data rules.

Final verification: **165 focused tests passed** (49 features, 32 ranking,
36 groups, 48 adapters), then **1,058 complete-suite tests passed**.
`git diff --check` passed. All new tests prohibit socket/httpx access; the complete
pure pipeline additionally runs with file-open APIs forbidden. All **336**
protected production/staging/settings files matched their pre-work SHA-256
inventory, with no added protected files. `.vscode/settings.json` remains the
same uncommitted user change. Legacy rankings and all Structure/Setup engine
source/tests remain unchanged; the full suite includes their regression tests.

No AP-LEADERSHIP-001 blocker remains. The unrelated September security-master
nanosecond/microsecond publication blocker remains deferred. No provider request,
ingestion, exposure build, publication, crosswalk application, empirical
calibration, trading-policy implementation or PR merge occurred. Production
integration and empirical calibration require separate work and approval.

Exact milestone file inventory (13 files; no data, reports or machine settings):

- `README.md`
- `docs/CODEX_NEXT_TASK.md`
- `docs/PROJECT_STATE.md`
- `docs/leadership-engine-implementation-v1.md`
- `src/market_dashboard/aperture/leadership.py`
- `src/market_dashboard/aperture/leadership_adapters.py`
- `src/market_dashboard/aperture/leadership_contracts.py`
- `src/market_dashboard/features/leadership_features.py`
- `tests/leadership_fixtures.py`
- `tests/test_leadership_adapters.py`
- `tests/test_leadership_features.py`
- `tests/test_leadership_groups.py`
- `tests/test_leadership_ranking.py`
