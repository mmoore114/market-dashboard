# Aperture Current Authority

Status: **CURRENT PRODUCT AUTHORITY**

Effective: 2026-09-08

Scope: product identity, terminology, architecture, target Structure/Setup design,
document precedence, and legacy boundaries

This file is the shortest authoritative statement of what Aperture is now. It
distinguishes settled product decisions from the currently implemented V1 engine
so an agent cannot mistake a target change for completed code.

## 1. Product definition

Aperture is a transparent, deterministic market-research and trading-decision
workstation for discretionary U.S. equity swing and momentum trading. Its workflow
is:

`Market Context -> Groups -> Leadership -> Structure -> Setup -> Actionability -> Risk -> Portfolio Context`

It should help a human move from market conditions to a small explainable decision
queue. It does not select trades opaquely, place orders, or replace human judgment.

## 2. Interface and charting boundary

- React/TypeScript is the primary interface.
- FastAPI is the typed local service boundary.
- Python owns canonical computation, ingestion, validation, and materialization.
- DuckDB and Parquet remain the local research-data foundation.
- Streamlit may remain for internal diagnostics and administration.
- Deepvue is the chart-review, drawing, replay, and alerting companion.
- Aperture presents evidence, metrics, states, setups, levels, vetoes, and sizing,
  then hands off final visual review to Deepvue.
- Aperture does not implement its own price-chart or drawing system.

## 3. Non-negotiable separation

Structure describes directional condition. Setup describes a measurable event or
configuration. Lifecycle describes a Setup's development. Leadership, groups,
extension, regime, earnings, actionability, risk, sizing, and portfolio policy are
independent downstream dimensions.

- Structure must not encode Setup, leadership, group strength, extension, earnings,
  regime, or actionability.
- Setup must not decide whether a setup should be traded.
- Extension is not a Structure state.
- Setup invalidation is not a trade stop.
- No arbitrary Structure or Setup confidence percentage is emitted.
- Multiple Setup families may coexist.

## 4. Settled grammar

Structure states:

`NEUTRAL | EMERGING | UPTREND | DETERIORATING | DECLINE`

Setup families:

`EP | CONTRACTION | TREND_PULLBACK | RANGE`

Setup lifecycle:

`FORMING | NEAR_TRIGGER | TRIGGERED | RESOLVED | FAILED | STALE`

`RECLAIM` is evidence, not a Setup family. Lifecycle is monotonic. `STALE` is
pre-trigger only. Terminal instances never reactivate.

## 5. Settled target Structure design

Structure V2 implements the final consolidated Word specification under
`AP-ENGINE-ALIGNMENT-001`; see [the V2 contract](engine-alignment-v2.md) for
source provenance, exact version selection, and explicit interpretations:

- SMA20 and SMA50 are the voting averages.
- EMA10 and SMA200 are calculated context but do not vote.
- Use Wilder ATR14.
- Use ATR-normalized close distance from SMA20 and SMA50, SMA20/SMA50 separation,
  SMA20 and SMA50 slopes, and ten-session persistence above SMA20.
- Use entry/retention hysteresis and consecutive-session confirmation.
- A normal pullback may remain `UPTREND` while Setup reports
  `TREND_PULLBACK`.
- A long horizontal base may be structurally `NEUTRAL` while Setup reports
  `RANGE` and/or `CONTRACTION`.
- A positive shock may move directly to `EMERGING`, not directly establish
  `UPTREND`.
- A negative shock may move directly to `DETERIORATING`, not directly establish
  `DECLINE`.

The current runtime `structure-engine-v1` uses an EMA10/SMA20/SMA50 stack and a
different predicate/transition model. It remains reproducible V1 output alongside
the explicitly selected V2 implementation. Existing snapshots retain their explicit engine identities. Under owner-authorized
`AP-V2-GROUPS-ACTIVATION-001`, newly constructed version selections default to the
reviewed coherent V2 pair and fingerprints. Explicit V1 generation remains available.

## 6. Settled Setup decisions

Retain from the final Word design:

- four families only;
- RECLAIM as evidence;
- simultaneous families without primary/secondary ranking;
- objective ATR-aware measurements;
- long-lived RANGE/base representation;
- no subjective classical-pattern or VCP-leg artistry;
- no setup confidence score.

Retain the implemented Git V1 safety corrections:

- trigger geometry committed from data known through T-1;
- stable setup identity independent of moving price hashes;
- explicit reference timestamps and frozen failure buffers;
- deterministic failure/trigger/resolution/staleness event order;
- failure precedence;
- no-look-ahead or same-day moving-boundary triggers;
- terminal non-reactivation and immutable transition history;
- split/corporate-action quarantine for EP;
- explicit missing-data evidence and corrected replay when a required failure
  session was unobservable;
- removal of mathematically unreachable failure predicates.

Implemented Setup V2 lifecycle-age limits:

- `RANGE` may remain active for up to 60 trading sessions while its geometry and
  qualifying behavior remain valid.
- `CONTRACTION` must not become stale after only 15 sessions solely because of age.
  Use 40 trading sessions as the versioned maximum while compression and
  geometry remain valid.
- If a RANGE persists, expands, and later tightens again, retain the valid RANGE,
  stale the ceased CONTRACTION, and create a new CONTRACTION instance.
- Loss of qualifying behavior, meaningful geometry change, trigger, failure, and
  terminal lifecycle rules remain independent of maximum age.

## 7. Choices settled for V2

The authorized bounded comparison is complete. V2 selects:

- Word closing-dispersion CONTRACTION ratios .75/.75 and true-range ratio .80;
- a single robust 20-session RANGE;
- geometry shift strictly greater than 1 inception ATR;
- TREND_PULLBACK only in UPTREND/DECLINE; EMERGING remains context;
- five-session CONTRACTION/RANGE observation, with five-/three-session failure
  windows respectively.

