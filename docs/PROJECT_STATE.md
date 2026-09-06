# Aperture — authoritative project state

Current milestone: AP-FOUNDATION-RECONCILE-001 complete; one original finding resolved by verified evidence and seven retained with bounded next actions. No real snapshot was built.
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


## AP-REGIME-001 completion record

Implemented on `codex/regime-engine-v1` from handoff commit `10c7e46`, targeting
`codex/leadership-engine-v1` for the draft PR. Recovered the interrupted draft
contracts and completed the pure opt-in `experimental_uncalibrated` layer.

Five independent sleeves retain index predicates, separate breadth denominators,
Leadership rotation participation and eligible sub-industry medians, spot VIX
context and exact 21-session equal-weight participation returns. The aggregate
exposes candidate, sleeve counts, historical memory, entry/counts, transition
reason, override branches and eligibility no earlier than the supplied T+1.
UNKNOWN observations emit no confirmed state and reset candidate continuity.
Opposite directional transitions pass through YELLOW; overrides use only valid
inputs required by their independently qualifying branch.

Frozen schemas, immutable thresholds, pure features and explicit bar/universe/
Structure/Leadership adapters reject ambiguous identity, duplicated observations,
mixed source bases, misaligned context and future-effective evidence. VIX remains
a versioned non-security spot series. Themes cannot affect internals, and
sub-industry security memberships cannot overlap. No crosswalk is applied.
[The implementation contract](regime-engine-implementation-v1.md) records formulas,
thresholds, missing-data behavior, initialization conventions and synthetic paths.

Versions: `market-regime-v1`, `market-regime-features-v1`,
`market-regime-thresholds-v1`. Rules fingerprint:
`3e13d0e057fbc80d806e8eab8fb3b9060b1c3f5de60bf45f8fb33ae15abec01a`.

Observed verification: **1,277 focused tests passed** (1,171 sleeves/candidates,
49 transitions, 57 adapters/contracts), followed by **2,335 complete-suite tests
passed**. Focused coverage includes all 64 index-vote combinations and 1,024
aggregate combinations. Every new test blocks socket/httpx network access; the
complete adapter/engine pipeline also runs with file-open APIs forbidden.
All **336** protected production/staging/settings files matched the saved
pre-disconnect SHA-256 inventory. `.vscode/settings.json` remains the preserved
uncommitted user change. Structure, Setup, Leadership, legacy code and immutable
configuration remain unchanged. Whitespace checks passed.

No AP-REGIME-001 implementation blocker remains. The unrelated September
security-master timestamp-precision publication issue is still deferred. No
provider request, ingestion, production publication, exposure rebuild, crosswalk
application, calibration, UI, actionability, sizing or PR merge occurred.

Milestone file inventory (13 files; no market data, reports or machine settings):

- `README.md`
- `docs/CODEX_NEXT_TASK.md`
- `docs/PROJECT_STATE.md`
- `docs/regime-engine-implementation-v1.md`
- `src/market_dashboard/aperture/regime.py`
- `src/market_dashboard/aperture/regime_adapters.py`
- `src/market_dashboard/aperture/regime_contracts.py`
- `src/market_dashboard/aperture/regime_policy.py`
- `src/market_dashboard/features/regime_features.py`
- `tests/regime_fixtures.py`
- `tests/test_regime_adapters.py`
- `tests/test_regime_sleeves.py`
- `tests/test_regime_transitions.py`


## AP-DECISION-RISK-001 completion record

Implemented on `codex/decision-risk-v1` from exact handoff commit
`370d5cdb79dde61854a89ace457f80edb5696a61`, targeting `codex/regime-engine-v1`
for the milestone draft PR. The layer remains `experimental_uncalibrated`.

