# Decision & Risk Layer V1 — AP-DECISION-RISK-001

Status: `experimental_uncalibrated`. This opt-in layer composes the completed
engines into explicit direction-aware evidence, a decision ladder and per-idea
size. It performs no data loading, event lookup, publication or order submission.
ACT means perform discretionary review for the supplied next exchange session.
It does not choose an entry, a trade stop or a primary setup.

## Public APIs and frozen contracts

- `decision_contracts.py`: frozen, extra-field-forbidding, finite-or-null input,
  extension, event, coverage, strength, group, regime gate, sizing, per-setup,
  symbol/direction and complete daily output schemas.
- `decision_policy.py`: immutable new thresholds and deterministic fingerprint,
  bound to the unchanged caller-supplied `ApertureRules` configuration.
- `decision_components.py`: pure extension, strength, group, default-stop helper
  and explicit-entry/stop sizing functions.
- `decision_events.py`: pure completed-close earnings evaluation.
- `decision_adapters.py`: existing Structure feature and Universe snapshot/
  membership adapters, plus cross-engine identity and provenance validation.
- `decision_risk.py`: `evaluate_decision` and `evaluate_daily_decisions`.

```python
features = features_from_structure(structure_output, source=source, calendar=calendar)
universe_input = universe_from_snapshot(
    decision_snapshot, source=source, calendar=calendar,
    universe=dated_research_universe, rules=caller_loaded_rules,
    completed_at=completed_T_close,
)
# Assemble DecisionInputV1 with explicit entry/stop, event coverage and engines.
output = evaluate_decision(inputs, calendar=calendar)
daily = evaluate_daily_decisions((long_inputs, short_inputs), calendar=calendar)
```

Daily batches require at least one explicit input and reject duplicate
symbol/direction keys, mixed session/action/source/universe evidence, and different
feature bases for two directions of the same symbol. Outputs sort by exact symbol
and direction for reproducibility. No omitted symbol or direction is inferred.

Engine: `decision-risk-v1`. Formula: `decision-risk-formulas-v1`.
Thresholds: `decision-risk-thresholds-v1`. Features: `decision-risk-features-v1`.
Input/output schemas: `decision-risk-input-v1`, `decision-risk-output-v1`,
`daily-decision-risk-output-v1`, `decision-event-input-v1`,
`decision-event-coverage-v1`, `decision-sizing-input-v1`.

Decision rules fingerprint:
`59109ef7baa8af98f6aea0cdea726060b7ce1dac7f647d43e342b027c61518a8`.
The exact immutable foundation configuration fingerprint is:
`920a29facf60a0c5375d094fa669dc2ed402504f3e80ef256feb2ed1724b03e0`.
The new rule hash binds that fingerprint, new named thresholds and formula/timing
semantics. A changed configuration is rejected; it needs a separately versioned
hypothesis. No configuration file is read by these APIs.

## Timing, source and compatibility boundary

Inputs identify the completed session T, an explicit aware close timestamp,
calendar ID and prefix fingerprint, and the exact next exchange session T+1 as
`action_session`. Same-session action, a later substituted action date, malformed
calendars and misaligned timestamps are rejected. No weekends, holidays, closing
times or missing sessions are inferred. The caller attests the actual completed
close and supplies the exchange calendar. Future calendar extension beyond all
required T+5 evidence does not change the result.

Symbols use exact `MarketDataSymbol` identity with no case conversion, alias or
crosswalk lookup. Reference callers must first use the existing explicit
compatibility boundary. `$VIX` is not a decision equity. Prices have the existing
`StrengthSourceV1` split-adjusted basis with explicit vendor/dataset, dividend
and volume conventions. Universe snapshots retain exposure and universe policy
versions, dated research provenance and all three distinct memberships. Only
current equity-trade membership votes at WATCH. The snapshot adapter rejects
stale/future-observed/wrong-version snapshots and ignores legacy action/stage/
regime fields. Direct membership adaptation requires caller-attested provenance.

