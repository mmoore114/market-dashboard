# Canonical setup-engine handoff

> Documentation handoff: 2026-09-05. Status: **IMPLEMENTATION-READY** when read with the authoritative [V1 decisions](engine-spec-decisions-v1.md), which close the conflicts recorded in [engine-spec-open-issues.md](engine-spec-open-issues.md).
> This file preserves the complete recovered design below, with the explicit amendments listed here. Amendments override conflicting inherited prose, examples, and pseudocode. Do not infer missing decisions.
> Original source: [reference/setup-classification-engine-v1.md](reference/setup-classification-engine-v1.md). The source's V1 label did not mean that this engine had shipped. No engine code or historical output is changed by this document.

## Confirmed amendments

- Exactly four families: `EP`, `CONTRACTION`, `TREND_PULLBACK`, `RANGE`. Multiple instances may coexist; no primary/secondary ranking. `RECLAIM` remains evidence.
- Exactly six lifecycle statuses: `FORMING`, `NEAR_TRIGGER`, `TRIGGERED`, `RESOLVED`, `FAILED`, `STALE`. `RESOLVED` means completion of observation, not a profitable trade. `STALE` is pre-trigger only. Terminal instances cannot reactivate.
- EP is born `TRIGGERED`; event age is zero. It resolves after five following trading sessions without failure, with failure evaluated before resolution on that session.
- For session T, evaluate a trigger against geometry committed by T-1. Do not include T's high/low in the reference that T must break, or rebuild that reference with T's bar before evaluating the crossing. Preserve `reference_as_of_session`, reference price, and the inputs used to construct it. Exact per-instance refresh and ATR-buffer timing remain open below.
- Frozen prior-day levels also apply to range and pullback trigger checks. Current-day measurements can be evidence and help discover tomorrow's geometry; they cannot retroactively move today's trigger.
- Numerical conflicts, including EP, geometry refresh, compatibility, feature
  definitions, and every lifecycle clock, are settled in the V1 decisions
  document. It overrides conflicting recovered proposals below.
- Do not apply pre-trigger contraction/zone predicates automatically as post-trigger failure rules: the distinction requires explicit resolution in the issues register.

## Recovered specification with confirmed amendments

# Short-Horizon Swing Setup Classification Engine — V1 Specification

**Question the engine answers:**
What recognizable, evidence-based trading structure or event is currently forming or triggering in this stock?

**What it does not answer:** structure state, leadership, regime, extension permission, earnings lockout, or whether to trade.

Version: `setup-engine-v1.1-draft`
Horizon: daily OHLCV, 1–6 week swing context
Companion: `structure-engine-v1.1-draft` (states: `NEUTRAL`, `EMERGING`, `UPTREND`, `DETERIORATING`, `DECLINE`)

The canonical non-trend structure state is `NEUTRAL`.

---

## A. Final V1 taxonomy (4 families)

| `setup_type` | Direction | Market behavior |
|---|---|---|
| `EP` | `LONG` / `SHORT` | A volatility-normalized gap/shock with participation and a decisive close. |
| `CONTRACTION` | `LONG` / `SHORT` | Multi-window range and ATR compression under a defined pivot. |
| `TREND_PULLBACK` | `LONG` / `SHORT` | Price has returned to a trend average from the trend side, trend still intact per structure. |
| `RANGE` | `LONG` / `SHORT` | Bounded, low-drift consolidation with objective upper/lower boundaries. |

No fifth family. `RECLAIM` is an event flag inside evidence, not a setup type.

### Why each exists, what it absorbs, what it must not encode

**EP**
Observable episodic expansion. Absorbs: gap-and-go, climax thrust, news gap, earnings gap as *tape*.
Does not encode: the catalyst, RS, whether to buy the close, or “EP continuation vs transition” as subtypes. Structure supplies that context.

**CONTRACTION**
Price energy is coiling. Absorbs: VCP, flag/pennant tightness, coil, NR compression. Named `CONTRACTION` on purpose — V1 does not claim textbook VCP recognition.
Does not encode: handle quality, number of textbook contractions, or “this will break out.”

**TREND_PULLBACK**
A trend that is still structurally intact has given back toward its own average. Absorbs: 10-day touch, 20-day undercut-and-hold, shallow 50-day tag. One family, `reference_ma` field.
Does not encode: buy the bounce, stop placement, or extension.

**RANGE**
A bounded box with little net drift. Absorbs: flat base, rectangle, channel-that-is-flat-enough, “horizontal consolidation.”
Does not encode: cup-and-handle, double bottom, IPO base, or base *quality* letter grades.

