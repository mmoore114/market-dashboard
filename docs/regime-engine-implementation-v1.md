# Market Regime Engine V1 — AP-REGIME-001

Status: `experimental_uncalibrated`. This is an opt-in, pure research layer.
The frozen assignment in `CODEX_NEXT_TASK.md` defines the initial hypothesis.
Legacy `aperture-regime-v1`, YAML risk multipliers, Structure, Setup, Leadership,
exposure policies and production outputs retain their existing meanings.
No new-risk permission, sizing calculation or order behavior is implemented.

## API and identity

- `regime_contracts.py`: frozen, extra-field-forbidding, finite-or-null Pydantic
  inputs, component evidence, confirmed memory and output contracts.
- `regime_policy.py`: immutable thresholds and deterministic SHA-256 of canonical
  sorted JSON containing thresholds, formulas, timing and transition rules.
- `features/regime_features.py`: pure full-window means and endpoint returns.
- `regime_adapters.py`: caller-loaded daily bars, a separately identified spot
  series, dated equity research universe, optional Structure and Leadership
  evidence to `RegimeInputV1`.
- `regime.py`: independent sleeves, aggregate candidate, transition function and
  `evaluate_regime(inputs, calendar=..., previous=...)`.

Versions are `market-regime-v1`, `market-regime-features-v1`,
`market-regime-thresholds-v1`, `market-regime-input-v1` and
`market-regime-output-v1`. Rules fingerprint:
`3e13d0e057fbc80d806e8eab8fb3b9060b1c3f5de60bf45f8fb33ae15abec01a`.

```python
inputs = regime_input_from_bars(
    equity_bars, spot_bars, session=T, calendar=exchange_sessions,
    source=source, universe=dated_equity_research_universe,
    volatility_identity=spot_identity, structure=structure_evidence,
    leadership=leadership_output,
)
output = evaluate_regime(inputs, calendar=exchange_sessions, previous=prior_output)
```

The caller owns loading, completed-session attestation, calendar correctness,
point-in-time universe selection and source provenance. Existing
`leadership_adapters.research_universe` and `research_memberships` adapt the
existing decision/universe contracts using **equity research** eligibility.
The bar adapter uses exact `MarketDataSymbol` validation without case conversion;
reference identities must first pass the existing explicit compatibility boundary.
It never consults unapplied crosswalks or loads a security master.

All equity closes share `StrengthSourceV1`: split-adjusted prices, explicit
vendor/dataset, dividend treatment, volume convention and calendar identity.
The adapter checks any corresponding columns present in supplied bars; explicit
source arguments attest metadata absent from legacy bar frames. Direct feature
input callers attest the same batch-level source, T and universe alignment.
Every research member must have one breadth row, even when all values are null.
Duplicate symbol/session observations through T, non-calendar observations,
intraday/ambiguous timestamps and mixed source columns are rejected.

VIX has `spot-volatility-identity-v1`, canonical `$VIX`, the exact
`deepvue-identity-disposition-v1` non-security identity, explicit source symbol,
vendor/dataset, spot-implied-volatility-points basis and equivalence evidence.
`spot_identity(...)` validates the caller-loaded canonical disposition fingerprint.
An equivalent series must explicitly attest that equivalence; a volatility ETF
or realized-volatility series is not implicitly interchangeable with spot VIX.
Spot frames use `series_id/date/close`; VIX never becomes an equity universe
member or security-master lookup. `$VIX` is rejected by the price-feature schema.

Optional Structure evidence requires exact T, source, universe wrapper and current
Structure rules fingerprint. Errored states have no valid structure vote.
Leadership requires exact T, source, calendar prefix, universe snapshot/policy,
current rules fingerprint, one symbol output per member, and aligned nested
symbol provenance. Group keys must be unique, memberships valid at T and
sub-industry security memberships non-overlapping. Themes may overlap; their
values never enter the internals sleeve. Effective dates must be on the supplied
calendar. The adapter never backdates current memberships.

## Features and independent sleeves