Structure and Setup inputs must match exact symbol, T, source, current rules
fingerprint, close, Wilder ATR and calendar index. SMA50 and embedded Structure
must agree. Setup instance dates/indexes, geometry references and identities must
be valid and nonfuture; duplicate IDs are rejected. Structure's existing ATR14
is Wilder ATR14; legacy simple rolling ATR is never substituted.

Leadership requires the exact T/source/calendar/research-universe/rules identity,
one observation per research member, matching nested component provenance and
valid dated group membership. Nested group member IDs must match their group.
Missing evidence is not calculated from another legacy field or score.

Future regime evidence is rejected. Stale, wrong-source, wrong-universe,
wrong-calendar, wrong-rules, same-session-ineligible and action-date-mismatched
regime evidence becomes distinct visible TRADE veto evidence. State/status/
confirmed-memory inconsistency also blocks. UNKNOWN never falls back to historical
confirmed memory. The entire supplied regime evidence remains available in the
output input contract. Existing engine versions and rules fingerprints remain
visible through their original nested contracts.

## Direction-aware extension

`extension = sign * (Close-SMA50)/WilderATR14`, sign +1 LONG and -1 SHORT.
Inputs retain prices, ATR, direction, session/source and calendar fingerprint.
Positive finite close/SMA50/ATR are required. Missing or invalid data produces
INSUFFICIENT_DATA with a distinct reason. Schemas reject NaN/infinities;
nonrepresentable calculated results remain null.

The existing configured bands are retained in every extension result:

| Signed extension | State |
|---|---|
| <0 | BELOW_REFERENCE |
| [0,3) | ENTRY_ZONE |
| [3,5) | HEALTHY |
| [5,7) | EXTENDED |
| >=7 | EXTREME |

New-entry eligibility is **0 through 4.8 ATR inclusive**. Classification and
entry eligibility are separate: 4.9 is HEALTHY but cannot promote ACT. The legacy
extension functions and columns remain unchanged. Decimal arithmetic for nominal
input prices avoids introducing a rounding tolerance at the inclusive boundary.

## Event records, freshness and coverage

Each `EventInputV1` retains exact symbol, EARNINGS discriminator, source event ID,
nullable scheduled exchange session, timing, confidence, source, observed-at and
source-as-of timestamps, LIVE/CANCELLED/REPLACED status and explicit replacement
ID. Unknown source/timestamps are representable and cannot establish clearance.
The event discriminator and schema version provide a future extension point;
other event types are not assigned invented V1 semantics.

The specification does not prescribe a provider-specific freshness duration.
Following existing caller-attested snapshot practice, events and coverage require
`fresh_for_session=T`. This is an explicit freshness assertion, not inferred from
record age. Both aware timestamps must be present and no later than T close;
source-as-of cannot follow observed-at. Missing attestation is UNKNOWN; another
session is stale. Old scheduled dates can remain valid when the caller supplies
current, explicitly verified freshness. No arbitrary TTL is introduced.

Coverage is symbol/event-type scoped and retains source/timestamps, covered start
and end exchange sessions, and COMPLETE/INCOMPLETE/UNKNOWN status. To establish
CLEAR it must be fresh and COMPLETE from at least T through T+5 inclusive. T is
included to account for after-close earnings. Missing, stale, incomplete or short
coverage makes aggregate eligibility UNKNOWN unless a known veto already blocks
it. An empty event list alone **never** proves clearance. The supplied calendar
must identify T+5 and the stated coverage endpoints.

Event distance is the difference of supplied exchange-session indices:

- T AFTER_CLOSE: distance 0, still effective.
- T BEFORE_OPEN or DURING_SESSION: already past, no next-session veto.
- T UNKNOWN timing: conservatively effective at distance 0, with UNKNOWN
  eligibility because timing is unverified.
- Next exchange session: distance 1; weekends and holidays consume no slots.