**Rejected as families:** reclaim, failed-breakout-as-type, opening-range breakout, hammer/engulfing, spring/shakeout-as-type. Those are evidence flags or candle language.

---

## B. Object architecture

A symbol-day may have **zero or more** active setups. No primary/secondary ranking inside this engine.

```
SetupObject {
  # identity
  symbol
  session_date
  setup_id                  # stable id: symbol|type|direction|detected_date|ref_hash
  setup_type                # EP | CONTRACTION | TREND_PULLBACK | RANGE
  direction                 # LONG | SHORT

  # lifecycle
  status                    # FORMING | NEAR_TRIGGER | TRIGGERED | RESOLVED | FAILED | STALE
  detected_at
  status_changed_at
  age_sessions
  sessions_in_status
  trigger_date              # null until TRIGGERED
  sessions_since_trigger    # null until TRIGGERED
  stale_after_sessions

  # geometry
  reference_level           # trigger / MA / range boundary, in price
  reference_kind            # PIVOT_HIGH | PIVOT_LOW | EMA10 | SMA20 | SMA50 | RANGE_HIGH | RANGE_LOW | GAP_OPEN
  distance_to_reference_atr
  invalidation_level        # price that fails the setup (not a trade stop)
  invalidation_kind

  # context (read-only, not voters except where specified)
  structure_state
  structure_engine_version

  # numbers
  measurements              # setup-specific dict
  rules_passed[]            # string ids
  rules_failed[]
  contradictions[]          # rules that failed but setup still exists
  flags[]                   # RECLAIM_SMA20, VOLUME_DRYUP, WEAK_CLOSE, ...

  # reproducibility
  engine_version
  feature_version
  threshold_version
  bar_timestamp_utc
  data_vendor
  adjustments
}
```

Universal fields: everything except `measurements` keys and some `flags`.
Setup-specific fields live only inside `measurements`.

Overlap policy: emit all valid setups. A later presentation layer may sort them. This engine does not.

---

## C. Shared measurements

Daily OHLCV. Split/dividend-adjusted for MA/ATR/range math. Volume as reported (or vendor-adjusted consistently). No future bars.

```
ATR14          = Wilder ATR(14)
ADV20          = SMA(volume, 20)
RVOL20         = volume[t] / ADV20[t-1]          # prior-window denom, no look-ahead
GapPct         = Open[t] / Close[t-1] - 1
GapATR         = (Open[t] - Close[t-1]) / ATR14[t-1]
ShockATR       = (Close[t] - Close[t-1]) / ATR14[t-1]
CLV            = 0.5 if High==Low else (Close-Low)/(High-Low)
RangeN         = HH(N) - LL(N)
RangeN_ATR     = RangeN / ATR14
RangeN_PCT     = RangeN / Close                      # stored, not used in predicates
ATR_ratio_5_20 = ATR(5) / ATR(20)
Vol_ratio_5_20 = SMA(volume,5) / SMA(volume,20)
dist(MA)       = (Close - MA) / ATR14
HHN, LLN       = max high / min low over last N sessions including today
```

RVOL for EOD V1 is `volume / ADV20` with yesterday’s ADV in the denominator. Not median, not ADV50, not dollar volume, not intraday TOD. Dollar volume and median RVOL can be stored as context later; they do not vote in V1.

---

## D. Lifecycle (shared machine)

Statuses are mutually exclusive per setup instance.

| Status | Meaning |
|---|---|
| `FORMING` | Predicates true. Price is not yet inside the proximity band of the trigger. |
| `NEAR_TRIGGER` | Predicates true and `0 ≤ signed_distance_to_trigger ≤ near_atr`. |
| `TRIGGERED` | Close crossed the trigger with the required buffer this session, or is holding beyond it within the post-trigger window. |
| `RESOLVED` | Post-trigger observation completed without invalidation. Terminal; does not assert trade profitability. |
| `FAILED` | Invalidation printed while the instance was live. Terminal. |
| `STALE` | Pre-trigger window expired or pre-trigger geometry ceased to identify the same setup. Terminal. |

Rules:

- A new instance is born `FORMING` or `NEAR_TRIGGER` or `TRIGGERED` (EP is usually born `TRIGGERED`).
- `TRIGGERED` does not expire into `FORMING` or `STALE`. It terminates as `RESOLVED` or `FAILED`.
- Resolved, failed, and stale instances are kept on the daily snapshot for history but are not “active.” Active = `{FORMING, NEAR_TRIGGER, TRIGGERED}`.
- Do not flap `FORMING ↔ NEAR_TRIGGER` on a 0.01 ATR wobble: apply a 0.10 ATR hysteresis band on the proximity edge.
- EP has no useful `FORMING` state. It is an event. Status starts at `TRIGGERED` (or is not emitted).