All means include T and require every session slot in their window. Nonpositive,
missing or nonfinite bar prices become missing features. Typed numeric inputs
reject NaN/infinities; nonpositive typed prices cannot vote. No gaps are filled.
Endpoint returns require only their two endpoint closes. Interior gaps do not
shift endpoints. Extreme nonfinite calculated results remain null.

### Index structure

For each of SPY, QQQ and IWM:

- CONSTRUCTIVE: `C > SMA20 > SMA50` and `SMA20 > SMA20[T-5]`.
- DEFENSIVE: `C < SMA50` and `SMA20 < SMA20[T-5]`.
- MIXED: every other fully evaluated case; equality is not directional.
- UNKNOWN: any required feature is unavailable/nonpositive.

GREEN requires at least two constructive and no defensive votes. RED requires
at least two defensive votes. Other fully evaluated combinations are YELLOW.
Any unknown index makes the sleeve UNKNOWN. Each index retains original feature
values, five-session SMA20 change in price units, individual predicate outcomes
and explicit failed/missing-predicate reasons.

### Breadth

Each price fraction has its own valid close/MA denominator and full universe
population count. A member exactly on the MA is valid but not above it; equality
counts are explicit. Each denominator requires at least 100 members and 60%
coverage. A failure in either gate makes the sleeve UNKNOWN.

- GREEN: above-SMA20 fraction >= .55 and above-SMA50 fraction >= .50.
- RED: above-SMA20 fraction < .35 and above-SMA50 fraction < .40.
- YELLOW: other gate-passing combinations.

Constructive Structure breadth is `(EMERGING or UPTREND)/valid supplied states`,
with its own denominator, population coverage and missing-context reason. It
never gates the price sleeve. Missing Structure does not count as NEUTRAL.

### Leadership internals

The three symbol fractions use independent valid denominators:

- strong leadership: `RS_comp >= 80`;
- strong rotation: `RS_rotation >= 80`;
- positive rotation: `rotation_delta > 0`.

Every symbol denominator requires >=100 valid members and >=60% universe
coverage; absent Leadership makes this sleeve UNKNOWN. Strong leadership remains
visible context and is not blended into a new stock score.

The common group denominator contains SUB_INDUSTRY groups eligible for leadership
rank (the existing >=5-valid-composite and >=60%-coverage gates) with non-null
median composite and median rotation delta. Rank and the underlying eligibility
counts must agree that the group is usable. At least five such groups are needed.
Leading groups have median composite >=60; improving groups have median delta >0.
Both fractions share that common valid denominator; total supplied sub-industries,
coverage, eligible IDs and excluded IDs remain explicit. This common-denominator
interpretation prevents missing medians from becoming false negative votes.

In order strong rotation, positive rotation, leading groups, improving groups:

- GREEN: every fraction >= (.20, .50, .35, .50).
- RED: every fraction < (.10, .35, .20, .35).
- YELLOW: other gate-passing combinations.

### Volatility

Requires positive current spot close and full SMA20. RED takes precedence:

- RED: close >=25 or close >=1.15*SMA20.
- GREEN: close <20 and close <=1.05*SMA20.
- YELLOW: other valid cases; UNKNOWN when the required values are unavailable.

Context retains five-session percent change `100*(C/C[T-5]-1)` and SMA20
percent distance `100*(C/SMA20-1)`. Missing five-session endpoints do not block
classification. Thresholds are uncalibrated hypotheses.

### Style and participation

For SPY/RSP/QQQ/QQQE, `R21=C[T]/C[T-21]-1`, in fractional units.
Broad gap is `RSP_R21-SPY_R21`; Nasdaq gap is `QQQE_R21-QQQ_R21`.

- GREEN: both equal-weight returns >0 and both gaps >=-.03.
- RED: both equal-weight returns <=0 and both gaps <-.03.
- YELLOW: other evaluated combinations.
- UNKNOWN: any required endpoint/return is unavailable.

All four returns and both gaps remain visible.

## Aggregate and confirmed memory

Sleeve scores are GREEN +1, YELLOW 0, RED -1, UNKNOWN null. Counts and every
sleeve remain visible; no master numerical score controls the state.