Live CONFIRMED and ESTIMATED events at distances 0..5 inclusive have distinct
hard-veto reasons. Distance 6 is outside the veto window when evidence is fully
known. Missing date/calendar position, timing, confidence or source freshness
makes a relevant event UNKNOWN. Unknown timing inside the window retains the
possible in-window veto reason alongside its UNKNOWN status.

Fresh explicit cancellations do not veto and remain in evidence. Replacements
require a REPLACED status and a same-source replacement ID resolving to a known
record. Missing replacement targets yield UNKNOWN; self/cyclic replacement
chains and duplicate source/event IDs are rejected. No ticker/date proximity
infers a replacement. Every known event remains visible, including farther events,
cancellations and replacements. Select one known revision per source/event ID.

Events first observed after T close are excluded before output construction;
future cancellations or schedule mutations cannot rewrite T. This API does not
reconstruct prior revisions from a current event record. The caller must supply
its actual point-in-time event snapshot. Future source-as-of timestamps cannot
establish freshness; coverage learned after close does not prove CLEAR.

Summary precedence: a known hard veto is BLOCKED; otherwise any unresolved event
or coverage is UNKNOWN; otherwise CLEAR. The nearest known veto is selected only
for summary display (stable source/ID tie-break). All event evidence and all
unresolved reasons remain available even when a nearer veto already blocks ACT.

## Strength and structural group gates

LONG strength has two independent branches:

- established: `RS_comp >=60`;
- new rotation: `RS_comp >=40 and RS_rotation >=80 and rotation_delta >=15`.

Every comparison and its original value/threshold is stored. Either true branch
is sufficient. An incomplete branch is unknown; when neither branch is true and
one is incomplete, eligibility is STRENGTH_UNKNOWN. In particular, established
strength does not require otherwise-unused short-horizon values. No missing
value is replaced with zero, and no stock score is altered or combined.

Only exact, currently effective SUB_INDUSTRY membership votes for the group gate.
Zero or multiple matching groups is UNKNOWN. A valid rank must be in [1, eligible
count] and the count must be positive. The inclusive not-lagging limit is
`ceil(.80*eligible_group_count)`; larger valid ranks are LAGGING. Average tied
ranks are compared directly: rank 8 passes out of 10, rank 8.5 does not.
Group rotation rank, rotation-rank advantage and all explicit theme memberships
are retained as nonvoting context. A leading theme cannot repair missing or
lagging sub-industry evidence.

## Ladder and per-setup evidence

Every gate is evaluated before selecting the highest consecutively passing rung.
Machine-readable codes and human explanations are separate fields. The decision
retains the complete failed-gate reason set; components also retain their own
predicate-level diagnostics. A higher rung cannot repair a lower failure.

| Rung | Requirements |
|---|---|
| WATCH LONG | Trade-universe eligible; EMERGING/UPTREND Structure; strength eligible |
| WATCH SHORT | Trade-universe eligible; DECLINE Structure |
| TRADE | WATCH; LONG promotion enabled; aligned GREEN/YELLOW regime eligible at T+1; NOT_LAGGING sub-industry |
| ACT | TRADE; qualifying LONG setup; extension eligible; earnings CLEAR; valid nonzero size |

Otherwise the symbol/direction remains at the prior achieved rung or NONE.
SHORT retains extension, strength, group, sizing and setup evidence, but
`SHORT_PROMOTION_DISABLED` caps promotion at WATCH. LONG strength is not an
additional requirement for SHORT WATCH.

Every supplied setup is retained, including all active instances and terminal
history. Qualification requires LONG in the evaluated direction, NEAR_TRIGGER or
TRIGGERED, evaluated, nonterminal and not replay-required. Setup engine errors
block qualification. FORMING remains visible without promotion. Every qualifying
ID/family is retained; no primary setup or ranking is created. `qualifying_setup_ids`
describes the setup gate; `act_setup_ids` is populated only when the entire ladder
reaches ACT. Each setup has its own qualification/action flags and reasons.
Setup invalidation remains explicitly separate from the caller's trade stop.

## Per-idea risk sizing