Shared proximity:

```
near_atr = 0.50          # configurable
trigger_buffer_atr = 0.10
fail_band hysteresis = 0.10
```

---

## E. Exact formulas and thresholds

Legend: **DEF** = hard definition of the setup. **P** = configurable initial parameter.

---

### E1. EP

Event, not a pattern. Evaluated on session `t` only. Instance lives after that as a decaying event.

**Direction**

```
if GapATR >= +gap_atr_min OR ShockATR >= +shock_atr_min: dir = LONG
if GapATR <= -gap_atr_min OR ShockATR <= -shock_atr_min: dir = SHORT
```

If both fire (pathological), take the sign of `ShockATR`.

**Core predicates (all required) — LONG**

```
DEF  MAG    : GapATR >= +1.20        P: gap_atr_min=1.20
              OR ShockATR >= +1.50   P: shock_atr_min=1.50
DEF  RVOL   : RVOL20 >= 1.80         P: rvol_min=1.80
DEF  CLOSE  : CLV >= 0.65            P: clv_min=0.65
DEF  HOLD   : Close >= Open          # long must not close under the open
```

**SHORT** mirrors signs and `CLV <= 1 - clv_min`, `Close <= Open`.

**Not required:** close above a 20-day high, prior trend, catalyst text, gap% floor. A 1% gap on a 0.6% ADR name can be an EP in ATR units; a 4% gap on a 9% ADR name may not be. That is the point of GapATR.

**Optional flags (not voters)**

```
ABOVE_HH20      : Close > HH20[t-1]
GAP_PCT_GE_4    : abs(GapPct) >= 0.04
WEAK_CLOSE      : would have passed MAG+RVOL but failed CLOSE/HOLD
NO_VOLUME       : MAG true, RVOL20 < rvol_min   # do not emit EP
```

`WEAK_CLOSE` and `NO_VOLUME` are logged as rejected-candidate evidence, not setups.

**Transition vs continuation** is not a subtype. Store `structure_state` on the object. Policy can treat `NEUTRAL/DECLINE + EP` differently from `UPTREND + EP`.

**Lifecycle**

| Status | Rule |
|---|---|
| born | `TRIGGERED` on the event day |
| `TRIGGERED` window | Event session is age 0; monitor the following five trading sessions (**P** `ep_live=5`). |
| `FAILED` LONG | Close < min(event_day Low, event_day Open) − 0.25 ATR (**P**) |
| `RESOLVED` | At the close of the fifth session after the event, if no failure occurred. Evaluate failure before resolution. |

No `FORMING` / `NEAR_TRIGGER` for EP.

**Geometry**

```
reference_level = Open[t] if abs(GapATR) >= gap_atr_min else Close[t-1]
reference_kind  = GAP_OPEN
invalidation    = event Low − 0.25 ATR   (LONG)
```

---

### E2. CONTRACTION

A coil under (long) or over (short) a pivot. Not a VCP recognizer.

**Windows (fixed)**

```
R20 = Range20_ATR
R10 = Range10_ATR
R5  = Range5_ATR
```

ATR-normalized ranges, not percent. A 6% box is tight for a 2% ADR name and loose for an 8% ADR name.

**Core predicates — LONG**

```
DEF  NEST   : R10 <= 0.72 * R20          P: k20=0.72
              AND R5  <= 0.78 * R10      P: k10=0.78
DEF  TIGHT  : R20 <= 8.0                 P: r20_max=8.0
              AND R5  <= 3.2             P: r5_max=3.2
DEF  ATRC   : ATR_ratio_5_20 <= 0.85     P: atr_c=0.85
DEF  LOC    : Close >= LL20 + 0.35 * Range20     P: loc_min=0.35
              # not sitting on the floor of the box
```

**Volume dry-up:** supporting evidence, **not required**.

```
flag VOLUME_DRYUP if Vol_ratio_5_20 <= 0.80     P
contradiction VOLUME_EXPANDING if Vol_ratio_5_20 >= 1.15
```

Quiet coils with rising volume still exist; they are just worse. Leadership/policy can downweight them. Requiring dry-up would drop many valid pre-event coils.

