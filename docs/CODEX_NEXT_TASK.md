# Codex Next Task

**Task ID:** AP-SETUP-001

**Status:** COMPLETE

**Issued:** 2026-09-06

**Base commit:** `29de3ef5abffe887dcc7d42af7e93feecd370165`

## Handoff protocol

This file is the single current assignment for VS Code Codex.

1. Read `AGENTS.md`, `docs/PROJECT_STATE.md`, and every authoritative contract
   referenced below before editing.
2. Work through the entire bounded milestone autonomously. Do not stop for
   routine implementation choices already settled by repository contracts.
3. Ask the user only when authoritative contracts materially conflict, a
   required rule is genuinely absent, or an external/destructive action would
   be required.
4. At completion, change this task's status to `COMPLETE`, add a concise
   completion record, update `docs/PROJECT_STATE.md`, commit, and push the
   milestone branch.
5. The user-facing completion response should be short: full commit SHA, focused
   and complete-suite test totals, and any genuine blocker. Detailed evidence
   belongs in the repository.

Preserve `.vscode/settings.json`, `.env`, credentials, databases, Parquet/CSV
datasets, staged artifacts, generated reports, and all unrelated user changes.

## Milestone

Implement the complete deterministic Aperture Setup Engine V1.

Create and work on:

`codex/setup-engine-v1`

Base it on this handoff branch after pulling the task-file commit. Preserve the
completed Structure Engine V1 at `29de3ef5abffe887dcc7d42af7e93feecd370165`.

## Authoritative sources

Read and follow:

- `AGENTS.md`
- `docs/PROJECT_STATE.md`
- `docs/aperture_product_contract.md`
- `docs/architecture_decision.md`
- `docs/setup-classification-engine-v1.md`
- `docs/structure-state-engine-v1.md` only to preserve the structure/setup
  boundary and consume the new typed Structure Engine output where required
- `docs/engine-spec-decisions-v1.md`
- `docs/engine-spec-open-issues.md`
- `docs/structure-engine-implementation-v1.md`

The approved decision overlay supersedes conflicting recovered prose, examples,
and archived sources. Implement U1-U8 exactly. Do not reconstruct rules from
chat history or redesign settled formulas.

## Required taxonomy and lifecycle

The only setup families are:

- `EP`
- `CONTRACTION`
- `TREND_PULLBACK`
- `RANGE`

Multiple valid setup instances may coexist. Do not rank them as primary or
secondary. `RECLAIM` is evidence, never a fifth setup family.

The only lifecycle statuses are:

- `FORMING`
- `NEAR_TRIGGER`
- `TRIGGERED`
- `RESOLVED`
- `FAILED`
- `STALE`

`STALE` is pre-trigger only. Terminal instances never reactivate. `RESOLVED`
means the observation window completed without setup failure; it does not assert
trade profitability.

## Implementation scope

Deliver:

- pure production feature and setup-calculation logic;
- explicit, frozen, versioned input, instance, evidence, and output schemas;
- deterministic detection for all four families and both directions;
- the complete stateful lifecycle for multiple concurrent instances;
- stable setup identity and committed T-1 geometry with stored
  `reference_as_of_session`, reference price, reference ATR, controlling
  boundaries, window, and reference kind;
- exact per-session event order: input/corporate-action validation, failure,
  trigger, resolution, pre-trigger staleness, then tomorrow's geometry;
- explicit geometry refresh/rebuild behavior and terminal history retention;
- deterministic reason codes, passed/failed rules, contradictions, and flags;
- rejected EP-candidate diagnostics without emitting invalid setup objects;
- point-in-time replay using only information available at the evaluated
  session;
- an explicit adapter from the existing daily-bar and Structure Engine V1
  contracts without I/O or implicit identity conversion;
- missing-data, nonpositive-input, volume, corporate-action, and insufficient-
  history behavior exactly as specified;
- concise implementation documentation with formulas, event ordering,
  lifecycle transitions, version identities, and representative outputs.

