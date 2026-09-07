# Structure Engine V1 implementation

AP-STRUCTURE-001 implements the [canonical structure contract](structure-state-engine-v1.md)
with the [approved S1–S6 overlay](engine-spec-decisions-v1.md). The overlay wins
where recovered prose, examples, or transition tables differ. There is no
setup, extension classification, actionability, leadership, regime, sizing, or
opportunity score in this module. Numerical distance evidence is not a trade gate.

## API and identity

- `aperture.structure_contracts.StructureInputV1`: frozen, extra-field-forbidding,
  finite-or-explicit-null input schema (`structure-input-v1`).
- `aperture.structure_contracts.StructureEvidenceV1`: corresponding output schema
  (`structure-evidence-v1`), including complete input/provenance, measurements,
  conditions, state history, candidate streak, transition diagnostics and reasons.
- `aperture.structure.evaluate_structure(inputs)`: pure replay of typed features.
- `features.structure_features.build_structure_inputs(bars, source=..., as_of=...)`:
  pure adapter from the existing `daily_bars` ticker/date/high/low/close columns.
- `features.structure_features.evaluate_daily_structure(...)`: composed bar-to-evidence API.
- `features.structure_features.evaluate_reference_structure(reference, boundary, ...)`:
  explicit conversion through the complete snapshot's `CompatibilityBoundary`.

Engine, feature and threshold versions are respectively `structure-engine-v1`,
`structure-features-v1` and `structure-thresholds-v1`. Frozen named thresholds
and the immutable transition table produce a deterministic SHA-256 rules
fingerprint. The schemas support `model_json_schema()`, `model_dump_json()` and
validated JSON round trips. Evidence returned by the API is ready for a later
snapshot writer; this milestone adds no automatic publication or production writer.

The bar API requires an existing uppercase `MarketDataSymbol`, without converting
case. Reference callers must explicitly convert: TPC and BCPC map to themselves;
TpC and BCpC remain valid reference identities but are refused by this market-data
consumer. No FIGI crosswalk or casefold lookup is applied. Legacy S1/S2/S3/S4,
EMA9, simple ATR, `trend_stage`, `price_action_state`, and decision snapshots
remain untouched. Consumers must opt into the new daily state schema.

`StructureSourceV1` requires vendor, dataset identity, a consistently split-adjusted
price basis, recorded dividend treatment, and a matching volume convention.
These are caller-attested dataset facts, not inferred from `adjusted=true`.
Unknown dividend treatment must be recorded honestly; no total-return adjustment
is claimed. This adapter neither adjusts prices/volume nor reads a vendor/store.
Optional UTC bar timestamps are retained when supplied; session dates are never
used to invent a closing timestamp. Volume is not a structure voter.

## Features and eligibility

All windows are trailing supplied trading-session rows, inclusive of T unless
an explicit lag is specified. Calendar gaps create no synthetic bars. Duplicate
symbol/date keys, intraday/null session dates, invalid ranges, nonpositive prices,
infinite prices and implicit reference conversion are rejected. Input frames
are copied, date-sorted per symbol, and never mutated.

- EMA10: first valid close seed; `EMA[t]=(2/11)*C[t]+(9/11)*EMA[t-1]`.
- SMA20/50/200: arithmetic means with full windows only.
- TR: `max(H-L, abs(H-C[t-1]), abs(L-C[t-1]))`; the first row uses H-L.
- Wilder ATR14: first 14 TR arithmetic mean, then `(13*ATR[t-1]+TR[t])/14`.
  The existing tested Wilder helper is reused; simple ATR is unchanged.
- `s20=(SMA20[t]-SMA20[t-10])/ATR14[t]`;
  `s50=(SMA50[t]-SMA50[t-20])/ATR14[t]`.
- `distN=(C-MA_N)/ATR14[t]`; `gap_atr=(C[t]-C[t-1])/ATR14[t-1]`.
  This structure shock is close-to-close, not the opening gap used by setups.