**Sequential legs:** not in V1. Swing-leg segmentation is a hidden pivot algorithm. Nested 5/10/20 ranges are the deterministic substitute. A later v1.1 can add `n_contractions` if a *fully specified* fractal-swing definition is frozen first.

**Pivot / trigger — LONG**

```
DEF  pivot_for_trigger_t = max(High[t-10 : t-1])  # prior 10 completed sessions
# auditable, no “since contraction began” (that needs a start detector)
NEAR     : 0 <= (pivot - Close) / ATR14 <= 0.50
TRIGGERED: Close > pivot + 0.10 * ATR14
FAILED   : Close < LL10 - 0.25 * ATR14
           OR R5 > 1.15 * R10            # re-expansion destroys the coil
           OR ATR_ratio_5_20 > 1.05
```

**SHORT** uses `pivot_for_trigger_t = min(Low[t-10:t-1])`, location near the top of the box (`Close <= HH20 - 0.35*Range20`), trigger `Close < pivot - 0.10 ATR`.

**Lifecycle**

| Status | Rule |
|---|---|
| `FORMING` | NEST ∧ TIGHT ∧ ATRC ∧ LOC, distance to pivot > 0.50 ATR |
| `NEAR_TRIGGER` | same, distance ≤ 0.50 ATR |
| `TRIGGERED` | close through pivot + buffer; remains TRIGGERED for **P** `contr_hold=8` sessions while Close stays beyond pivot − 0.15 ATR |
| `FAILED` | invalidation above |
| `STALE` | 25 sessions since `detected_at` with no trigger (**P** `contr_stale=25`), or R20 expands above `r20_max` without trigger |

**Do not require** `structure == UPTREND`. A coil can exist in `NEUTRAL` or `EMERGING`. Compatibility is recorded, not enforced as a voter except for direction sanity (see matrix).

---

### E3. TREND_PULLBACK

One family. Field `reference_ma ∈ {EMA10, SMA20, SMA50}`.

Pick the **deepest qualifying** reference this session (SMA50 beats SMA20 beats EMA10 if both qualify). Emit **one** pullback object, not three. The chosen MA is in `reference_kind`.

**Structure voter (confirmed — do not duplicate slope logic)**

```
DEF LONG  requires structure_state in {UPTREND, EMERGING}
DEF SHORT requires structure_state in {DECLINE}
```

`EMERGING` is allowed for LONG pullbacks to EMA10/SMA20 only, not SMA50 (too early).
`DETERIORATING` does **not** get a long pullback. That would relabel breakdown as setup.

If the structure engine is unavailable, refuse to emit this setup (`error=missing_structure`). Do not secretly reimplement SMA50 slope here.

**Approach-from-trend-side — LONG**

```
DEF  AWAY : max(dist(ref) over t-6..t-1) >= +0.90     P: away_min=0.90
DEF  NOW  : pullback_lo[ref] <= dist(ref) <= pullback_hi[ref]
```

This blocks names that have lived under the MA.

**Zones (asymmetric; longs allow a small undercut)**

| reference | `pullback_lo` | `pullback_hi` |
|---|---|---|
| EMA10 | −0.35 | +0.55 |
| SMA20 | −0.45 | +0.70 |
| SMA50 | −0.55 | +0.85 |

All **P**. Not symmetric: a long pullback may undercut; it must not hover 1 ATR above the MA and still count.

**SHORT** mirrors: `min(dist)` over prior 6 sessions ≤ −0.90, zone flipped.

**Core vs optional**

In the definition: structure gate, approach, current zone.
Evidence only: `VOLUME_DRYUP`, `ATR_ratio_5_20 <= 0.90`, down-day count in last 5, `CLV`, `dd_from_HH20 = (HH20-Close)/ATR14`, flag `UNDERCUT_RECLAIM` if Low < MA ≤ Close.

**Trigger**

A pullback does not need a horizontal pivot. The operational trigger is **reclaim/hold of the reference MA**.

```
NEAR_TRIGGER : in zone AND Close <= MA + 0.15 ATR     (LONG)
TRIGGERED    : in zone yesterday AND Close > MA + 0.10 ATR
               AND CLV >= 0.55
               AND (Low <= MA + 0.20 ATR)             # actually tagged/held
FAILED       : Close < MA - fail_atr[ref]
               OR structure_state moves to DETERIORATING or DECLINE
STALE        : 8 sessions in zone with no TRIGGERED    P: pb_stale=8
               OR dist(ref) > pullback_hi + 0.40       # rallied away
```

