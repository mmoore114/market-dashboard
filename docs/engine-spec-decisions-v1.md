# Aperture engine decisions — V1

Status: **APPROVED FOR IMPLEMENTATION**. Owner authorization recorded 2026-09-05.

This document closes every item in `engine-spec-open-issues.md`. It is the
authoritative overlay for the recovered structure and setup specifications. If
older wording conflicts with this file, this file wins. Numerical changes are
intentional V1 decisions, not silent defaults. Any future semantic change must
receive a new engine or threshold version.

## Shared feature contract

- Sessions are exchange trading-session rows, sorted by symbol and session.
  Calendar gaps do not create synthetic bars and do not count toward streaks.
- Price features use one internally consistent split-adjusted OHLC basis.
  Dividend treatment must be recorded from the actual vendor dataset; do not
  label data “dividend adjusted” merely because a request used `adjusted=true`.
- Volume uses the matching vendor adjustment convention. A split adjustment may
  not be applied to price without the corresponding volume convention being
  identified in evidence metadata.
- True range is `max(H-L, abs(H-C[t-1]), abs(L-C[t-1]))`. Wilder ATR(n) uses
  the arithmetic mean of the first n true ranges, then
  `ATR[t] = ((n-1)*ATR[t-1] + TR[t])/n`.
- EMA10 uses `alpha=2/11`, seeded with the first valid close, with the recurrence
  `EMA[t]=alpha*C[t]+(1-alpha)*EMA[t-1]`. Replay must begin with at least 250
  prior sessions so initialization differences are immaterial and SMA200 context
  is available.
- A state or setup is not evaluated unless every hard-voting input for that
  family is finite and `ATR14 > 0`. Missing evidence-only volume does not block
  CONTRACTION, TREND_PULLBACK, or RANGE; it does block EP.
- Strict comparisons stay strict. Equality to an average counts as neither
  above nor below. Define `below20_15=count(C<SMA20)` and
  `below50_15=count(C<SMA50)` directly; never derive them as `15-above`.
- The session-T trigger buffer uses `ATR14[t-1]`. Failure buffers use the
  reference ATR recorded with the active geometry, except moving-average
  pullbacks, whose failure buffer uses `ATR14[t-1]` with the T-1 MA.
- Corporate-action QA must quarantine a bar before EP evaluation when the
  provider records a split effective on T or when a split-factor discontinuity
  explains the apparent gap. A suspected split is not an EP.

## Structure decisions (S1–S6)

EMA10 remains a voter. The up/down stacks are exactly
`EMA10 > SMA20 > SMA50` and `EMA10 < SMA20 < SMA50`; SMA200 remains context only.
The authoritative exit predicate is:

```text
BROKEN_UP = (not stack_up) and (LOST_20 or SMA20_FALLING or s50 < 0)
```

An UPTREND whose residual candidate would be NEUTRAL holds UPTREND. It can leave
only through a two-session `cand_DETERIORATING` or a same-day decline shock.

### Candidate streaks and initialization

`candidate_streak` is consecutive trading sessions of the same candidate. It
resets to one whenever the candidate changes and resets to zero after an
accepted transition. A blocked candidate does not accumulate across a different
candidate. Self-candidates simply hold state and do not require persistence.

The first fully eligible row is seeded `NEUTRAL`. Normal births follow
`NEUTRAL -> EMERGING -> UPTREND`; however, to make an already-trending symbol
reachable after warmup, three consecutive `cand_UPTREND` rows allow
`NEUTRAL -> UPTREND`. Three consecutive `cand_DECLINE` rows similarly allow
`NEUTRAL -> DECLINE`. These are initialization/re-entry edges, not shock flags.

### Required persistence

| From | To | Sessions |
| --- | --- | ---: |
| NEUTRAL | EMERGING | 2 |
| NEUTRAL | UPTREND | 3 |
| NEUTRAL | DECLINE | 3 |
| EMERGING | NEUTRAL | 3 |
| EMERGING | UPTREND | 3 |
| EMERGING | DETERIORATING | 2 |
| DETERIORATING | UPTREND | 2 |
| DETERIORATING | EMERGING | 2 |
| DETERIORATING | NEUTRAL | 3 |
| DETERIORATING | DECLINE | 2 |
| UPTREND | DETERIORATING | 2 |
| DECLINE | NEUTRAL | 3 |
| Any legal self-transition | same state | 0 |
| Any accepted shock override | specified below | 1 |

All other non-shock edges are forbidden. In particular UPTREND never falls
directly to NEUTRAL or EMERGING, and DECLINE never moves directly to EMERGING.

### Exact shock matrix

`SHOCK_UP = gap_atr >= 2.50` and additionally requires `C>SMA20` and `C>SMA50`.
Its target is UPTREND when `stack_up or dist50>=1.0`; otherwise EMERGING.
It is accepted from NEUTRAL, EMERGING, DETERIORATING, or DECLINE. From UPTREND it
holds UPTREND. Shock acceptance is same-day and overrides the normal edge table.

`SHOCK_DN = gap_atr <= -2.50` and additionally requires `C<SMA50`. Its target is
DECLINE when `stack_dn or dist50<=-1.0`. Otherwise its target is DETERIORATING
only from EMERGING, UPTREND, or DETERIORATING. A weak negative shock from
NEUTRAL holds NEUTRAL; from DECLINE it holds DECLINE. Accepted shocks reset the
candidate streak and set `shock_override=true`.