Keep setup classification separate from market regime, group/industry/theme
leadership, relative strength, extension permission, earnings policy,
actionability, trade entry policy, stops, position sizing, portfolio heat, and
opportunity scoring. A setup invalidation level is not a trade stop.

Do not modify or relabel legacy setup or structure history. New consumers must
opt into the new V1 contracts.

## Non-negotiable decision details

- EP uses the approved conjunction: GapPct, GapATR, ShockATR, prior-20-session
  median-volume RVOL, and CLV. It does not require Close versus Open or a new
  high/low. EP is born `TRIGGERED`, event day is age zero, and failure precedes
  resolution on following session five.
- Horizontal triggers use geometry committed by T-1. Current-session highs,
  lows, moving averages, or ranges may not move the reference before today's
  trigger decision.
- Exact setup identity is
  `symbol|type|direction|detected_at|reference_kind`; a price hash is evidence,
  not identity.
- Contraction pre-trigger predicate loss uses the approved two-session
  `GEOMETRY_CEASED` staleness rule. Use the independent post-trigger failure
  rules; do not restore the impossible `R5 > 1.15*R10` rule.
- Only TREND_PULLBACK uses structure as a detection gate. Other structure/setup
  compatibility is display context and may warn, but may not suppress EP,
  CONTRACTION, or RANGE.
- Pullback triggers use the frozen T-1 moving average and ATR correction. A
  same-day reclaim flag alone is not a trigger.
- RANGE tries the trimmed 30-session box first and uses 20 only when 30 fails
  and 20 passes. Trigger, depth, drift, location, and touches use the selected
  trimmed box. Reject degenerate geometry.
- ATR5, ATR14, and ATR20 are Wilder ATRs. EP uniquely requires current and 20
  prior volume observations; volume remains evidence-only for the other three
  families.
- Preserve split/corporate-action quarantine behavior. A provider-confirmed or
  factor-explained split discontinuity cannot emit an EP.

## Required verification

Add focused tests covering, at minimum:

- every equality and threshold boundary for all four families and directions;
- all lifecycle transitions, clocks, precedence rules, and terminal
  non-reactivation;
- multiple coexisting instances and stable identity;
- T-1 committed trigger geometry and future-bar mutation/no-look-ahead tests;
- simultaneous failure versus trigger or resolution, with failure winning;
- geometry shift, geometry ceased, reference change, expiry, and new-instance
  behavior;
- EP median-volume denominator using exactly T-20 through T-1;
- missing/nonpositive ATR and family-specific volume behavior;
- range 30/20 precedence, trimmed boundaries, touches, drift, and degenerate
  geometry;
- pullback deepest-reference selection, structure gates, frozen-MA trigger, and
  incompatible-structure failure;
- contraction post-trigger failure and eight-session resolution;
- EP and pullback five-session resolution and range eight-session resolution;
- corporate-action EP quarantine;
- exact reference versus uppercase market-data identity behavior;
- preservation of legacy outputs and the completed Structure Engine tests;
- zero network calls in setup calculation and replay tests.

Run focused tests during development. At the end run:

`.venv/bin/python -m pytest`

`git diff --check`

Commit only reviewed source, configuration, documentation, and tests. Push
`codex/setup-engine-v1`. Do not merge, publish data, or open a production writer.

## Deferred work and publication blocker

The 2026-09-05 staged security-master artifact remains valid but production
publication is separately blocked by nanosecond Parquet versus microsecond
DuckDB timestamp precision. Do not fix or publish it during AP-SETUP-001.

Do not build leadership, groups, themes, regime, actionability, risk, UI, or
portfolio layers during this milestone. Do not apply crosswalk proposals, build
exposure classification, make provider requests, or alter staged/production
data.

## Completion report

At completion, record in this file and `docs/PROJECT_STATE.md`:

- implemented behavior and version identities;
- exact files changed;
- representative setup and lifecycle paths;
- focused and complete-suite test totals;
- any genuine unresolved decision or blocker;
- confirmation that protected data, settings, legacy outputs, and the Structure
  Engine remained unchanged.


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
