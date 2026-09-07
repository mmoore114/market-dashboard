# Aperture Current Authority

Status: **CURRENT PRODUCT AUTHORITY**

Effective: 2026-09-07

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

The next Structure version will align to the final consolidated Word specification:

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
different predicate/transition model. It remains valid historical V1 output until
a separately authorized, newly versioned alignment is implemented. Do not silently
replace or relabel it.

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

Settled lifecycle-age direction for the next Setup version:

- `RANGE` may remain active for up to 60 trading sessions while its geometry and
  qualifying behavior remain valid.
- `CONTRACTION` must not become stale after only 15 sessions solely because of age.
  Use 40 trading sessions as the initial target maximum while compression and
  geometry remain valid.
- If a RANGE persists, expands, and later tightens again, retain the valid RANGE,
  stale the ceased CONTRACTION, and create a new CONTRACTION instance.
- Loss of qualifying behavior, meaningful geometry change, trigger, failure, and
  terminal lifecycle rules remain independent of maximum age.

## 7. Provisional choices requiring only a bounded comparison

The following are not reasons to delay documentation or product alignment. Compare
them quickly on identical existing data before freezing a new engine version:

- final CONTRACTION measurement formula and thresholds;
- 20-session-only versus 30-first RANGE detection;
- exact geometry-shift ATR threshold;
- whether EMA10/SMA20 pullbacks in `EMERGING` are labeled
  `TREND_PULLBACK` or remain contextual evidence until `UPTREND`;
- exact post-trigger observation clocks for CONTRACTION and RANGE.

This is a classification sanity comparison, not threshold optimization or a large
backtest. Do not tune rules to famous winners or future returns.

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