Boundary examples: `gap_atr=2.50` qualifies; `2.499999` does not. A close exactly
on SMA50 does not qualify for either shock branch. Two BROKEN_UP sessions move
UPTREND to DETERIORATING; one broken session followed by ALIGN_UP does not.

## Setup decisions (U1–U8)

### EP

EP uses a deliberately selective conjunction. LONG requires all of:

```text
GapPct >= 0.04
GapATR >= 1.00
ShockATR >= 1.50
Volume[t] / median(Volume[t-20:t-1]) >= 1.50
CLV >= 0.65
```

SHORT mirrors signs, uses the same positive volume ratio, and requires
`CLV <= 0.35`. `Close>Open`, `Close<Open`, and a new 20-day high/low are not
voters. They remain evidence flags. Event day is age zero. Failure is evaluated
first on each following session; absent failure, the instance becomes RESOLVED
at the close of following session five.

### Geometry, identity, and event order

Horizontal geometry is born from data through T-1 and committed for T.
`reference_as_of_session`, reference price, reference ATR, boundaries, and
window must be stored. A setup id is
`symbol|type|direction|detected_at|reference_kind`; a price hash is evidence,
not identity.

Before trigger, a horizontal reference may refresh for tomorrow. A movement of
either controlling boundary greater than 0.75 ATR from birth closes the old
instance as STALE/GEOMETRY_SHIFT and may create a new instance next session.
Moving-average pullbacks keep the same instance while the reference kind is
unchanged; each session uses the T-1 value of that MA. A deeper qualifying MA
closes the shallower instance STALE/REFERENCE_CHANGED and births a new one.

Per-session order is: validate inputs and corporate actions; evaluate failure
against committed geometry; evaluate trigger; evaluate resolution clock;
evaluate pre-trigger staleness; compute and commit tomorrow's geometry. Failure
wins over trigger or resolution on the same session. Terminal instances never
rearm; a later pattern receives a new `detected_at` and setup id.

### Lifecycle clocks

| Family | Post-trigger observation | Failure evaluated | Resolution |
| --- | ---: | --- | --- |
| EP | 5 following sessions | event invalidation, through session 5 | close of session 5 |
| CONTRACTION | 8 following sessions | close below/above committed LL10/HH10 buffer or failed breakout hold | close of session 8 |
| TREND_PULLBACK | 5 following sessions | MA failure buffer or incompatible structure | close of session 5 |
| RANGE | 8 following sessions | opposite boundary break or failed breakout hold | close of session 8 |

The trigger session is `sessions_since_trigger=0`; “following session 5” means
the fifth later trading row. STALE remains pre-trigger only.

### Contraction reachability

NEST, TIGHT, ATRC, and LOC are detection predicates. Before trigger, failure of
any hard geometry predicate for two consecutive sessions makes the instance
STALE/GEOMETRY_CEASED; it is not FAILED. Post-trigger failure is independent:
LONG fails on `Close < committed_LL10 - 0.25*reference_ATR` or, within the first
five following sessions, `Close < committed_pivot - 0.35*reference_ATR`.
SHORT mirrors. The impossible `R5 > 1.15*R10` post-trigger rule is removed.

### Compatibility

Only TREND_PULLBACK uses structure as a detection gate: LONG EMA10/SMA20 accepts
EMERGING or UPTREND, LONG SMA50 only UPTREND, and SHORT only DECLINE.
EP, CONTRACTION, and RANGE are structure-independent. The compatibility matrix
for those families is display context and may produce warnings, never suppress
an otherwise valid setup.

### Pullback timing correction

A reclaim flag on T does not by itself satisfy the trigger. LONG is TRIGGERED
when T-1 was in zone and T closes above `MA[t-1]+0.10*ATR14[t-1]`, with
`CLV>=0.55` and `Low[t]<=MA[t-1]+0.20*ATR14[t-1]`. Thus the old example with
today's `dist=-0.10` is NEAR_TRIGGER plus RECLAIM evidence, not TRIGGERED unless
the frozen T-1 threshold is also crossed.

### Range geometry

Try N=30 first; use N=20 only when N=30 fails and N=20 passes. For the selected
window, second-highest high and second-lowest low are the authoritative `upper`
and `lower`. Depth, location, touches, drift, proximity, and trigger all use this
trimmed box; raw HH/LL are evidence only. A degenerate box (`upper<=lower`) is
invalid. Minimum lookback is 20 sessions, pre-trigger expiry is 40 sessions, and
the 60-session inherited age is removed. Boundary movement greater than 0.75
ATR invokes the shared geometry rebuild rule.

### ATR and volume by family

ATR5, ATR14, and ATR20 are Wilder ATRs using the shared recurrence. Contraction's
`Vol_ratio_5_20` uses arithmetic means of the matching adjusted-volume series.
EP uniquely requires valid current and 20-prior-session volume because volume is
a hard voter. Other families may emit with missing volume and record
`VOLUME_UNAVAILABLE`; volume-derived flags are then omitted.

## Versioning and acceptance

- Implement as new structure/setup version identities; do not relabel legacy
  S1/S2/S3/S4 or older setup history.
- Required tests include every equality boundary, missing/nonpositive ATR,
  equality-to-MA counts, all legal and illegal state edges, shock matrix paths,
  trigger-reference no-look-ahead, simultaneous failure precedence, terminal
  non-reactivation, range-window precedence, ambiguous geometry, and EP's
  median-volume denominator using only T-20 through T-1.