The [V2 contract](engine-alignment-v2.md) explicitly documents incomplete Word
transition details, P20 equality/complement handling, initialization and counters,
transitional exits, and retained Git safeguards. These interpretations must not be
mistaken for verbatim Word rules. Change them only under a new version.

The small identical-input comparison measured classification changes and churn,
not future returns. It does not establish improved predictive performance or
reduced churn. Results and limitations are in the
[completion receipt](engine-alignment-v2-receipt.md).

## 8. Current implementation truth

As of commit `401e1b0afd6ad2a4678af4f1040014b5c9b568e9`:

- the Python Structure, Setup, Leadership, Regime, Decision/Risk, universe, and
  snapshot layers are implemented as versioned deterministic modules;
- FastAPI and the React Workstation are implemented;
- the first real bounded current-state snapshot is validated;
- current runtime Structure/Setup outputs use the implemented V1 contracts, not
  the target alignment in sections 5-7;
- legacy scores/states are preserved but explicitly excluded from current
  Aperture decision voting;
- Groups lacks published membership in the first snapshot;
- Deepvue remains external to runtime.

### AP-ENGINE-ALIGNMENT-001 implementation

Structure/Setup V2 now exist as independent versioned implementations with explicit
materializer dispatch, typed API evidence, and rules fingerprints. The original V1
snapshot still decodes with its original fingerprint. A separate, labeled V2
comparison snapshot preserves its T/E/A clocks and original expiry. It is not a
new market refresh or a production source-data publication. Groups and other
known evidence gaps remain. See the completion receipt for observed test and
browser results, classification differences, and operational limits.

## 9. Document precedence

For current work, use this order:

1. `AGENTS.md` for repository safety and working rules.
2. This file for current product truth and target design decisions.
3. `PROJECT_STATE.md` for what is actually implemented and available.
4. `CODEX_NEXT_TASK.md` for the specifically authorized task.
5. Current implementation contracts and versioned code for runtime behavior.
6. Historical product contracts, decision overlays, milestone reports, session
   notes, and archived source specifications as evidence only.

An active task may implement a target decision only when it provides a new version
identity, migration/rebuild boundary, and acceptance criteria. Historical files
must not be edited to pretend a later decision was always true.

## 10. Change rule

If a future decision changes this authority, update this file and its effective
date, record the reason, identify affected runtime versions, and preserve the prior
implementation history. Never resolve a conflict by silently choosing the oldest,
longest, or most detailed document.


## 11. V2 activation and dated Groups publication

`AP-V2-GROUPS-ACTIVATION-001` activates the reviewed pair for new selections without
changing formulas, thresholds or 60/40 lifetimes. Retained V1 and V2 snapshots
remain readable with original fingerprints and freshness clocks.

Verified Deepvue hierarchy (September 7) and themes (September 5) are separately
published to a private local database/Parquet workspace. Production source inputs
remain unchanged. Sector, Group, Industry and Sub-Industry use full source parent
paths as group identities; conflicting labels are not canonicalized. Themes remain
many-to-many. Missing and unresolved identities remain explicit. Existing
Leadership V1 aggregation and eligibility gates are unchanged.

Historical membership first applies September 8 under its retained publication.
The owner-authorized continuation now permits explicitly versioned
`CURRENT_COHORT_AT_E` Groups to analyze completed-session price evidence using
membership known by evaluation and valid for the action session. This corrects the
prior historical-only restriction for current-state analysis. It does not backdate
membership or historical rotation. See [the current refresh contract and receipt](current-refresh-v2.md).

The verified real snapshot has 312 Groups. A supported locked daily refresh command
uses pinned XNYS closes/opens, bounded existing provider acquisition, recoverable
local publication and verified atomic activation. New pre-open evaluations derive
validity from their own action open and controls; old snapshot expiry is unchanged.
User-systemd scheduling and resume/premarket catch-up are installed locally. Linux
must be running; no unattended-host guarantee is made. Future membership validity,
provider delays and incomplete earnings remain explicit source/control limits.

## 12. Operator-approved current membership reuse

The owner-authorized PR #17 continuation adds `membership-reuse-policy-v1` and
`CurrentGroupProvenanceV3`. Verified captures can support CURRENT_COHORT_AT_E
between captures for 14 calendar days (hierarchy) / 7 (themes), warning 3 / 2 days
before exclusive UTC expiry. Source age remains anchored to the original capture
date, never authorization or rebuild time. New captures supersede prospectively.
The separate hashed policy authorizes reuse; it is not provider reconfirmation.
Original schedules/receipts and historical selection remain unchanged. Independent
identity, tradability, earnings and other controls are not extended. See
[the policy contract and receipt](membership-maintenance-v1.md).


## 13. Explicit expanded coverage

The owner-authorized `AP-UNIVERSE-EXPANSION-001` replaces the initial cohort as a
permanent operational cap with a hash-pinned, versioned coverage publication.
Candidate identity, research, strict trade, mapping and history readiness remain
separate. Existing security/exposure/universe rules and V2 engine formulas are
unchanged. Missing taxonomy/themes do not exclude otherwise eligible stocks.
Unresolved identities and incomplete histories stay explicit in private coverage.

`coverage-current-state-v1` binds current API evidence to the published coverage
manifest. Daily refresh acquires every published covered identity and required
benchmark, rejects unreviewed additions and preserves independent membership,
identity, earnings, adjusted-history and freshness gates. It never creates historical
membership/rotation. Retained V1/V2 snapshots preserve their original fingerprints.
See [published coverage V1](universe-expansion-v1.md) and its completion receipt for
observed population, source limits, scale verification and scheduler deployment.
