# Canonical structure-engine handoff

> Documentation handoff: 2026-09-05. Status: **IMPLEMENTATION-READY** when read with the authoritative [V1 decisions](engine-spec-decisions-v1.md), which close the conflicts recorded in [engine-spec-open-issues.md](engine-spec-open-issues.md).
> This file preserves the complete recovered design below, with the explicit amendments listed here. Amendments override conflicting inherited prose, examples, and pseudocode. Do not infer missing decisions.
> Original source: [reference/structure-state-engine-v1.md](reference/structure-state-engine-v1.md). The source's V1 label did not mean that this engine had shipped. No engine code or historical output is changed by this document.

## Confirmed amendments

- Canonical states are `NEUTRAL`, `EMERGING`, `UPTREND`, `DETERIORATING`, `DECLINE`. `BASE` is an obsolete identifier, not a second live name or a display alias.
- The arrows in conversation summaries were illustrative, not a replacement for the legal-transition table below.
- This draft does not map existing `S1/S2/S3/S4` history onto the new states. Introduce a versioned migration after semantics are resolved; retain legacy outputs.
- Missing or invalid required features must not silently become `NEUTRAL`.
- The inherited EMA10 voting, initialization, shock behavior, transition details,
  equality rules, and warmup behavior are settled in the V1 decisions document.
  That document overrides conflicting recovered prose below.

## Recovered specification with canonical naming

# Short-Horizon Swing Structure State Engine — V1 Specification

**Question the engine answers:**
What is the current structural condition of this stock from the perspective of a swing/momentum trader?

**What it does not answer:** leadership, setup type, extension, earnings risk, liquidity, or whether a trade is allowed.

Version: `structure-engine-v1.1-draft`
Horizon: daily bars, 1–6 week swing context
Bias of V1: long-side primary; down structure exists so shorts can attach later without a second engine

---

## A. State taxonomy (5 states)

| State | Job |
|---|---|
| `NEUTRAL` | No confirmed directional trend. Price is digesting. |
| `EMERGING` | Up-structure is forming but not yet confirmed. |
| `UPTREND` | Confirmed intermediate up-structure. |
| `DETERIORATING` | Previously confirmed up-structure is breaking. |
| `DECLINE` | Confirmed down-structure. |

### Why these five and not six or eight

- `EXTENDED` is not a structure state. Extension is a separate measurement layer (Design B). An extended leader is still in `UPTREND`.
- `RANGE` is not a separate state. Dead sideways names and constructive consolidations are both `NEUTRAL`. Leadership, compression, and setup engines decide whether the base is interesting.
- Mirrored `EMERGING_DOWN` / `DOWNTREND` states are unnecessary in V1. `DECLINE` is the down analog of `UPTREND`. A later short module can add `EMERGING_DOWN` if shorts become first-class. Do not double the vocabulary until that is real.
- Transitional states `EMERGING` and `DETERIORATING` stay. Inflection is the part swing traders actually use. Collapsing them into `NEUTRAL`/`UPTREND`/`DECLINE` would hide the exact window where most swing decisions happen.

### What each state means — and what it must not encode

**NEUTRAL**
Price is not in a confirmed trend. Moving averages are not stacked and persistent in one direction.
Does **not** encode: base quality, VCP, tightness grade, accumulation vs distribution, whether a breakout is near.

**EMERGING**
Short and intermediate averages are aligning up, price is holding the 50-day region, but persistence is not yet enough for `UPTREND`.
Does **not** encode: “buy now”, RS, catalyst, or that the move will succeed.

**UPTREND**
Price, 10/20/50-day structure, and 50-day slope agree. Constructive pullbacks to EMA10 or SMA20 remain `UPTREND`.
Does **not** encode: extension, pullback setup, breakout, or leadership.

**DETERIORATING**
The up-stack has broken or the 50-day has rolled over, but the stock has not yet printed confirmed down-structure.
Does **not** encode: “sell everything”, or that a breakdown setup exists.

**DECLINE**
Price and averages are stacked down with a falling 50-day.
Does **not** encode: short signal, capitulation, or oversold bounce quality.

---

## B. Developer-ready specification

### B1. Inputs (only these)

Daily OHLCV. Adjusted closes for MA/ATR math; unadjusted for event/gap research elsewhere.