Explicit caller proposals supply equity, available buying power, entry and stop.
No default entry is selected. The separate optional helper returns:

- LONG stop: `entry-1.6*WilderATR14`;
- SHORT stop: `entry+1.6*WilderATR14`.

A nonpositive proposed/helper stop is invalid. Setup invalidation is never used
as a substitute. Standalone SHORT sizing can describe an oriented hypothetical
size; it does not bypass the decision policy's SHORT promotion cap.

```text
base_risk = account_equity * .0025
allowed_risk = base_risk * (GREEN 1.0 / YELLOW .5 / RED 0.0)
distance = abs(entry-stop)
risk_based_shares = floor(allowed_risk/distance)
pilot_shares = floor(risk_based_shares/3)
affordable_shares = floor(available_buying_power/entry)
capital_constrained_shares = min(risk_based_shares, affordable_shares)
```

No margin or fractional shares are modeled. Buying power affects only affordable
shares, never the equity risk denominator. Both `risk_based` and
`capital_constrained` amount objects expose full shares, floor(shares/3) pilot
shares, full/pilot costs, full/pilot dollar risk, equity-risk percentages and
unused allowed risk. The constrained object's pilot is based on its constrained
full size; the unconstrained object's pilot preserves the exact specified formula.
Stop distance is also shown in dollars, percent of entry and Wilder ATR units.

Sizing status is INVALID for missing/nonpositive/nonfinite financial inputs,
incorrect stop orientation, invalid distance, zero constrained shares,
RED/UNKNOWN/misaligned/ineligible regime, and BLOCKED/UNKNOWN earnings. Schemas
refuse nonfinite inputs. Nonrepresentable calculations emit nulls and invalid
reasons. Decimal arithmetic preserves price and whole-share floor boundaries.
A valid one-share full size may have zero pilot shares; the specified pilot floor
is not replaced with a minimum-one-share rule.

Calculable theoretical amounts remain visible on INVALID results, but must not
be used as an available size. `status=VALID` is required for ACT. CAPITAL_CONSTRAINED
is an informational reason on a still-valid positive constrained size.

Synthetic examples, $25,000 equity, entry $100, explicit stop $98:

| Regime / buying power | Base / allowed risk | Risk shares / pilot | Capital shares / pilot |
|---|---|---|---|
| GREEN / $25,000 | $62.50 / $62.50 | 31 / 10 | 31 / 10 |
| YELLOW / $25,000 | $62.50 / $31.25 | 15 / 5 | 15 / 5 |
| GREEN / $2,500 | $62.50 / $62.50 | 31 / 10 | 25 / 8 |
| GREEN / $99.99 | $62.50 / $62.50 | 31 / 10 | 0 / 0, INVALID |

GREEN unconstrained full risk is $62, .248% of equity, with $.50 unused risk.
With $2,500 buying power, constrained risk is $50 and unused risk $12.50; the
base remains $62.50. With ATR $2, the separate LONG default-stop helper gives
$96.80. These are synthetic formula demonstrations, not selected trades.

## Verification and scope

Focused tests cover all band/equality boundaries, event timing and freshness,
explicit replacement chains, both strength branches, group ties, independent
ladder gates and 64 combined failure paths, all setup lifecycle statuses, multiple
qualifying IDs, SHORT caps, default/explicit stops, monetary floors, zero shares,
capital constraints, complete reasons, exact identity/provenance and future-event
mutation invariance. Frozen JSON round trips and a golden rules fingerprint are
checked. Every new test blocks socket/httpx access; the complete pipeline also
runs with builtins/io/os file-open APIs forbidden and preserves input objects.

See PROJECT_STATE for observed focused/full-suite totals and protected-file
verification. Universe, Structure, Setup, Leadership, Regime, legacy extension,
legacy snapshots and immutable configuration are unchanged.

Portfolio heat/concentration, position management, exits, journal, API/UI,
ingestion, publication and brokerage behavior remain deferred. The unrelated
security-master timestamp-precision publication blocker remains unchanged.
