# Setup Engine V1 implementation

AP-SETUP-001 implements the [canonical setup specification](setup-classification-engine-v1.md)
with the authoritative [U1–U8 decisions](engine-spec-decisions-v1.md). The latter
supersede recovered formulas and examples. The owner additionally confirmed that
an unobservable failure session requires corrected-data replay before an existing
triggered instance can resume. No success is inferred across missing observations.

## Public boundary and versions

`aperture.setup.evaluate_setups(inputs)` is a pure replay API. It accepts frozen
`SetupInputV1` rows and returns frozen `SetupOutputV1` daily outputs. The input,
instance, evidence and output schemas have separate `*-v1` schema identities;
engine, features and thresholds are `setup-engine-v1`, `setup-features-v1` and
`setup-thresholds-v1`. Pydantic rejects extra fields, nonfinite numbers and invalid
identities. Nested collections are tuples of frozen models, not mutable dictionaries.
JSON serialization/validated round trips and JSON Schema generation are supported.

The four families are EP, CONTRACTION, TREND_PULLBACK and RANGE. Direction is LONG
or SHORT; status is FORMING, NEAR_TRIGGER, TRIGGERED, RESOLVED, FAILED or STALE.
STALE is pre-trigger only. Terminal instances cannot reactivate. A geometry price
hash is evidence; identity is exactly
`symbol|type|direction|detected_at|reference_kind`.

`features.setup_features.build_setup_inputs` adapts the existing daily-bar columns
without I/O. It consumes supplied typed Structure Engine evidence, or invokes the
existing pure Structure Engine when none is supplied. Evidence must match symbol,
session, source, session index, close, previous close and current/prior ATR exactly.
Missing structure suppresses only pullback detection. The adapter does not infer
or duplicate structural states and never modifies Structure Engine output.

`evaluate_daily_setups` composes adaptation and replay. `evaluate_reference_setups`
requires explicit `ReferenceTicker` conversion through a complete snapshot's
`CompatibilityBoundary`: exact TPC/BCPC are permitted, mixed-case TpC/BCpC are
refused without rewriting or deleting their reference identities. No crosswalk
or normalized identity join is used.

Callers provide the existing explicit source contract: vendor, dataset identity,
split-adjusted price basis, dividend treatment and matching volume convention.
No adjustment is inferred from an API flag. Corporate-action evidence is supplied
as a local `(symbol, session_date) -> (QA status, evidence)` mapping. CLEAR is an
explicit caller assertion; absent evidence is UNKNOWN. CONFIRMED_SPLIT,
FACTOR_EXPLAINED_SPLIT, SUSPECTED_SPLIT and UNKNOWN all quarantine EP evaluation.
This API does not retrieve or reconstruct corporate actions from a guessed gap.

No writer, provider client, exposure builder, UI, trade policy or order interface
is introduced. Legacy classifiers and historical records remain unchanged.
Setup invalidation is a lifecycle boundary, never a trade stop.

## Features and detection

Rows are sorted by exact market-data symbol and exchange session. Replay uses
supplied trading rows, never calendar-day resampling. At least 250 prior rows are
required. Duplicate keys, malformed session dates, infinite/invalid OHLC and
implicit reference normalization are rejected. Missing values remain null.

EMA10 and ATR14 come from the unchanged Structure Engine feature adapter. Wilder
ATR5/20 use the same TR convention and arithmetic seed followed by
`ATR[t]=((n-1)*ATR[t-1]+TR[t])/n`. Missing recursive input does not silently reseed.
Volume averages use the matching series; the EP median uses exactly T-20…T-1,
excluding the event day's volume. Six previous MA distances exclude today.
All windows below are trailing inclusive windows when calculating tomorrow's
candidate geometry. Current geometry cannot move a reference used earlier today.

EP LONG requires every condition:

```text
(Open/PreviousClose - 1) >= 0.04
(Open-PreviousClose)/ATR14[t-1] >= 1.00
(Close-PreviousClose)/ATR14[t-1] >= 1.50
Volume[t]/median(Volume[t-20:t-1]) >= 1.50
CLV >= 0.65
```

SHORT reverses the first three signs and requires CLV <= 0.35. CLV is
`(Close-Low)/(High-Low)`, or 0.5 for a zero-range bar. Close-versus-open and a new
20-session high are flags, not voters. Invalid EP candidates produce diagnostics,
not setup instances. Birth is TRIGGERED, age zero, with the event open as reference
and event low/high as controlling boundaries. The event's ATR is frozen for failure.