| Feature | Definition | Why it exists |
|---|---|---|
| `C` | Close | Location of price |
| `EMA10` | 10-day EMA of close, α = 2/11 | Tactical swing average. EMA because 10-day must move with 3–8 day swings. |
| `SMA20` | 20-day SMA of close | One-month structure. SMA to reduce noise vs EMA20. |
| `SMA50` | 50-day SMA of close | Intermediate spine of swing structure. SMA for stability. |
| `SMA200` | 200-day SMA of close | Context only. **Not used in state predicates.** |
| `ATR14` | Wilder ATR(14) | Volatility unit for distance, slope, buffers, gaps. |
| `HH20`, `LL20` | 20-session high / low | Compression and local range. |
| `HH63` | 63-session high | Intermediate drawdown reference. |
| `above20_15` | count of last 15 closes `> SMA20` | Persistence without volume or RS. |
| `above50_15` | count of last 15 closes `> SMA50` | Persistence vs the spine. |

Rejected as state inputs: volume, RS, group rank, SMA200 slope, linear-regression slope, HH/HL sequence counters, ADR as a second vol unit, %B, MACD, ADX. See section G.

**SMA200 rule:** store it on the evidence object as context (`C > SMA200`, `SMA200` slope) so other layers can use it. Do not let it vote on short-horizon state. A stock can be `UPTREND` below the 200-day (early repair) or `DETERIORATING` above it (late breakdown).

### B2. Derived measurements

All series are as-of the current session `t`. Lookbacks use completed prior values. No future bars.

```
stack_up   = EMA10 > SMA20 AND SMA20 > SMA50
stack_dn   = EMA10 < SMA20 AND SMA20 < SMA50

pct_slope(ma, n) = 100 * (ma[t] / ma[t-n] - 1)
atr_slope(ma, n) = (ma[t] - ma[t-n]) / ATR14[t]

s20 = atr_slope(SMA20, 10)
s50 = atr_slope(SMA50, 20)

dist10 = (C - EMA10) / ATR14
dist20 = (C - SMA20) / ATR14
dist50 = (C - SMA50) / ATR14

rng20_atr = (HH20 - LL20) / ATR14
dd63_atr  = (HH63 - C) / ATR14

gap_atr   = (C - C[t-1]) / ATR14[t-1]     # signed close-to-close shock
```

**Why ATR slope, not raw percent slope**
A 2% ADR name and an 8% ADR name both “rise” when the 50-day advances a fraction of their own noise. Percent slope over-calls trend on volatile names and under-calls it on quiet names. ATR slope is the single normalization that matters for structure.

**Why percent slope is still stored**
Evidence and debugging. Not used in predicates.

**Initial slope thresholds**

```
SMA20_RISING     : s20 > +0.25
SMA20_FALLING    : s20 < -0.25
SMA50_RISING     : s50 > +0.20
SMA50_FLATISH    : abs(s50) <= 0.20
SMA50_FALLING    : s50 < -0.20
```

These are starting values, not fitted magic. Calibration process is in section 23.

### B3. Boolean condition blocks

These are reusable predicates. States are combinations of them plus previous state and persistence counters.

```
HELD_50     = C > SMA50 - 0.15 * ATR14          # buffer, not a knife-edge
LOST_50     = C < SMA50 - 0.35 * ATR14
HELD_20     = C > SMA20 - 0.20 * ATR14
LOST_20     = C < SMA20 - 0.40 * ATR14

ALIGN_UP    = stack_up AND SMA50_RISING AND HELD_50
ALIGN_DN    = stack_dn AND SMA50_FALLING AND C < SMA50 + 0.15 * ATR14

PERSIST_UP  = above20_15 >= 11 AND above50_15 >= 10
PERSIST_DN  = (15 - above20_15) >= 11 AND (15 - above50_15) >= 10

FORMING_UP  = HELD_50 AND SMA20 > SMA50 AND SMA20_RISING
              AND (s50 > 0 OR C > SMA50 + 0.50 * ATR14)
              AND above20_15 >= 8

BROKEN_UP   = (NOT stack_up) AND (LOST_20 OR SMA20_FALLING OR s50 < 0)

COMPRESSED  = rng20_atr <= 6.0                  # evidence only, not a state voter
SHOCK_UP    = gap_atr >= +2.50
SHOCK_DN    = gap_atr <= -2.50
```