```
fail_atr: EMA10=0.90, SMA20=1.10, SMA50=1.40     P
```

That invalidation is a *setup* failure, not the user’s stop.

**Shorts in V1:** yes, the mirror is cheap and keeps the schema honest. It can stay dark in the UI until shorts are traded. Do not invent a second engine later.

---

### E4. RANGE

Bounded, low-drift box. One canonical window plus one alternate.

**Windows**

```
Primary N = 30
Alternate N = 20 if primary fails horizontalness but 20-day box passes.
Do not scan 15/40/60 in V1. Two windows. Record `window_n`.
```

Minimum duration **DEF**: 20 sessions. Maximum instance age before rebuild: 60 sessions (**P**).

**Depth (ATR, not percent)**

```
depth_atr = RangeN_ATR
DEF  depth_atr <= 7.5          P: depth_max=7.5
DEF  depth_atr >= 1.8          P: depth_min=1.8   # not a doji
```

Percent depth is stored for humans (`(HH-LL)/HH`) and does not vote.

**Horizontalness — the thing that stops “a trend looks like a range”**

```
net = Close[t] - Close[t-N+1]
drift_atr = abs(net) / ATR14
span_atr  = RangeN_ATR

DEF  LOW_DRIFT : drift_atr / max(span_atr, 1e-6) <= 0.45     P: drift_ratio=0.45
DEF  FLAT_SPINE: abs(atr_slope(SMA20, 10)) <= 0.35            P
DEF  TOUCHES   : at least 2 closes in the top 20% of the box
                 AND 2 closes in the bottom 20% of the box over the N days
```

`TOUCHES` is what makes it a *range* rather than a one-sided drift that never tested support.

**Boundaries — trimmed extrema, not raw HH/LL**

```
# drop the single most extreme high and low inside the window
highs = sort(High[t-N+1 : t])
lows  = sort(Low[t-N+1 : t])
upper = highs[-2]          # second-highest high
lower = lows[1]            # second-lowest low
```

One anomalous wick cannot own the pivot. Still fully deterministic. No percentiles-of-closes in V1 (that hides the level). Store raw HH/LL as well for audit.

**Location / trigger — LONG**

```
NEAR     : 0 <= (upper - Close) / ATR14 <= 0.50
TRIGGERED: Close > upper + 0.10 * ATR14
FAILED   : Close < lower - 0.25 * ATR14          # breakdown of the same box
           OR after TRIGGERED, Close back < upper - 0.35 ATR within 5 sessions
              → status FAILED (failed breakout of this instance)
STALE    : 40 sessions since detected with no trigger  P
           OR upper/lower both move more than 0.75 ATR from birth levels
              (geometry changed → close instance, maybe birth a new one)
```

**SHORT / breakdown** is the same family: `direction=SHORT`, trigger `Close < lower - 0.10 ATR`.

**Not required:** volume on the break. Store `RVOL20` as evidence. Policy may demand it.

---

### E5. RECLAIM — flag, not family

```
flag RECLAIM_SMA20 if Close[t-1] < SMA20[t-1] AND Close[t] > SMA20[t] AND Low[t] <= SMA20[t] AND CLV >= 0.60
flag RECLAIM_SMA50 analogous
flag RECLAIM_EMA10 analogous
```

Attach these flags to `TREND_PULLBACK`, `CONTRACTION`, `RANGE`, and `EP` when they fire. Do not birth a fifth setup. A reclaim without a pullback/range/contraction/EP is just a moving-average cross — structure already sees that.

---

## F. Compatibility matrix

Setup detection does **not** redefine structure.
`✓` = valid to emit. `rare` = allowed but usually empty. `—` = do not emit (direction/structure contradiction).

| setup \ structure | NEUTRAL | EMERGING | UPTREND | DETERIORATING | DECLINE |
|---|:---:|:---:|:---:|:---:|:---:|
| EP LONG | ✓ | ✓ | ✓ | ✓ | ✓ |
| EP SHORT | ✓ | ✓ | ✓ | ✓ | ✓ |
| CONTRACTION LONG | ✓ | ✓ | ✓ | rare | — |
| CONTRACTION SHORT | rare | — | — | ✓ | ✓ |
| TREND_PULLBACK LONG EMA10/SMA20 | — | ✓ | ✓ | — | — |
| TREND_PULLBACK LONG SMA50 | — | — | ✓ | — | — |
| TREND_PULLBACK SHORT | — | — | — | rare | ✓ |
| RANGE LONG | ✓ | ✓ | ✓ | rare | — |
| RANGE SHORT | ✓ | rare | — | ✓ | ✓ |