CONTRACTION uses `RN=(HHN-LLN)/ATR14`, for N=5/10/20:

```text
NEST:  R10 <= 0.72*R20 and R5 <= 0.78*R10
TIGHT: R20 <= 8.0 and R5 <= 3.2
ATRC:  ATR5/ATR20 <= 0.85
LOC:   Close >= LL20+0.35*(HH20-LL20)                 # LONG
       Close <= HH20-0.35*(HH20-LL20)                 # SHORT
```

The reference is HH10 for LONG or LL10 for SHORT. Pre-trigger loss of any geometry
predicate for two consecutive valid observations is STALE/GEOMETRY_CEASED.
Post-trigger evaluation does not reuse those detection predicates or the removed
impossible re-expansion rule.

TREND_PULLBACK selects the deepest qualifying reference: SMA50, then SMA20, then
EMA10. LONG EMA10/SMA20 permits EMERGING or UPTREND; LONG SMA50 requires UPTREND;
SHORT requires DECLINE. In signed LONG coordinates (reverse the price direction
for SHORT), at least one of the prior six MA distances must be >= 0.90 ATR and
today's distance must lie inclusively in the selected zone:

| Reference | Lower zone | Upper zone | Failure buffer |
| --- | ---: | ---: | ---: |
| EMA10 | -0.35 | 0.55 | 0.90 ATR |
| SMA20 | -0.45 | 0.70 | 1.10 ATR |
| SMA50 | -0.55 | 0.85 | 1.40 ATR |

LONG triggers only if yesterday was in zone, today's close is strictly above
`MA[t-1]+0.10*ATR14[t-1]`, CLV >= 0.55, and Low <= `MA[t-1]+0.20*ATR14[t-1]`.
SHORT mirrors signs, uses High for the tag and CLV <= 0.45. Same-day reclaim
cannot substitute for the frozen threshold. Each session updates the *same*
reference kind to its actual T-1 MA/ATR. A deeper qualifying reference stales an
untriggered shallower instance as REFERENCE_CHANGED and births a new instance.
Triggered pullbacks retain their original kind; they cannot become STALE.

RANGE tries N=30 first; only if it fails is a passing N=20 box selected. Upper is
the second-highest high, lower the second-lowest low. Upper <= lower is invalid.
Every test uses that trimmed box, with raw HH/LL retained only as evidence:

```text
1.8 <= (upper-lower)/ATR14 <= 7.5
(abs(C[t]-C[t-N+1])/ATR14) / max((upper-lower)/ATR14, 1e-6) <= 0.45
abs(s20) <= 0.35
at least two closes inside each outer 20% band of the trimmed box
```

Upper/lower are LONG/SHORT references. Prices beyond a trimmed box are not counted
as touches inside its outer bands. No structure label suppresses RANGE,
CONTRACTION or EP.

Mean volume5/mean volume20 <= 0.80 adds VOLUME_DRYUP; >= 1.15 adds
VOLUME_EXPANDING as a contradiction. Missing/invalid volume evidence adds
VOLUME_UNAVAILABLE for non-EP detection and omits volume-derived flags. Reclaim,
close/open, new-high and shared-pivot flags remain evidence only. Contraction and
range sharing a directional pivot within 0.15 current ATR both retain their own
instances and receive SHARED_PIVOT; neither is ranked above the other.

## Session ordering and committed geometry

For each live instance:

1. Validate required inputs and EP corporate-action QA.
2. Check failure using already committed geometry.
3. Check a trigger using the committed reference and ATR14[t-1] buffer.
4. Check the post-trigger resolution clock.
5. Check pre-trigger expiry, predicate cessation, rallied-away or reference change.
6. Only then compute/commit tomorrow's horizontal geometry.

Horizontal birth uses yesterday's qualified detection and stores
`reference_as_of_session`, reference kind/price/ATR, both controlling boundaries
and window. At birth and on subsequent sessions, today's close can trigger that
prior geometry. A current-session wick cannot move the threshold before this
check. Horizontal references refresh only while untriggered and currently
qualified. Either boundary moving > 0.75 **birth ATR** from its birth value stales
the instance as GEOMETRY_SHIFT. A replacement can be born next session, not
retroactively on the same session. Triggered horizontal geometry remains frozen.

The replay permits one live non-EP instance per family/direction, with terminal
history retained separately. Pullback selection is deepest-reference only; it
never emits three simultaneous MA pullbacks. EP events can overlap as independent
dated instances. Different families and directions coexist without priority.