Entry buffers are tighter than exit buffers (hysteresis baked into `HELD_*` vs `LOST_*`).

### B4. State predicates (candidate labels)

A candidate label is computed every day from measurements + previous state. Persistence (section D) decides whether the candidate is accepted.

```
cand_UPTREND:
    ALIGN_UP AND PERSIST_UP

cand_EMERGING:
    FORMING_UP
    AND NOT cand_UPTREND
    AND NOT cand_DECLINE

cand_DECLINE:
    ALIGN_DN AND PERSIST_DN

cand_DETERIORATING:
    previous in {UPTREND, DETERIORATING, EMERGING}
    AND BROKEN_UP
    AND NOT cand_DECLINE
    AND NOT cand_UPTREND

cand_NEUTRAL:
    NOT cand_UPTREND
    AND NOT cand_EMERGING
    AND NOT cand_DECLINE
    AND NOT cand_DETERIORATING
```

`NEUTRAL` is the residual. That is intentional. Anything that is not a forming, confirmed, weakening, or down trend is digestion.

Priority if multiple candidates fire (should be rare):

```
DECLINE > UPTREND > DETERIORATING > EMERGING > NEUTRAL
```

Shock overrides (section 13):

```
if SHOCK_UP and C > SMA50 and C > SMA20:
    candidate at least EMERGING
    if stack_up or dist50 >= 1.0: candidate = UPTREND   # persistence waived

if SHOCK_DN and C < SMA50:
    candidate at least DETERIORATING
    if stack_dn or dist50 <= -1.0: candidate = DECLINE  # persistence waived
```

Shock changes structure immediately when the move is large in that stock’s own units. The event/setup engine still owns “this was an EP.” Structure only records that the tape is no longer the previous structure.

---

## C. Transition table

Rows = from. Columns = to. `Y` = allowed. `S` = allowed only via shock override. Blank = forbidden; hold previous state and increment a `blocked_transition` counter for tests.

| from \ to        | NEUTRAL | EMERGING | UPTREND | DETERIORATING | DECLINE |
|------------------|:----:|:--------:|:-------:|:-------------:|:-------:|
| NEUTRAL             |  Y   |    Y     |    S    |       —       |    S    |
| EMERGING         |  Y   |    Y     |    Y    |       Y       |    S    |
| UPTREND          |  —   |    —     |    Y    |       Y       |    S    |
| DETERIORATING    |  Y   |    Y     |    Y    |       Y       |    Y    |
| DECLINE          |  Y   |    S     |    S    |       —       |    Y    |

Rules of the graph:

- `UPTREND` cannot go directly to `NEUTRAL`. It must pass through `DETERIORATING` unless a crash shock sends it to `DECLINE`.
- `UPTREND` cannot go to `EMERGING`. Emerging is a birth state, not a demotion.
- `NEUTRAL` cannot go to `DETERIORATING`. There is no up-structure to deteriorate.
- `DECLINE` cannot go to `DETERIORATING`. Deteriorating is defined as a damaged *up* structure.
- `NEUTRAL → UPTREND` is shock-only. Gradual births go `NEUTRAL → EMERGING → UPTREND`.
- `DECLINE → EMERGING` is shock-only (violent reversal). Normal repair is `DECLINE → NEUTRAL → EMERGING`.

This is the anti-whipsaw of last resort: even if predicates flicker, illegal edges are refused.

---

## D. Hysteresis rules

Three mechanisms, stacked. Use all three. None of them is a score.

### D1. Asymmetric session persistence

| Transition | Sessions candidate must print |
|---|---|
| NEUTRAL → EMERGING | 2 |
| EMERGING → UPTREND | 3 |
| UPTREND → DETERIORATING | 2 |
| DETERIORATING → DECLINE | 2 |
| DETERIORATING → UPTREND (reclaim) | 2 |
| DETERIORATING → NEUTRAL | 3 |
| DECLINE → NEUTRAL | 3 |
| Any shock override | 1 (same day) |

Implementation: keep `cand_streak` = consecutive sessions the same candidate has printed. Accept when `cand_streak >= required(from, to)` and the edge is legal.

### D2. ATR buffers (already in predicates)