- Above and below counts independently count strict comparisons in the last 15
  sessions. Equality counts in neither direction. Missing comparisons stay null.
- Range evidence: `(HH20-LL20)/ATR14`; drawdown: `(HH63-C)/ATR14`.
- Percent slopes, SMA200 location and 60-session SMA200 ATR slope are context only.
  Compression is range <= 6 ATR and never votes.

At least **250 prior sessions** are required, making row 251 the earliest eligible
row. All hard inputs (close, prior close, EMA10, SMA20/50, their lagged slope
references, ATR14 and prior ATR14, four strict counts) must be available; prices
and ATR denominators must be positive. Insufficient rows emit `state=null` and
`insufficient_history`. Missing hard inputs emit `missing_data`; nonpositive typed
hard inputs emit `nonpositive_input`. Explicit NaN/infinity is rejected by the
typed schema; pandas missing values become explicit nulls at the adapter boundary.

Missing evidence-only volume, range or SMA200 fields do not suppress state. A
missing recursive input does not forward-fill or reseed ATR/EMA: correct the data
and replay. This follows the shared recurrence's lack of an authorized reseed rule.
When a typed replay has an unavailable row, it emits no classification, clears
candidate continuity, and retains the last confirmed state solely as memory.
State age counts elapsed supplied sessions, including such unavailable rows;
these rows cannot count toward transition persistence. No inferred transition or
backfilled state is emitted during the gap.

## Predicates and precedence

The implementation preserves strict comparisons without rounding or epsilon:

```text
stack_up = EMA10 > SMA20 > SMA50
stack_dn = EMA10 < SMA20 < SMA50
SMA20_RISING/FALLING = s20 > 0.25 / s20 < -0.25
SMA50_RISING/FALLING = s50 > 0.20 / s50 < -0.20
SMA50_FLATISH = abs(s50) <= 0.20
HELD_50 / LOST_50 = C > SMA50-0.15*ATR / C < SMA50-0.35*ATR
HELD_20 / LOST_20 = C > SMA20-0.20*ATR / C < SMA20-0.40*ATR
ALIGN_UP = stack_up and SMA50_RISING and HELD_50
ALIGN_DN = stack_dn and SMA50_FALLING and C < SMA50+0.15*ATR
PERSIST_UP = above20_15 >= 11 and above50_15 >= 10
PERSIST_DN = below20_15 >= 11 and below50_15 >= 10
FORMING_UP = HELD_50 and SMA20 > SMA50 and SMA20_RISING
             and (s50 > 0 or C > SMA50+0.50*ATR) and above20_15 >= 8
BROKEN_UP = not stack_up and (LOST_20 or SMA20_FALLING or s50 < 0)
```

Candidate precedence: DECLINE (`ALIGN_DN and PERSIST_DN`), UPTREND
(`ALIGN_UP and PERSIST_UP`), DETERIORATING (`BROKEN_UP` and previous state in
EMERGING/UPTREND/DETERIORATING), EMERGING (`FORMING_UP`), residual NEUTRAL.
Failure of ALIGN_UP alone does not demote an uptrend.

## State transitions and hysteresis

The first fully eligible row always seeds NEUTRAL, even on a shock. Its ordinary
candidate starts streak one. Later rows use the approved edge table:

| From | Allowed target: required consecutive candidate sessions |
| --- | --- |
| NEUTRAL | EMERGING: 2; UPTREND: 3; DECLINE: 3 |
| EMERGING | NEUTRAL: 3; UPTREND: 3; DETERIORATING: 2 |
| UPTREND | DETERIORATING: 2 |
| DETERIORATING | UPTREND: 2; EMERGING: 2; NEUTRAL: 3; DECLINE: 2 |
| DECLINE | NEUTRAL: 3 |

Self-candidates hold immediately. All other ordinary edges are forbidden.
An illegal residual NEUTRAL or EMERGING candidate cannot demote UPTREND.
A changed candidate starts streak one. An accepted transition or accepted shock
resets the streak to zero. Blocked candidates never accumulate across a different
candidate. `blocked_transition_count` counts forbidden-edge attempts within replay.