EP is structure-agnostic because it is an event.
Long pullbacks require intact-or-forming up structure. That is the one hard coupling, and it reads the structure engine instead of copying its math.

Leadership, extension, regime, earnings: **ignored**. A low-RS, extremely extended, red-regime, earnings-tomorrow breakout is still `RANGE / TRIGGERED` or `CONTRACTION / TRIGGERED`. Policy disqualifies it.

---

## G. Overlap, priority, age

**Multiple setups:** allowed. Typical legal stacks:

- `UPTREND + CONTRACTION + NEAR_TRIGGER`
- `UPTREND + TREND_PULLBACK(SMA20)`
- `EMERGING + EP LONG + TRIGGERED`
- `NEUTRAL + RANGE + NEAR_TRIGGER`
- `DETERIORATING + RANGE SHORT` (breakdown)
- `UPTREND + CONTRACTION + RANGE` — possible when a 30-day box is also a nested coil

**Redundancy rule (only one):** if `CONTRACTION` and `RANGE` share the same trigger level within 0.15 ATR and same direction, keep both objects but set `flags += SHARED_PIVOT` so the UI can collapse them. Do not delete either. They answer different questions (coil vs box).

**No setup priority.** EP is not “higher” than CONTRACTION. Actionability ranks. This layer does not.

**Age fields (minimum history)**

Per instance, persist a small transition log:

```
transitions[] = [{ts, from_status, to_status, reason}]
```

Reasons are closed-vocab: `BORN`, `PROXIMITY`, `LEFT_PROXIMITY`, `CROSSED_TRIGGER`, `INVALIDATED`, `EXPIRED`, `GEOMETRY_SHIFT`, `STRUCTURE_BROKE`.

Keep the instance row daily until 20 sessions after terminal status, then archive.

---

## H. Evidence schema (one instance)

```
{
  "symbol": "XYZ",
  "session_date": "2026-09-04",
  "bar_timestamp_utc": "2026-09-04T20:00:00Z",
  "setup_id": "XYZ|CONTRACTION|LONG|2026-08-21|p:84.50",
  "setup_type": "CONTRACTION",
  "direction": "LONG",
  "status": "NEAR_TRIGGER",
  "detected_at": "2026-08-21",
  "status_changed_at": "2026-09-02",
  "age_sessions": 10,
  "sessions_in_status": 3,
  "trigger_date": null,
  "sessions_since_trigger": null,
  "stale_after_sessions": 25,

  "reference_level": 84.50,
  "reference_kind": "PIVOT_HIGH",
  "distance_to_reference_atr": 0.28,
  "invalidation_level": 79.10,
  "invalidation_kind": "LL10_BREAK",

  "structure_state": "UPTREND",
  "structure_engine_version": "structure-engine-v1.1-draft",

  "measurements": {
    "R5": 2.1, "R10": 2.9, "R20": 4.6,
    "ATR_ratio_5_20": 0.66,
    "Vol_ratio_5_20": 0.74,
    "RVOL20": 0.81,
    "CLV": 0.71,
    "pivot": 84.50,
    "HH10": 84.50,
    "LL10": 79.90
  },

  "rules_passed": ["NEST", "TIGHT", "ATRC", "LOC", "NEAR"],
  "rules_failed": [],
  "contradictions": [],
  "flags": ["VOLUME_DRYUP"],

  "transitions": [
    {"ts": "2026-08-21", "from": null, "to": "FORMING", "reason": "BORN"},
    {"ts": "2026-09-02", "from": "FORMING", "to": "NEAR_TRIGGER", "reason": "PROXIMITY"}
  ],

  "engine_version": "setup-engine-v1.1-draft",
  "feature_version": "setup-features-v1.0",
  "threshold_version": "setup-thresholds-v1.0",
  "data_vendor": "...",
  "adjustments": "split_dividend_adjusted"
}
```

No `confidence` field. Margins live in `measurements` and `distance_to_reference_atr`.

---

## I. Worked examples

### EP-1 — valid long EP from NEUTRAL

Yesterday close 40.00, ATR14=1.00. Today open 42.20 (GapATR=+2.20), high 43.10, low 41.90, close 42.85, RVOL20=2.4, CLV=0.79, Close>Open. Structure=`NEUTRAL`.
→ emit `EP / LONG / TRIGGERED`. Flags: `ABOVE_HH20` if true. Not a subtype “transition EP.”

### EP-2 — huge gap, weak close — no setup