Frozen inputs and evidence compose the unchanged Universe, Structure, Setup,
Leadership/Group and Market Regime contracts. Direction-aware extension preserves
the configured bands and inclusive 4.8-ATR cap. Earnings use explicit known event
records, exchange-session distances and complete fresh coverage through T+5;
missing coverage never makes an empty list CLEAR. Freshness is caller-attested
for T with timestamps no later than completed close, without an invented provider
TTL. Explicit cancellation/replacement and every known event remain auditable.

The complete ladder evaluates all gates before selecting the highest passing
rung. Strength branches remain separate, only sub-industry membership votes,
SHORT promotion stops at WATCH, and every setup retains its own qualification
and action evidence without a primary ranking. Regime alignment and exact T+1
eligibility are required; historical memory cannot replace UNKNOWN current data.

Sizing uses explicit entry/stop proposals, equity times .0025 as the risk base,
configured regime multipliers, exact whole-share floors, and separate capital
constraints. Both unconstrained/constrained full and pilot costs, dollar risk,
equity-risk percentages and unused risk are visible. Default-stop calculation is
a separate optional helper; setup invalidation never supplies a trade stop.
Invalid earnings/regime/input/zero-share cases cannot promote ACT. The pure daily
batch rejects duplicate symbol/direction keys and mixed evidence identities.

Engine/formula/threshold versions: `decision-risk-v1`,
`decision-risk-formulas-v1`, `decision-risk-thresholds-v1`.
Feature version: `decision-risk-features-v1`. Rules fingerprint:
`59109ef7baa8af98f6aea0cdea726060b7ce1dac7f647d43e342b027c61518a8`.
[The implementation contract](decision-risk-implementation-v1.md) documents all
formulas, schema identities, timing, missing-data behavior and synthetic examples.

Observed verification: **306 focused tests passed** (95 components, 45 events,
98 ladder, 68 adapters/contracts), followed by **2,641 complete-suite tests
passed**. Focused tests cover independent gates and 64 combined failure paths,
threshold equality, lifecycle status, monetary floors, point-in-time alignment,
future-event mutation and frozen JSON round trips. Every new test blocks
socket/httpx access; the full decision pipeline additionally runs with file-open
APIs forbidden and input objects unchanged. Whitespace checks passed.

All **336** protected production/staging/settings files matched their pre-work
SHA-256 inventory. `.vscode/settings.json` remains the preserved uncommitted user
change. Completed engine source/tests, immutable configuration, legacy extension
and legacy decision snapshots are unchanged. The full suite includes their
regression coverage. No provider request, market-data ingestion, production write,
exposure build, crosswalk application, empirical calibration or PR merge occurred.

No AP-DECISION-RISK-001 implementation blocker remains. Portfolio heat,
concentration, position management, exits, journal, API/UI, ingestion, publication
and brokerage behavior remain deferred. The unrelated September security-master
timestamp-precision publication blocker is unchanged.

Milestone file inventory (15 files; synthetic tests, source and documentation only):

- `README.md`
- `docs/CODEX_NEXT_TASK.md`
- `docs/PROJECT_STATE.md`
- `docs/decision-risk-implementation-v1.md`
- `src/market_dashboard/aperture/decision_adapters.py`
- `src/market_dashboard/aperture/decision_components.py`
- `src/market_dashboard/aperture/decision_contracts.py`
- `src/market_dashboard/aperture/decision_events.py`
- `src/market_dashboard/aperture/decision_policy.py`
- `src/market_dashboard/aperture/decision_risk.py`
- `tests/decision_fixtures.py`
- `tests/test_decision_adapters.py`
- `tests/test_decision_components.py`
- `tests/test_decision_events.py`
- `tests/test_decision_ladder.py`

## AP-WORKSTATION-SLICE-001 completion record — 2026-09-06

Recovered the interrupted workstation implementation on
`codex/workstation-slice-v1`, based on exact handoff
`3b46db79f7ad9530606b98632af18bbe0ddc16bb`. The milestone draft PR targets
`codex/decision-risk-v1`; no merge is included.

