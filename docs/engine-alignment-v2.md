# Structure/Setup V2 implementation contract

Assignment: `AP-ENGINE-ALIGNMENT-001`. Baseline:
`a9c81aa048bc23d9247c8e9f3c76ef3aae17d92a`.

This contract describes the explicitly selected V2 interpretation. It does not
redefine V1 or supersede the immutable source transcription. Completion results
are recorded separately in `engine-alignment-v2-receipt.md`.

## Source and precedence

The owner supplied source commit `71ef80d8637539d40ecdb7eda172db80adc50ce3`,
cherry-picked as `a463bce`. Read
[the provenance README](sources/final-word-spec/README.md) and the complete
[Word text](sources/final-word-spec/word-final-spec.txt). The companion JSON
preserves 400 paragraphs and eight tables. A test reproduces the text from those
blocks without changing a paragraph or table cell. The recorded original DOCX
SHA-256 is `3e8de86756299a91a592eb9a78431896e783e7d8500d6c1254d93f28f6567965`.
The original binary is not in this repository; its byte length/hash and extraction
verification are attestations in the owner-provided source handoff.

The later [current authority](APERTURE_CURRENT_AUTHORITY.md) controls the 60/40
lifetimes and retained Git safeguards. Historical Git numerical overlays do not
override the Word formulas. Both runtime V1 implementations remain unchanged.

## Structure V2

Versions are `structure-engine-v2`, `structure-features-v2`, and
`structure-thresholds-v2`. Frozen parameters and their rule fingerprint reside in
`src/market_dashboard/aperture/structure_v2.py`.

Use the Word D20, D50, Spread2050, median-ATR slope denominators, and P20 exactly:
Slope20 uses the ten inclusive ATR observations t-9 through t; Slope50 uses the
twenty observations t-19 through t. P20 counts strict `Close > SMA20` over ten
inclusive observations. Every E/U/H/D/L predicate, mandatory predicate, and
minimum passed-condition count is recorded with a signed threshold margin.
EMA10 and SMA200 never vote or gate eligibility. The reused V1 bar adapter also
supplies historical context fields; none of its 15-session counts vote in V2.

Source enum mapping: TRANSITION_UP/TRANSITION_DOWN become
EMERGING/DETERIORATING; TREND_UP/TREND_DOWN become UPTREND/DECLINE.
Shocks use D50, not EP's close-to-close ShockATR. They can only cause the explicit
Word immediate transitional edges. The first eligible observation initializes NEUTRAL; its qualification counters
start on the following observation. A single bar never initializes a mature state. Ordinary emergence/deterioration requires two
consecutive valid sessions, and mature entry requires three after entering the
transitional state. Mature retention loss requires five consecutive failures.

### Material source ambiguities and selected interpretations

The Word supplies predicates but not a complete executable state machine. These
choices are explicit interpretations, not quotations from that source:

- **Downside mirroring:** mirror the emerging, retention, and damage numeric
  rules by sign inversion. Mirror persistence as `1 - P20`, with decimal rounding
  of that complement to avoid floating subtraction noise. Equality with SMA20
  counts as not-above; it is not silently substituted with the old strict-below
  15-session count. The explicit Word DECLINE condition remains `P20 <= 0.40`.
- **Transition table versus symmetry:** preserve the explicit Word edge table.
  In particular DETERIORATING may recover directly to UPTREND after three
  qualifying sessions, but DECLINE must pass through EMERGING. Do not invent
  EMERGING-to-DECLINE or DETERIORATING-to-EMERGING edges to make the graph symmetric.
- **Precedence:** valid shock override first; then explicit damage/repair before
  mature retention fallback. Within EMERGING, confirmed opposite emergence wins
  before mature uptrend; within DETERIORATING, confirmed uptrend recovery wins
  before decline. Opposing mature rules cannot both qualify on the same inputs.
- **Counters:** independent predicate counters, reset on every accepted state
  transition and on unavailable input. Counters cannot inherit mature-entry credit
  from the prior state. A shock resets counters and does not establish a mature
  state. Evidence reports counters before the accepted-transition reset.
- **Transitional exits:** EMERGING returns to NEUTRAL after two consecutive days
  without emerging, uptrend, or opposite-emergence support. DETERIORATING returns
  to NEUTRAL after two days without deterioration, decline, or uptrend support.
  This avoids indefinitely retaining a transition after qualifying evidence ends.
- **Warmup and missing data:** retain 250 prior supplied sessions and the Git
  conservative Wilder ATR continuity rule. No recursive reseeding after an
  internal missing bar. Emit an unavailable state and reset confirmation counters;
  retain last confirmed state only as memory. No formula or price is imputed.

State duration, prior-state duration, last transition reason/date, and trailing
20/60-session transition counts are evidence only. The compatibility
`candidate_streak` field reports the maximum qualification counter; explicit
`qualification_counts` and `retention_failure_count` are the authoritative facts.

## Setup V2

Versions are `setup-engine-v2`, `setup-features-v2`, and `setup-thresholds-v2`.
Frozen thresholds, expiry limits and observation/failure windows reside in
`setup_v2_detection.py`. The separate replay is `setup_v2.py`.

- **CONTRACTION:** Word closing-dispersion ratios CR10/CR20 and CR5/CR10 <= .75;
  mean true-range TR5/TR20 <= .80; positive CR20. A zero CR10 cannot qualify a
  division by zero. Median volume dry-up is evidence only. References are the
  second-highest high/second-lowest low over ten sessions.