Open 42.20, high 42.40, low 39.80, close 40.10, RVOL20=3.1, CLV=0.12, Close<Open.
→ no EP. Store rejected-candidate `{MAG:pass, RVOL:pass, CLOSE:fail, HOLD:fail}` if you want a research tape. Setup list stays empty.

### CONTRACTION-1 — shrinking ranges into a pivot

R20=5.0, R10=3.2, R5=2.2, ATR_ratio=0.62, Vol_ratio=0.70, Close 0.30 ATR under HH10. Structure=`UPTREND`.
→ `CONTRACTION / LONG / NEAR_TRIGGER`. Flag `VOLUME_DRYUP`.

### CONTRACTION-2 — one-day tightness only

R5 collapses because of a single inside day, R10≈R20, ATR_ratio=0.98.
→ no setup. `NEST` fails.

### TREND_PULLBACK-1 — healthy SMA20 tag

Structure=`UPTREND`. Five days ago dist(SMA20)=+1.6. Today dist=−0.10, Low undercuts SMA20, Close back above, CLV=0.68.
→ `TREND_PULLBACK / LONG / TRIGGERED`, `reference_kind=SMA20`, flag `RECLAIM_SMA20` + `UNDERCUT_RECLAIM`.

### TREND_PULLBACK-2 — lived under the MA

Structure=`UPTREND` (borderline). dist(SMA20) has been −0.4 to −1.2 for 15 days. Today dist=−0.20.
→ no setup. `AWAY` fails. This is not a pullback.

### RANGE-1 — 30-day box

N=30, depth_atr=4.1, drift_ratio=0.22, SMA20 slope flat, 3 tops and 3 bottoms tested. Second-highest high=91.20. Close=90.70 (0.23 ATR below).
→ `RANGE / LONG / NEAR_TRIGGER`, `reference_level=91.20`.

### RANGE-2 — trend masquerading as a range

N=30, depth_atr=6.8, but net drift = 5.1 ATR, drift_ratio=0.75, SMA20 rising hard, only upper-half closes.
→ no RANGE. `LOW_DRIFT` and `TOUCHES` fail.

---

## J. Synthetic test plan

Each fixture is a hand-built OHLCV path. Assert emitted objects.

### EP

| Fixture | Expect |
|---|---|
| GapATR=+1.5, RVOL=2.0, CLV=0.8, Close≥Open | `EP LONG TRIGGERED` |
| GapATR=+0.9, ShockATR=+0.8, rest fine | no EP (below MAG) |
| GapATR=+2.0, RVOL=1.1, good close | no EP; rejected `NO_VOLUME` |
| GapATR=+2.0, RVOL=2.5, CLV=0.2 | no EP; rejected `WEAK_CLOSE` |
| GapATR=−1.8, RVOL=2.2, CLV=0.2, Close≤Open | `EP SHORT TRIGGERED` |
| MAG at threshold−ε | no EP |
| MAG at threshold+ε, others pass | EP |

### CONTRACTION

| Fixture | Expect |
|---|---|
| R20>R10>R5 nested, ATRC pass, near HH10 | `NEAR_TRIGGER` |
| Nested but Vol_ratio=1.25 | still emit; contradiction `VOLUME_EXPANDING` |
| Only today is tight | no setup |
| Nested, then R5 explodes | `FAILED` (re-expansion) |
| Nested 8 days, then Close > HH10+0.10ATR | `TRIGGERED` |
| Passes NEST but R20=12 ATR | no setup (`TIGHT`) |

### TREND_PULLBACK

| Fixture | Expect |
|---|---|
| UPTREND, tag EMA10 from +1.2 ATR | pullback EMA10 |
| UPTREND, tag SMA20 from +1.5 ATR | pullback SMA20 (deeper wins if both in zone) |
| UPTREND, tag SMA50 from +2 ATR | pullback SMA50 |
| UPTREND, under SMA20 for 20 days | no setup |
| Was pullback, structure → DETERIORATING | `FAILED` reason `STRUCTURE_BROKE` |
| In zone 9 days, never reclaims | `STALE` |
| DECLINE, rally to falling SMA20 | `TREND_PULLBACK SHORT` |

### RANGE

| Fixture | Expect |
|---|---|
| 30d box, low drift, both sides tested | `RANGE FORMING` or `NEAR` |
| 30d up-channel, high drift | no RANGE |
| Raw HH is a one-tick spike; second-high is the real cap | trigger uses second-high |
| Close > upper+0.10ATR | `TRIGGERED` |
| Trigger then close back through upper−0.35ATR in 3 days | `FAILED` |
| Close < lower−0.10ATR | `RANGE SHORT TRIGGERED` |