Added frozen `workstation-snapshot-v1` and `workstation-api-v1` contracts,
canonical evidence projections, deterministic synthetic GREEN/YELLOW/RED
scenarios, and explicit fail-closed standalone local JSON loading. API routes
cover health, Brief, Tape, exact-case symbol detail, canonical what-if sizing
and current rules. Local errors are sanitized; CORS and process commands use
loopback defaults. No production materializer is implemented.

The primary React interface includes the five regime sleeves, transparent funnel,
group context and ACT queue; sortable/filterable Tape; every setup and gate in a
responsive detail dialog; manual copy-symbol Deepvue handoff; complete canonical
sizing amounts/refusals; and API-sourced rule metadata. Missing values stay
unknown. Synthetic identity stays visible. Portfolio heat is explicitly
unavailable. Only UI preferences persist in session storage.

[Development commands, schemas and scope](workstation-slice-v1.md) are documented.
[Desktop Brief](workstation-evidence/brief-1366.png),
[mobile Brief](workstation-evidence/brief-390.png), and Tape/detail/Sizer captures
in the same directory were produced by real Chromium tests against the local
fixture API. The browser tests found and verified a fix for dialog focus return
under React StrictMode.

Observed verification: **58 focused Python tests passed**, followed by
**2,699 full-suite tests passed**. **11 frontend component tests** and **two
desktop/mobile browser tests** passed. Generated OpenAPI determinism, frontend
type synchronization, TypeScript, production build, Python/frontend lint/format
and whitespace checks passed. One upstream Starlette httpx TestClient
deprecation warning remains nonblocking. Initial sandbox TestClient execution
stalled; the complete observed passing runs used local execution outside that
sandbox, without provider access.

Completed engine source, feature source and immutable configuration have no diff
from the handoff. The pre-existing `.vscode/settings.json` change is preserved
and excluded from the milestone commit. No data ingestion, database/staged
publication, exposure rebuild, crosswalk application, calibration, broker
interaction or PR merge occurred. No workstation blocker remains; real
materialization, portfolio workflows and the unrelated September security-master
timestamp-precision publication correction remain separate future work.

## AP-WORKSTATION-SNAPSHOT-002 completion record — 2026-09-06

Implemented on `codex/workstation-snapshot-v2` from exact handoff
`8a128abebb1e10c19be316cc6e50985cb925e133`, targeting
`codex/workstation-slice-v1` for the milestone draft PR.

The prior 12-row snapshot repeated full Leadership/Regime populations per record.
`workstation-snapshot-v2` stores a typed content-addressed evidence table once,
with deterministic integer references bound to full SHA-256 IDs. A frozen
registry/catalog binds all canonical field types and column order. Complete
Structure, Setup, raw/ranked strength, memberships, groups, extension, earnings,
regime gates, decision ladders and sizing evidence remain losslessly resolvable.
Exact-source equality, duplicate/dangling/wrong-type references, contradictory
shared copies, cross-direction consistency and point-in-time alignment are tested.

The pure materializer accepts streamed canonical engine outputs and explicit
shared context. SnapshotStore accepts V2 only; V1 keeps its historical meaning
and is retained only for explicit parity tests. Sizer uses exact key context and
canonical `size_idea`, returning typed refusal for an absent direction. Existing
OpenAPI/TypeScript transport schemas, frontend design and engine/configuration
files are unchanged. Synthetic UI fixtures and desktop/mobile screenshots were
regenerated from V2; mobile Tape scrolling is explicitly verified.

Observed verification: **93 focused Python tests**, **2,734 full-suite tests**,
**11 frontend component tests**, and **two Chromium desktop/mobile tests passed**.
Typecheck, production build, OpenAPI/type synchronization, snapshot-schema/catalog
determinism, Python/frontend lint/format and whitespace checks passed. One existing
Starlette httpx TestClient deprecation warning remains nonblocking.