- **RANGE:** select the Word's single 20-session window. Use second extrema,
  depth <= 6 median ATR and <= 25%, efficiency <= .50, and median-ATR-normalized
  SMA20 drift <= .50. No touch-count or minimum-depth rule is imported from V1.
- **Lifetimes:** birth age is zero. Keep CONTRACTION through age 40 and RANGE
  through age 60; expire on the following session if still pre-trigger. Their
  Structure may remain NEUTRAL throughout. Meaningful geometry shift is strictly
  greater than 1 inception ATR. Formation cessation over two sessions stales an
  instance independently of age, retaining the Git cessation safeguard. This is
  applied to RANGE too so a no-longer-qualifying box cannot linger indefinitely.
- **Geometry:** discovery at T supplies an eligible birth/trigger reference no
  earlier than T+1. Current-session geometry is committed only after today's
  trigger/failure events. No current high/low can move today's trigger.
- **Post-trigger:** CONTRACTION observes five sessions, with a .50 trigger-session
  ATR failure buffer for all five; RANGE observes five, with a .25 trigger-session
  ATR buffer in the first three. Boundary price means the frozen Upper/Lower
  reference (not reference plus entry buffer). ATR is captured on the actual
  trigger session for these post-trigger buffers. Failure wins on a resolution
  date. Later observation does not extend a stated failure window.
- **Pullbacks:** only UPTREND-long and DECLINE-short qualify, including EMA10/SMA20
  references. EMERGING pullbacks remain context rather than setups. Use the prior
  five distances for the 1-ATR excursion and select the nearest qualifying MA;
  record all candidates, breaking equal-distance ties by reference enum name.
  The six-value legacy envelope is retained, but only its last five values vote.
  Apply the Word contact zone [-.50,+.25], near (.25,.75], and forming (.75,1.50].
  Evaluate contact against the prior session's MA/ATR, not today's moving MA.
  A birth can immediately enter TRIGGERED if that prior reference was contacted.
  Failure requires two consecutive closes below -.75 ATR or explicit opposing
  structural damage. NEUTRAL alone ends a pre-trigger instance as STALE; it is
  not invented as immediate post-trigger structural failure. Subsequent pullback
  checks continue using each session's committed prior MA, as in Git, rather than
  freezing a moving MA for the entire trade. Resolve on a >=1 ATR rebound; do not
  invent a fixed post-trigger timeout where the Word gives none. Pre-trigger age
  >10 or movement above 1.50 ATR stales the instance.
- **EP:** retain identical Word/Git detection thresholds and corporate-action
  quarantine. It is born TRIGGERED; event high/low failure boundaries follow the
  Word without the old extra .25 ATR offset, within five subsequent sessions.
  Five complete sessions without failure resolve it.

The Word's pre-trigger CONTRACTION failure statements are superseded by the
accepted Git cessation safeguard: predicate loss stales an instance, not an
unreachable or moving-reference price failure. RANGE follows the same cessation
handling. NEAR_TRIGGER never moves backwards to FORMING in V2. It can still
trigger, fail, or stale. Terminal instances never reactivate; reformation gets a
new birth identity. Identity is the pair `(setup engine version, setup_id)`;
the stable birth-facts ID format itself remains compatible and contains no
rolling-price hash. Missing necessary observations latch corrected-replay-required;
they cannot be silently skipped to resolve a setup.

### Provisional choices

Selected the exact Word contraction definition, 20-only RANGE, 1-ATR geometry
shift, mature-only pullbacks, and Word 5/5 observations with 5/3 failure windows.
These make a coherent source-based candidate. A bounded classification comparison
uses the first eight research symbols alphabetically and their last 126 sessions
on identical existing bars, with full-prefix warmup. It measures V1/V2 differences
and churn; it does not optimize thresholds, inspect future returns, select famous
winners, or run a parameter grid. Current 75-symbol snapshot differences are
recorded independently in the local receipt. This is not a broad calibration.

## Version wiring and snapshot preservation

Materialization validates a coherent engine-version/fingerprint pair before
dispatching both Structure and Setup. V1 remains the default. V2 requires its
explicit pair. Decision, regime context, normalized evidence, symbol detail, and
Rules carry the actual typed V2 input/output objects and rule fingerprints;
changing labels without recomputation is rejected. Downstream risk/policy versions
are unchanged and consume their new explicit evidence normally.

The normalized snapshot schema remains `workstation-snapshot-v2` (its number is
independent of engine generation). Preserve all old evidence type codes and append
new types. Accept the exact retained prototype registry fingerprint for V1-only
graphs; reject V2 evidence under that registry. Existing snapshot files remain
byte-identical, readable, and governed by their original freshness deadlines.

`python -m market_dashboard.workstation.materialization.comparison` loads explicit
baseline workspace/snapshot paths, verifies manifest hashes and publication
completion, rechecks DuckDB/Parquet agreement, and builds only new output names.
The snapshot identifies `ENGINE_VERSION_COMPARISON` with its baseline fingerprint
and Word source hash. It preserves T, E, A, population evidence and the original
expiry; generation time describes the new computation only. The Workstation
displays the comparison label. If the deadline has passed, normal live surfaces
refuse it as stale; there is no fake freshness, time override, or provider fallback.