Entering “above SMA50” uses −0.15 ATR. Leaving uses −0.35 ATR. Same idea on SMA20. Do not use raw `C > SMA50` anywhere in a live predicate.

### D3. Previous-state memory

Classification is `f(measurements, previous_state, cand_streak)`, never `f(measurements)` alone. A stock hugging SMA50 from `UPTREND` stays `UPTREND` until `BROKEN_UP` persists. The same tape arriving from `NEUTRAL` stays `NEUTRAL` or becomes `EMERGING`.

Initial values above are V1. Do not tune them per ticker.

---

## E. Evidence schema

One row per symbol per session. This is the object that must answer: “Why was this stock EMERGING on this date?”

```
{
  "symbol": "XYZ",
  "session_date": "2026-09-04",
  "bar_timestamp_utc": "2026-09-04T20:00:00Z",
  "data_vendor": "...",
  "adjustments": "split_dividend_adjusted",

  "engine_version": "structure-engine-v1.1-draft",
  "feature_version": "features-v1.0",
  "threshold_version": "thresholds-v1.0",

  "state": "UPTREND",
  "previous_state": "EMERGING",
  "state_entered_date": "2026-08-20",
  "sessions_in_state": 11,
  "previous_state_duration": 6,
  "candidate": "UPTREND",
  "candidate_streak": 11,
  "transition_today": false,
  "shock_override": false,

  "inputs": {
    "C": 84.12,
    "EMA10": 82.40,
    "SMA20": 80.95,
    "SMA50": 76.10,
    "SMA200": 64.22,
    "ATR14": 2.15,
    "HH20": 85.40,
    "LL20": 77.10,
    "HH63": 85.40
  },

  "measures": {
    "stack_up": true,
    "stack_dn": false,
    "s20": 0.62,
    "s50": 0.41,
    "pct_slope_sma20_10": 1.8,
    "pct_slope_sma50_20": 3.1,
    "dist10": 0.80,
    "dist20": 1.47,
    "dist50": 3.73,
    "rng20_atr": 3.86,
    "dd63_atr": 0.60,
    "above20_15": 13,
    "above50_15": 14,
    "gap_atr": 0.12,
    "C_gt_SMA200": true
  },

  "conditions": {
    "ALIGN_UP": true,
    "PERSIST_UP": true,
    "FORMING_UP": true,
    "BROKEN_UP": false,
    "ALIGN_DN": false,
    "HELD_50": true,
    "LOST_50": false,
    "HELD_20": true,
    "LOST_20": false,
    "SHOCK_UP": false,
    "SHOCK_DN": false
  },

  "failed_for_adjacent": ["ALIGN_DN", "BROKEN_UP"],

  "context_only": {
    "sma200_atr_slope_60": 0.55,
    "compressed": true
  }
}
```

No confidence percentage. The evidence *is* the explanation: which predicates passed, how long the state has held, and the numeric distances.

State-history fields to retain permanently: `state`, `state_entered_date`, `sessions_in_state`, `previous_state`, `previous_state_duration`. These become features for the setup and review layers later.

---

## Answers to the 24 design questions (compressed)

**1. Taxonomy** — five states above.

**2. Inputs** — C, EMA10, SMA20, SMA50, SMA200 (context), ATR14, 20-day range, 63-day high, 15-session close-vs-MA counts. Each one either locates price, measures the spine, measures persistence, or scales by volatility. Nothing else.

**3. Moving averages**
- EMA10: tactical, must respond inside a 1–2 week swing.
- SMA20: monthly structure, slower on purpose.
- SMA50: swing spine. Most state decisions hang off this average.
- SMA200: regime/context only. A short-horizon engine that requires price above the 200-day will miss early leadership and will lag breakdowns that still sit above a rising 200-day.

**4. Slope** — ATR-normalized displacement over a fixed lookback:
`atr_slope(ma, n) = (ma[t] − ma[t−n]) / ATR14[t]`
n = 10 for SMA20, n = 20 for SMA50. Simplest robust formula. No regression.

**5. Volatility normalization** — ATR units for distance, slope, buffers, and gaps. Percent thresholds are rejected for classification. ADR is redundant with ATR on daily bars for this purpose; keep ATR only.

**6. Mathematical states** — section B4.

**7. Transitions** — section C. Direct `UPTREND → DECLINE` only on shock. Violent gaps use shock overrides.