Measured GREEN fixture: **480,251 bytes**, **94.51% smaller** than the supplied
8,739,961-byte V1 baseline. Measured scale: **2,000 records**, **18,834,442 compact
uncompressed bytes (17.96 MiB)**, **9,417.221 bytes/record**, below the hard 24 MiB
ceiling and unchanged 32 MiB loader bound. Final diagnostic build/load/rebuild
times: **86.41 / 13.18 / 24.68 seconds**. Timing is diagnostic, not a hard test.
Reordered inputs rebuilt byte-identically; first/middle/last detail and Sizer
contexts matched independent canonical engine evaluations. The scale funnel is
1,226 NONE / 5 WATCH / 268 TRADE / 501 ACT.

Scale fingerprint:
`866c148e05a11d5553fcc9d5a7571c83018cce0f0e8c11f4dc0e085bac712e40`.

[Schema, migration, exact commands and measured evidence](workstation-snapshot-v2.md)
are documented with a generated standalone JSON Schema/column catalog. Generated
scale files stay in temporary test storage. The pre-existing
`.vscode/settings.json` change is preserved and excluded from the commit. No
provider/event retrieval, real data materialization, database/staged publication,
exposure rebuild, crosswalk, portfolio workflow, UI redesign, hosting, brokerage
or PR merge occurred. No snapshot-correction blocker remains. The separate
September security-master timestamp-precision publication issue is unchanged.


## AP-LOCAL-MATERIALIZER-001 completion record — 2026-09-06

Implemented on `codex/local-materializer-v1` from exact handoff
`866b15a09773c56dcbf72530bf077b9def9355e9`, with draft PR base
`codex/workstation-snapshot-v2`.

The explicit offline CLI now provides plan, audit, build and validate. Frozen
plans/readiness and source attestations bind exact paths, versions, hashes,
publication state, identity intervals, adjustment basis and exchange calendar.
Native DuckDB reads are read-only with external access disabled; explicitly
selected Parquet copies are compared in full. Missing optional groups/events/
proposals/QA remain canonical UNKNOWN or refused evidence. Real source repair,
publication and provider access are separate boundaries.

Replay uses existing pure Structure/Setup, Leadership, Regime and Decision/Risk
engines. Histories are processed per symbol, group history is bounded, and final
records stream into normalized V2. Historical membership revisions are retained;
departed members' history is verified through their last effective member session.
The existing shared-calendar/per-symbol-index incompatibility is an explicit
blocker rather than filled data or an engine semantic change. Build rechecks the
successful audit and source hashes, validates temporary output, then uses an
atomic no-replace rename. Standalone validation checks full V2, receipt/field
hashes and canonical decision parity. The prescribed standalone workstation
staging layout is narrowly accepted by the existing live loader.

Observed verification: **46 materializer focused tests** and **93 workstation
focused tests passed**, followed by **2,780 full-suite tests passed**. **11 frontend
component tests** and **two desktop/mobile browser tests passed**. Typecheck,
production build, OpenAPI/snapshot-schema/type synchronization, Python/frontend
lint/format and whitespace checks passed. The existing Starlette TestClient
httpx deprecation warning remains nonblocking. The unchanged normalized scale
regression again retained 2,000 records in 18,834,442 bytes with the same logical
fingerprint. Existing engine/feature source, immutable configuration, API schemas
and frontend files have no diff from the handoff.

One actual plan and read-only audit returned **8 HARD_BLOCKER findings** and five
optional gaps. Adjusted bars: 63,279 rows, 100 explicit Parquet copies, 2024-01-02
through 2026-07-24, zero duplicate keys/required OHLCV nulls, but exact copies
disagree. July master and exposure each have 13,023 rows and agreeing copies;
exposure-policy-v3 publication is complete and verified. The legacy universe
slice has 13,023 diagnostic rows, disagrees across stores and is not a published
Aperture research/trade schedule. Calendar, provenance and spot paths are missing;
the July 26 master follows candidate T=July 24, and one mandatory benchmark is
missing. No real build or real-data API startup was attempted.