After seeding, shocks precede the edge gate:

- Positive: `gap_atr >= 2.50`, C strictly above both SMA20 and SMA50. Target UPTREND
  if stack_up or dist50 >= 1; otherwise EMERGING. Accept from all states except
  UPTREND, which holds UPTREND without a new override.
- Negative: `gap_atr <= -2.50`, C strictly below SMA50. Target DECLINE if stack_dn
  or dist50 <= -1. Otherwise target DETERIORATING only from EMERGING, UPTREND or
  DETERIORATING; weak shocks from NEUTRAL/DECLINE hold their state.
- Accepted shocks set `shock_override=true` and reset streaks, including an
  accepted same-state negative shock. Hold-only cells do not accept an override.

`state_before` is the prior confirmed state entering this row; `previous_state`
and `previous_state_duration` retain the state preceding the current state run.
A transition starts age one and sets `state_entered_date`. Initialization is
reported separately from an ordinary transition. Reason codes are
`INITIALIZED_NEUTRAL`, `SELF_HOLD`, `PERSISTENCE_PENDING`, `PERSISTENCE_ACCEPTED`,
`FORBIDDEN_EDGE_HOLD`, `SHOCK_OVERRIDE`, `SHOCK_HOLD`, or an eligibility error,
plus `CANDIDATE_<state>` for eligible rows. Every condition is exposed; the
`failed_for_adjacent` diagnostic lists the false condition names without scoring.

## Representative synthetic outputs

These are synthetic paths, not empirical calibration or a trading recommendation.

| Supplied eligible candidates/path | Resulting state path |
| --- | --- |
| neutral, emerging, emerging, uptrend, uptrend, uptrend | NEUTRAL, NEUTRAL, EMERGING, EMERGING, EMERGING, UPTREND |
| uptrend, uptrend, uptrend from fresh replay | NEUTRAL, NEUTRAL, UPTREND |
| decline, decline, decline from fresh replay | NEUTRAL, NEUTRAL, DECLINE |
| UPTREND then broken, aligned, broken, broken | UPTREND, UPTREND, UPTREND, DETERIORATING |
| DETERIORATING then two uptrend candidates | DETERIORATING, UPTREND |
| UPTREND then -3 ATR close shock at dist50=-2 | DECLINE immediately, override=true |
| DECLINE then +3 ATR close shock at dist50=0.5, unstacked | EMERGING immediately, override=true |

For a synthetic 280-row series with `C=100+0.3*i`, H=C+1, L=C-1, row 251 seeds
NEUTRAL, row 253 enters UPTREND, and row 280 has state age 28. Flat closes emit
NEUTRAL after warmup, with above and below counts both zero.

## Reproducibility and acceptance

Replay the complete supplied history before selecting an output date. `as_of`
filters future bars before price/identity processing. Appending or mutating future
prices cannot change earlier evidence. Per-symbol feature replays require
consecutive prior-session counters and a single source/basis. Partial typed
replays deliberately start a new NEUTRAL seed; they are not resumable state
checkpoints. Signals describe T close; this API computes no fills or orders.

Focused verification covers every normal edge, shock matrix cell, equality and
near-threshold behavior, candidate interruption, state ages, missing data, strict
MA counts, EMA/Wilder seeds, current/prior ATR separation, JSON round trips,
future-data isolation, multiple symbols, synthetic trend/pullback/extension paths,
and explicit reference conversion. Network operations are forbidden in adapter
acceptance tests. Production and staged file hashes are checked separately.

No empirical universe-wide stability/calibration claim is made: the current
milestone uses synthetic fixtures and leaves all production bars untouched.
The separate September security-master publication blocker remains deferred:
DuckDB TIMESTAMP loses nanoseconds in 13,146 `last_updated_utc` values. This task
does not change its schema, publish any snapshot, build exposures, or apply the
23 proposed crosswalk mappings.