Horizontal proximity enters NEAR_TRIGGER at signed distance 0…0.50 ATR. An
existing near state is retained within -0.10…0.60 ATR, then returns to FORMING.
Pullback proximity requires the selected current zone and signed distance from
the committed reference <= 0.15 ATR; a near state exits above 0.25 ATR. Hysteresis
never changes strict trigger or failure thresholds.

## Failure, expiry and terminal history

| Family | Failure | Resolution | Pre-trigger expiry |
| --- | --- | --- | --- |
| EP | close through event low/high minus/plus 0.25 event ATR | following session 5 | none |
| CONTRACTION | close through committed LL10/HH10 minus/plus 0.25 reference ATR; failed hold within first 5 following sessions | following session 8 | 25 sessions from birth; two-session geometry cessation |
| TREND_PULLBACK | close through T-1 MA buffer or incompatible structure | following session 5 | 8 observed sessions in zone; signed distance > zone upper + 0.40 ATR |
| RANGE | close through opposite boundary minus/plus 0.25 reference ATR; failed hold within first 5 following sessions | following session 8 | 40 sessions from birth |

A failed LONG breakout hold is `Close < pivot - 0.35*reference_ATR`; SHORT mirrors.
It applies on following sessions 1…5, not trigger session zero. RANGE's opposite
boundary failure also applies before trigger. CONTRACTION's pre-trigger geometry
loss is staleness rather than a post-trigger failure rule. Failure wins over a
simultaneous trigger or resolution. Trigger wins over pre-trigger expiry/rebuild.

An instance's trigger day has `sessions_since_trigger=0`. RESOLVED means all
required observation sessions completed without a setup failure, not a profitable
trade. FAILED, STALE and RESOLVED never reactivate. Their immutable daily evidence
remains on outputs through terminal+20 supplied sessions. At terminal+21, the replay
reports the archived ID and stops repeating it; earlier daily outputs retain the
full terminal object. There is no destructive archive writer.

## Missing data and replay safety

New detections with missing hard inputs or nonpositive ATR are suppressed with an
explicit family error. EP additionally requires nonnegative current/prior volumes
and a positive prior median; current volume zero fails RVOL rather than becoming
an event. Other families do not require volume. Missing structure blocks only
pullbacks. Missing source corporate-action QA never defaults to CLEAR.

For existing instances, validation distinguishes detection inputs from ongoing
failure inputs: missing event volume after an EP birth does not hide a price
failure, and loss of contraction geometry after trigger cannot suppress its
independent failure checks. An unavailable required live observation preserves
only the last observed lifecycle state, sets `replay_required=true` and
`unavailable_since`, and emits `evaluated=false`. It cannot subsequently trigger,
fail, stale or resolve from a gap in evidence; corrected-data replay is required.
This prevents falsely resolving an instance whose earlier failure was unobservable.
The daily output retains the suspended instance as history, not an evaluated
valid setup. A later independent EP event can still be detected.

Replay requires consecutive supplied session indices and a single source/basis
per symbol. Calendar gaps do not create observations. Future bars are filtered
before price/identity validation when `as_of` is supplied. The complete history
must be replayed before selecting a result; arbitrary partial replays are not
resumable instance checkpoints. No T+1 bar contributes to a T output, and the API
computes no entries, fills or risk decisions.

## Representative synthetic paths and acceptance

- EP: TRIGGERED on day zero, observation days 1–4, RESOLVED at day 5; a day-5
  invalidation instead produces FAILED.
- A range or contraction can be FORMING, become NEAR_TRIGGER, trigger against
  yesterday's pivot, and resolve at following session 8.
- Two failed contraction geometry observations produce STALE/GEOMETRY_CEASED;
  intervening valid geometry resets the counter.
- A deeper qualifying MA replaces an untriggered pullback with a new ID, while
  the old STALE instance remains visible in terminal history.
- A triggered instance with an unobservable failure session remains suspended
  even when later prices look healthy; a corrected full replay can resolve it.

Synthetic tests cover both directions, all predicate thresholds and transition
clocks, failure precedence, window/MA selection, geometry changes, overlapping
instances, exact identity conversion, median-volume timing, corporate-action
quarantine, schema round trips and future-mutation invariance. All setup tests
block socket/httpx requests. No proprietary source data is used as a fixture.
Full-suite tests retain the existing Structure Engine and legacy regression tests.
Actual production/staging/settings files are verified unchanged by SHA-256 inventory.

The separate security-master nanosecond/microsecond publication blocker remains
deferred. This milestone does not publish data, apply crosswalk proposals, build
exposure classifications or merge a PR. Empirical calibration and production
snapshot materialization remain separately scoped work.