Also: lifecycle hysteresis around the 0.50 ATR proximity line; instance id stability when the same coil persists; no look-ahead (ADV20 and ATR use `t-1` where specified).

---

## K. Calibration

Lock semantics first. Then set **P** values from distributions, not from 10-day forward returns.

1. Point-in-time liquid universe, several years, including 2018, 2020, 2022.
2. Plot GapATR, RVOL20, R10/R20, ATR_ratio_5_20, dist(SMA20) conditional on structure=`UPTREND`, drift_ratio of 30-day windows.
3. Put initial knobs near visible shoulders (e.g. RVOL 1.8 is “unusual,” not “maximum edge”).
4. Hand-label 40–60 *dates* (not eventual winners): “this day is / is not a coil / pullback / box / EP.” Measure false positives on chop and missed obvious events.
5. Walk-forward the same knobs across vol regimes. If a knob must move >30%, the unit is wrong — switch that knob to ATR.
6. **Forward returns are diagnostic only after definitions freeze.** If `TRIGGERED` coils have poor average returns, that is a policy/leadership problem until proven that the *geometry* is mis-specified. Do not climb a return hill by tightening RVOL until the setup becomes a stealth ranking model.

---

## L. Failure modes

| Risk | Mitigation |
|---|---|
| Pretend-VCP / swing-leg fragility | Nested 5/10/20 ATR ranges only. No fractal pivots. |
| Every quiet week is a contraction | `TIGHT` caps + ATRC + location off the floor. |
| Pullback on a broken name | Structure gate; `AWAY` from above; fail on structure change. |
| Trend labeled as range | `LOW_DRIFT` + `FLAT_SPINE` + two-sided `TOUCHES`. |
| Wick-owned pivots | Second-highest / second-lowest in RANGE; HH10 for contraction. |
| Gap% fails across ADR | GapATR / ShockATR vote; gap% is a flag. |
| Setup pile-up | Allow multiples; only collapse in UI via `SHARED_PIVOT`. |
| Lifecycle flicker | 0.10 ATR hysteresis on proximity; terminal states stay terminal. |
| Stale pile | Explicit stale clocks per family; archive 20 sessions after terminal. |
| Volume holes / halt days | If volume or ATR missing, emit nothing (`insufficient_data`). |
| Hidden scoring | No composite. Failed rules become contradictions, not a 0–100 score. |
| Setup engine reimplements structure | Pullback is the only structure reader; it consumes the state label. |

---

## M. Deliberately excluded

| Excluded | Why |
|---|---|
| Fifth family `RECLAIM` | MA cross + hold is a flag. Structure already tracks the cross. |
| VCP leg counter | Hidden swing algorithm. Nested windows replace it. |
| Cup-and-handle / double bottom / IPO base | Named chart art. RANGE + CONTRACTION cover the measurable part. |
| Failed-breakout as its own type | It is `RANGE` or `CONTRACTION` → `FAILED`. |
| Intraday TOD RVOL | EOD V1. Add later in an intraday engine. |
| Dollar-volume RVOL as voter | Useful for tradability, wrong layer. |
| Close-through-HH20 required for EP | Many valid EPs start inside a range. Store as flag. |
| Setup confidence % | Not calibrated. Predicates + margins instead. |
| Setup ranking EP > others | Policy’s job. |
| Earnings date as a setup voter | Policy lockout. |
| RS, group, regime, extension as voters | Orthogonal layers. |
| Trade stop = setup invalidation | Different objects. Invalidation kills the *setup instance*. |
| LLM pattern naming | Not reproducible. |

---

## N. What I would ship as V1

Four families: `EP`, `CONTRACTION`, `TREND_PULLBACK`, `RANGE`.
Each with `direction`, a six-state lifecycle, ATR-normalized geometry, and a persisted evidence object.

Hard couplings to other layers: only `TREND_PULLBACK` reads `structure_state`. Everything else can exist even when policy will refuse the trade.

Reclaim, volume dry-up, weak-close, shared-pivot, and “close above HH20” are flags.

No confidence score, no setup ranking, no VCP-leg parser, no SMA200, no earnings, no RS.

If a later version adds anything, add `EMERGING_DOWN` support on the structure side first, then turn the already-built short mirrors on in the UI — do not invent new setup names.

That is the whole V1 setup engine. It records what is on the tape. It does not decide whether to care.
