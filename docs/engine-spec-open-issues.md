# Engine specification reconciliation

Status: **RESOLVED 2026-09-05** by explicit owner authorization to select and
freeze coherent V1 formulas. The authoritative decisions are recorded in
[engine-spec-decisions-v1.md](engine-spec-decisions-v1.md). This file remains as
the audit trail of the conflicts that were closed.

The complete recovered source specifications are preserved under `docs/reference/`.
The canonical files contain explicit, higher-priority amendments for NEUTRAL,
RESOLVED, EP's five-session resolution, and prior-day trigger references.
The recovered sources did not authorize filling gaps by intuition. The later
owner decision did authorize resolving them; no item below remains open.

## Structure decisions needed

| ID | Source evidence | Decision required |
| --- | --- | --- |
| S1 | Section C permits EMERGING→NEUTRAL and DETERIORATING→EMERGING, but D1 supplies no persistence duration for them. | Complete the transition-duration table, including self-transitions, streak resets and blocked candidates. Do not default unspecified edges to one session. |
| S2 | First eligible state is seeded NEUTRAL; non-shock NEUTRAL→UPTREND/DECLINE is forbidden. Candidate UPTREND excludes EMERGING. | Define initialization and gradual-trend reachability. An already trending stock can otherwise remain NEUTRAL indefinitely. |
| S3 | Shock logic says “at least” EMERGING/DETERIORATING, while the graph forbids some resulting edges. | Specify exact candidate and accepted state for every prior state under each shock branch; state whether any forbidden edge is overridden. |
| S4 | B4 uses BROKEN_UP, Q11 says ALIGN_UP failure for two sessions, and examples use looser wording. | Select one authoritative exit predicate and align examples. Specify what happens when the residual NEUTRAL candidate is illegal from UPTREND. |
| S5 | Full source uses EMA10 in voting; later summaries describe a 20/50 core. | Explicitly settle EMA10's voting role from the final design discussion, rather than silently dropping or retaining it as a newly approved decision. |
| S6 | PERSIST_DN = 15 minus strict-above counts, so equality counts down; warmup is approximate. | Confirm equality handling, all required feature warmups, nonpositive ATR handling, EMA seed and missing-session policy. |

## Setup decisions needed

| ID | Source evidence | Decision required |
| --- | --- | --- |
| U1 | Source EP uses GapATR≥1.20 OR ShockATR≥1.50, mean RVOL≥1.80 and Close≥Open. Another compared proposal uses a gap-percent floor AND gap/shock conditions, median RVOL and no Close≥Open requirement. | Confirm the final EP definition; adoption of RESOLVED does not establish adoption of every parameter in that proposal. |
| U2 | Contraction has an eight-session hold; pullback and range have no complete post-trigger resolution clock. | Specify resolution clocks, failure precedence and endpoint inclusivity for every non-EP family. Do not use STALE to fill missing post-trigger behavior. |
| U3 | Source contraction re-expansion includes R5>1.15×R10 although nested ranges on the same bars imply R5≤R10. Expansion is also expected at breakout. | Define reachable pre-trigger invalidation and independent post-trigger failure. |
| U4 | Frozen prior-day references are adopted; inherited geometry otherwise moves daily and setup_id uses ref_hash. | Specify birth/refresh/freeze rules, ATR buffer timestamps, stable identity, simultaneous event order, rearming, and when a changed MA/window creates a new instance. |
| U5 | Matrix excludes several contraction/range directions by structure, but prose says only pullbacks read structure. Short pullback matrix permits rare DETERIORATING while its core allows only DECLINE. | Freeze which compatibility cells are detection gates versus display-only context. |
| U6 | Pullback example says dist=-0.10 and Close above MA, then marks TRIGGERED despite required Close>MA+0.10 ATR. | Correct worked example only after precise trigger/reference timing is settled. |
| U7 | RANGE defines raw depth/drift, trimmed boundaries, top/bottom touches and both 40/60-session age limits. | Specify which box defines touches and depth; distinguish lookback, expiry and rebuild ages; define alternate-window precedence and degenerate boxes. |
| U8 | ATR(5)/ATR(20) smoothing and volume adjustment are not fully specified; generic missing-volume rejection conflicts with evidence-only volume. | Freeze shared feature definitions and missing-data requirements by family. |

## Data and migration decisions needed

- Source specs claim split/dividend-adjusted data; the repository has a vendor
  adjusted REST path and a separate unadjusted flat-file path. Verify actual
  adjustment coverage, corporate-action treatment and volume convention before
  using the source's adjustment label. Never assume `adjusted=true` proves a
  total-return or dividend adjustment policy.
- Keep all OHLC inputs on a consistent basis for ATR and range calculations.
  Establish how split-day gaps and genuine event gaps are distinguished.
- Preserve existing S1/S2/S3/S4 and legacy classifiers. New state semantics need
  a new version and recomputation, not relabeling historical records.
- Stored point-in-time snapshots alone do not establish a survivorship-free
  historical universe. Document actual historical coverage and revision policy.

## Resolution acceptance criteria

For each closed issue, record the selected rule, its source or explicit owner
decision, exact formulas and timing, and at least one boundary/path example.
Update the canonical document and remove conflicting inherited wording. Only
then change its status to implementation-ready. No unresolved issue may be
silently converted to a default in code.