**8. Hysteresis** — section D.

**9. Transitional states** — keep `EMERGING` and `DETERIORATING`. They are the reason to have a state machine instead of a single “above/below 50-day” flag.

**10. Extension** — Design B. Structure stays `UPTREND`. A separate attribute `extension ∈ {NORMAL, ELEVATED, EXTREME}` is computed from `dist10` / `dist20` / `dist50` by another module. Mixing extension into structure forces `UPTREND → EXTENDED → UPTREND` flicker on every pullback and violates orthogonality.

**11. Constructive pullbacks** — remain `UPTREND` as long as `ALIGN_UP` has not failed for 2 sessions. Touching EMA10 or SMA20 is a setup, not a structure change. Boundary: `LOST_20` persisting, SMA20 flattening/rolling, or loss of stack. That is `DETERIORATING`.

**12. Bases** — all non-trend digestion is `NEUTRAL`, including:
- leader coiled above a rising 50-day,
- multi-month sideways with a flat 50-day,
- post-advance tight action that no longer meets `PERSIST_UP`.

A name that still satisfies `ALIGN_UP ∧ PERSIST_UP` stays `UPTREND` even if it has gone sideways for two weeks. That is correct: the structure is still an uptrend; the setup engine may label it `CONTRACTION`. Quality of the base is not this engine’s job.

**13. Gaps / EPs** — shock overrides in B4. Persistence waived only when `|gap_atr| ≥ 2.5` and price confirms on the close versus the 20/50. EP detection itself stays in the event engine.

**14. Long/short symmetry** — do not mirror the vocabulary in V1. `DECLINE` is the short-side structure state. Add `EMERGING_DOWN` later only if shorts are actually traded.

**15. Relative strength** — no. A stock can be `UPTREND` with poor RS. That is a lagging/weak trend, not “not a trend.” Leadership decides whether we care.

**16. Group strength** — no. Same reason.

**17. Interface with setups**

| Structure | Compatible setup examples |
|---|---|
| NEUTRAL | range breakout, early coil, failed breakdown reclaim |
| EMERGING | EP / catalyst gap, first pivot through SMA50 |
| UPTREND | pullback to EMA10/SMA20, continuation VCP, contraction |
| DETERIORATING | breakdown, failed breakout, distribution top |
| DECLINE | short continuation, dead-cat fade (policy later) |

Illegal pairings the workstation can warn on: `DECLINE + trend pullback`, `NEUTRAL + “in-trend pullback”`, `UPTREND + breakdown` (should already have moved).

**18–21.** Evidence schema and reproducibility fields in section E. Minimum replay kit: vendor + adjustment policy + `feature_version` + `engine_version` + `threshold_version` + the stored `inputs` block. If inputs are stored, state can be recomputed even after a logic bugfix; if only the label is stored, history is frozen but not diagnosable.

**19. Confidence** — do not emit a composite percent. Emit passed/failed predicates, streaks, and distances.

**22. Tests** — section below.

**23. Calibration** — section below.

**24. Failure modes** — section below.

---

## F. Five worked examples

Numbers are illustrative, not a backtest.

### F1. Flat name, then a real emergence

Sessions 1–30: C oscillates through SMA20 and SMA50, `s50 ≈ 0`, `above20_15 = 7`.
→ `NEUTRAL` the entire time.

Sessions 31–33: C holds above SMA50, SMA20 crosses above SMA50, `s20 > 0.25`, `above20_15` rises to 9.
→ candidate `EMERGING` for 2 days → state `EMERGING`.

Sessions 34–40: stack completes, `s50` crosses +0.20, `above20_15 = 12`.
→ candidate `UPTREND` for 3 days → state `UPTREND`.

### F2. Clean uptrend with a normal pullback

State is `UPTREND`, 18 sessions old. Price pulls back 4 days to EMA10, then SMA20. `stack_up` still true, `s50 = +0.35`, `C` never prints `LOST_20` for 2 days.
→ remains `UPTREND`. Setup engine may flag `PULLBACK`.

### F3. Extension is not a state change

Same uptrend. Price runs to `dist50 = 4.2`, `dist20 = 2.1`. Predicates for `UPTREND` still true.
→ state stays `UPTREND`. Extension module marks `EXTREME`. Policy layer can forbid new entries. Structure does not flicker.