All **337 protected files / 112,487,134 bytes** retained SHA256s, including
production datasets, September provider staging, environment file and user VS Code
settings. Git status/diff were unchanged across the audit. Reports and preservation
proof remain private in the authorized audit workspace. No provider request,
source mutation/publication, exposure/universe rebuild, crosswalk, broker action,
UI redesign or PR merge occurred.

[Complete source contract, commands, limitations, report fingerprints and the
next bounded offline foundation reconciliation](local-materializer-v1.md) are
recorded. The September timestamp-precision publication issue remains deferred;
no unpublished source was consumed or repaired.


## AP-FOUNDATION-RECONCILE-001 completion record — 2026-09-06

Implemented on `codex/foundation-reconciliation-v1` from remote handoff
`c6746c16e91bdcf0b4ef0792f865d00078322aba`, verified to descend from product
baseline `c5e696ddeb0be2a2fb8befa91ad2adc292ee49e9`. Draft PR base is
`codex/local-materializer-v1`; no merge is included.

The new offline reconciliation command has zero-I/O planning, exact original
audit/plan/source binding, read-only DuckDB and explicit Parquet comparisons,
conserved finding identities, staged candidate/UNKNOWN evidence, no-clobber
outputs and independent offline validation by recomputation. Versioned DATE
equivalence is confined to reconciliation; original materializer fingerprints,
engine contracts and historical audit receipts are unchanged. Exact numeric
comparison also avoids integer-to-float precision loss above `2**53`.

The actual 100-copy bar comparison found the same 63,279 keys and only 11,607
volume differences, consistent with the writer's BIGINT coercion. No canonical
volume source was inferred. Legacy-universe copies agree across all 13,023 keys
and fields under lossless DATE equivalence: that original finding is resolved.
Seven original findings remain: volume authority, calendar, provenance, spot,
Aperture schedule publication, identity/time alignment and missing QQQE.
The original eight are never combined or replaced. A separate rules-effective-
date finding records August 25 rules versus candidate T=July 24.

July master/exposure copies agree; native exposure-policy-v3 publication count
and fingerprint verify. All bar sessions precede the selected July 26 identities,
so there are zero feasible T/T+1 pairs. Dated market cap and other population
prerequisites are absent; no candidate research/trade schedule was fabricated.
SPY, QQQ, IWM and RSP each have 642 observed rows; QQQE is absent in both stores.
No authoritative calendar implementation/artifact or spot identity/source is
available locally. Calendar gaps, exact warmup and research denominator stay
UNKNOWN. The 100-record ingestion receipt and configuration hints cannot attest
dividend treatment, matching volume basis or complete source publication.

The private plan and independent validation succeeded with network calls blocked.
Evidence fingerprint:
`15e72badc9e2456a861a11b3bf4ba4d21fe05a1aa2a17cc2ced43586cfe5cd00`.
All 344 protected files retained their pre-work hashes, with no added/removed
production or provider-staging files. User VS Code settings remain uncommitted.
The [complete reconciliation contract](foundation-reconciliation-v1.md) records
the exact ledger, source distinctions, command forms, private receipt fingerprints
and conditional acquisition caps.

Observed verification: **76 focused Python tests passed**, including 30 new
reconciliation tests, followed by **2,810 full-suite tests passed**. Frontend components (11),
desktop/mobile fixture browsers (2), API/schema/type synchronization, TypeScript,
build, lint/format and whitespace checks passed. The existing Starlette TestClient
httpx deprecation warning remains nonblocking. Sandbox TestClient/loopback limits
required local execution for the passing integration/browser runs.

Next bounded action: offline operator review of the staged volume/provenance
matrix and selection of a pinned XNYS calendar implementation. Unsupported source
semantics stay UNKNOWN. Dependency/source acquisition, any recoverable data
correction, identity/population input acquisition, schedule publication and market
history fetch require separately bounded authority. No real snapshot build,
production API startup, provider request, source mutation/publication, exposure
rebuild, crosswalk application or PR merge occurred. The September master
publication issue remains deferred.