The normal candidate requires all five sleeves:

- GREEN: index and breadth GREEN, no RED sleeve, and >=3 GREEN sleeves.
- RED: index RED with breadth or volatility RED, or >=3 RED sleeves.
- YELLOW: other fully evaluated combinations.
- UNKNOWN: one or more UNKNOWN sleeves.

| Previous confirmed state | Candidate | Result |
|---|---|---|
| Uninitialized | Fully evaluated | Initialize YELLOW |
| YELLOW | GREEN / RED | Confirm after two consecutive matching candidates |
| GREEN / RED | Same state | Hold immediately |
| GREEN / RED | YELLOW | Move to YELLOW immediately |
| GREEN / RED | Opposite direction | Move to YELLOW, reset streak |
| Any | UNKNOWN | No state today; retain confirmed memory, reset streak |

The initialization session counts as the first directional candidate, but its
emitted state is always YELLOW absent an override. A confirmed directional
transition consumes/resets the pending streak. The first opposite candidate
moves to YELLOW without starting a fresh streak; two subsequent matching
candidates are required to confirm the opposite direction. Missing exchange
session outputs also reset candidate continuity. Actual dated universe snapshot
changes are allowed; a source, universe-policy, spot identity or rule-version
change requires replay rather than silently transferring state memory.

A same-session risk-off override supersedes missing sleeves and hysteresis if:

1. at least two observed indexes are DEFENSIVE and the independently gated
   above-SMA20 breadth fraction is <.30; or
2. the current positive spot close is >=30.

Only inputs for the qualifying branch must be valid. The first branch can work
with a third unknown index or missing SMA50 breadth; the second needs no SMA20.
Neither fills missing evidence. A qualifying override establishes RED even on
the first observation, and resets the streak. Both qualifying reasons are saved.
The normal candidate and unknown sleeve count remain visible beside the override.

`state` is null and `status` UNKNOWN on a missing normal result without override.
`memory.confirmed_state` is explicitly historical. `entered_date` and
`sessions_in_state` describe only emitted state; unknown sessions expose null/0
there. Memory retains the last confirmed entry and count. Counts include only
observed emitted sessions in the held state, never skipped/UNKNOWN sessions.
A transition starts its count at 1. An override holding RED preserves its entry.

## Timing, examples and verification

Regime uses completed T data; `eligible_from_session` is the explicitly supplied
next exchange session, never T. A final calendar entry has null eligibility with
`NEXT_EXCHANGE_SESSION_NOT_SUPPLIED`; UNKNOWN output has no eligibility. Future
bars are ignored. Calendar fingerprints hash only the prefix through T, allowing
future extension without changing historical evidence. Callers supply an actual
exchange calendar; the engine does not infer weekends or holidays.

Representative paths:

- GREEN candidates on T and T+1: YELLOW/streak 1, then GREEN/streak 0.
- Confirmed GREEN followed by three RED candidates: YELLOW/0, YELLOW/1, RED/0.
- YELLOW with GREEN, UNKNOWN, GREEN: YELLOW/1, no state/0, YELLOW/1.
- Spot close 30 with missing Leadership and missing VIX SMA20: normal candidate
  UNKNOWN, volatility sleeve UNKNOWN, override RED; eligible no earlier than T+1.
- 120 valid breadth members out of 200 pass coverage; 120 out of 201 do not.

Focused tests cover all 64 index vote combinations, all 1,024 aggregate sleeve
combinations, strict/inclusive thresholds, independent denominators, context
alignment, frozen schemas, transitions, missing history and future mutation.
Every new test blocks socket/httpx requests. The full adapter/engine test also
forbids builtins/io/os file-open APIs and checks inputs unchanged. The complete
suite includes the unchanged Structure, Setup, Leadership and legacy regressions.
Observed test totals and protected-file checks are recorded in PROJECT_STATE.

Production integration/publication, empirical calibration, actionability,
extension/earnings gates, risk sizing, portfolio heat and UI remain deferred.
The separate security-master timestamp-precision blocker is unchanged.