### F4. Weakening then breakdown, plus a false breakdown

`UPTREND`. Two sessions: SMA20 lost, stack breaks, `s20 < 0`.
→ `DETERIORATING`.

Next 4 sessions: price slides, `ALIGN_DN` and `PERSIST_DN` print for 2 days.
→ `DECLINE`.

Alternate path (false breakdown): after 2 days of `DETERIORATING`, price reclaims SMA20, stack_up returns, `s50` still positive for 2 sessions.
→ back to `UPTREND`. Legal edge. Setup engine can record the shakeout.

### F5. NEUTRAL → gap +15%

Yesterday `NEUTRAL`. Today `gap_atr = +3.1`, close above SMA20 and SMA50, `dist50 = 1.4`.
→ shock override to `UPTREND` the same day.
If the gap only clears SMA50 and stack is not formed (`dist50 = 0.4`, EMA10 still below SMA20): shock override to `EMERGING`, then normal persistence into `UPTREND`.

Crash analog: `UPTREND` yesterday, `gap_atr = −3.4`, close under SMA50.
→ `DECLINE` same day. No obligatory stop in `DETERIORATING` when the shock is large.

---

## G. Deliberately excluded

| Excluded | Why |
|---|---|
| Volume / RVOL | Event and setup concern. Structure can exist on quiet tape. |
| Relative strength / RS line | Orthogonal leadership layer. |
| Group / sector rank | Orthogonal. |
| SMA200 as a voter | Wrong horizon. Context only. |
| EMA20 or SMA10 extras | Redundant with EMA10 + SMA20. |
| Linear regression slope | More moving parts, same information as ATR slope. |
| HH/HL swing count | Fragile to swing definition. Persistence counts already capture it. |
| ADX / DMI | Thresholds are regime-unstable. Persistence + slope replace it. |
| MACD, RSI, %B, Keltner | Oscillators describe location, not structure state. |
| ADR as a second scaler | ATR14 is enough on daily bars. |
| VCP / contraction grade | Setup engine. `COMPRESSED` is stored as context only. |
| Extension as a state | Breaks orthogonality. Design B. |
| Confidence score | Not reconstructable. Predicates are. |
| ML / LLM classification | Cannot answer “why this date” from stored numbers. |
| Mirrored short states | Premature. `DECLINE` is enough for V1. |

---

## H. What I would ship as V1

Ship exactly this:

1. Five states: `NEUTRAL`, `EMERGING`, `UPTREND`, `DETERIORATING`, `DECLINE`.
2. Four averages computed, three vote (EMA10, SMA20, SMA50), SMA200 stored only.
3. ATR14 as the only volatility unit.
4. ATR-slope over 10/20 sessions as the only slope definition.
5. Previous-state + 2/3-session persistence + ATR buffers + a hard transition graph.
6. Shock override at `|gap_atr| ≥ 2.5`.
7. No extension state, no RS input, no volume input, no confidence score.
8. Full evidence object persisted every symbol-day.

That is small enough to audit on a single chart, stable enough not to flip on ordinary 20-day noise, and fast enough to register a 3-day structural break.

Do not add a sixth state, a second slope method, or SMA200 voting until this version has been run on a few hundred names for a year of daily snapshots and the failure modes below have been measured, not imagined.

---

## Testing strategy

Build a fixture harness that feeds synthetic OHLCV (and a few replayed real leaders) and asserts state sequences.

| Fixture | Construction | Expected |
|---|---|---|
| Flat base | C = 50 ± 0.4 ATR noise, flat MAs, 60 days | Stay `NEUTRAL`. No EMERGING. |
| Gradual emergence | SMA50 slowly lifts, price holds above it for 8–12 days | `NEUTRAL` → `EMERGING` (≥2d) → `UPTREND` (≥3d). No skip. |
| Clean uptrend | Stacked MAs, s50 > 0.3, 40 days | Remain `UPTREND`. |
| Normal pullback | From clean uptrend, 4-day dip to SMA20, hold | Remain `UPTREND`. |
| Extended advance | dist50 climbs to 4+ | Remain `UPTREND`. |
| Weakening | Lose SMA20 for 3 days, flatten SMA20 | `UPTREND` → `DETERIORATING` on day 2 of fail. |
| Breakdown | Continue lower, stack down | `DETERIORATING` → `DECLINE`. |
| False breakdown + reclaim | 3 days under SMA20, then 3 days reclaimed stack | `DETERIORATING` then back to `UPTREND`. Never `DECLINE`. |
| EP gap | From NEUTRAL, +3 ATR gap, hold | Same-day `EMERGING` or `UPTREND` via shock. |
| Crash gap | From UPTREND, −3 ATR gap under SMA50 | Same-day `DECLINE`. |
| Noisy oscillator | C crosses SMA20/SMA50 every 2–4 days, s50 ≈ 0 | Stay `NEUTRAL`. Persistence must block flicker. |
| Illegal edge attempt | Force candidate DECLINE while state is NEUTRAL without shock | Stay `NEUTRAL`. Log blocked transition. |

Also run a universe-level stability test: on a liquid 500-name set, median state duration should be many sessions, not 1–2. If median `sessions_in_state` for `UPTREND` is under ~8 on a normal tape, hysteresis is too weak.

---

## Calibration process (anti-overfit)

1. Lock the *shape* of the rules first (which averages, ATR slope, persistence, graph). Do not hunt indicators.
2. On a cross-section of liquid names — leaders, average names, and dead names, including delisted if available — plot distributions of `s50`, `dist50`, `above20_15`, `rng20_atr`. Set initial thresholds near obvious gaps or shoulders in those distributions, not at a backtested optimum.
3. Hand-label 30–50 charts *by date* (not by eventual winner): “on this Friday, I would have called this UPTREND / NEUTRAL / …” Include failures and chop. Measure agreement and, more important, measure *flip rate*.
4. Do **not** maximize forward 10-day return by state. That sneaks a ranking model into a classifier.
5. Primary objective: transition stability + face-validity on held-out labeled days. Secondary: after the fact, check that `UPTREND` days are not dominated by names already down 20%. If they are, exit buffers are too loose.
6. Walk-forward only to confirm thresholds are not decade-specific (2017 quiet vs 2020 vol vs 2022 bear). If a threshold must move more than ~30% across decades, replace it with a more invariant unit (that is why ATR slope exists).
7. Never calibrate on a list of famous winners alone. Survivorship plus hindsight will create an engine that only recognizes NVDA after the fact.

---

## Failure modes and mitigations

| Failure | Mitigation |
|---|---|
| MA redundancy (10/20/50 saying the same thing) | They have different jobs. If EMA10 and SMA20 agree too often to matter, drop EMA10 from *predicates* but keep it in evidence. Do not add EMA21. |
| Over-sensitive flips | Persistence + buffers + illegal-edge table. Measure median state age. |
| Too slow on real breaks | Shock override at 2.5 ATR. 2-day exit from UPTREND. |
| Volatile leaders look “extended/broken” every week | ATR units. Pullbacks stay UPTREND. Extension is another layer. |
| Pullback labeled DETERIORATING | Exit requires lost stack / lost 20-day with persistence, not a touch of EMA10. |
| Dead names = constructive bases | Acceptable. RS and setup layers ignore them. Do not split RANGE in V1. |
| Hindsight / survivorship in calibration | Label dates, include losers and delistings, no return-maximizing. |
| Threshold soup | Five numeric knobs: two slopes, two persist counts, one shock size. Resist adding more. |
| SMA200 leaking in | Code review: SMA200 must not appear in any `cand_*` predicate. |
| Treating structure as permission to trade | Policy layer owns that. Evidence object must never include a “tradable” flag. |

---

## Implementation notes for the developer

- Compute features left-to-right on a date-sorted frame. Warmup: 200 sessions recommended so SMA200 context exists; state engine itself only needs ~70 sessions (SMA50 + 20-day slope + 15-day counts + ATR).
- Seed `previous_state = NEUTRAL` on first eligible day.
- Persist the full evidence JSON (or columnar equivalent) before the next bar arrives.
- Unit-test the transition graph as a pure function: `(prev, candidate, streak, shock) -> next`.
- Do not let NaNs silently become NEUTRAL. If ATR or SMA50 is missing, emit `state = null` and `error = insufficient_history`.

This is the whole V1 engine. It is intentionally smaller than Weinstein stages, smaller than a setup taxonomy, and smaller than a ranking model. That is the point.
