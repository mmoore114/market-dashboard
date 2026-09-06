# Codex Next Task

**Task ID:** AP-REGIME-001

**Status:** READY

**Issued:** 2026-09-06

**Base commit:** `9ba7bfbac17e08992dd8216426a0eef25ae70b6f`

## Handoff protocol

This file is the single current assignment for VS Code Codex.

1. Read `AGENTS.md`, `docs/PROJECT_STATE.md`, and every authoritative source
   listed below before editing.
2. Implement the exact V1 hypothesis in this assignment as a new opt-in regime
   contract. Do not reinterpret legacy regime-like research outputs.
3. Work autonomously unless contracts materially conflict, a required input
   cannot be represented safely, or external/destructive action is required.
4. At completion, mark this task `COMPLETE`, add a concise completion record,
   update `docs/PROJECT_STATE.md`, commit, push, and open a draft PR targeting
   `codex/leadership-engine-v1` so it contains only this milestone.
5. Return only the full commit SHA, focused and complete-suite test totals, PR
   link, and any genuine blocker. Keep detailed evidence in the repository.

Preserve `.vscode/settings.json`, `.env`, credentials, databases, Parquet/CSV
datasets, staged artifacts, generated reports, and unrelated user changes.

## Milestone

Implement a deterministic, point-in-time Market Regime Engine V1 with five
independently visible sleeves and an auditable `GREEN`, `YELLOW`, `RED`, or
`UNKNOWN` aggregate state.

Create and work on:

`codex/regime-engine-v1`

Base it on this handoff branch after pulling the task commit. Preserve Structure,
Setup, and Leadership/Group engines unchanged.

## Authoritative sources

Read and follow:

- `AGENTS.md`
- `docs/PROJECT_STATE.md`
- `docs/aperture_product_contract.md`, especially Market Regime
- `docs/architecture_decision.md`
- `config/aperture_rules_v1.yaml` and its immutable loader
- `docs/leadership-engine-implementation-v1.md`
- existing index, breadth, volatility, benchmark, feature, universe, and
  decision-contract code/tests

The formulas below freeze the initial `market-regime-v1` hypothesis. Keep every
component visible. Do not hide the result in a machine-learned or master score.

## Timing and input contract

Regime for session T uses only completed T data and is eligible to influence new
risk no earlier than T+1. Use an explicit exchange-session calendar; never count
weekends/holidays or synthesize missing bars.

Require typed point-in-time inputs for:

- SPY, QQQ, and IWM daily closes;
- RSP and QQQE daily closes;
- VIX close or an explicitly identified equivalent spot-volatility series;
- the T research universe and its daily close/SMA20/SMA50 values;
- optional Structure Engine and Leadership/Group evidence from the exact same
  session, universe, source basis, and version identities.

All price series must use one documented, internally consistent basis. VIX is a
market series, not a security-master equity and must retain its own identity.
Missing hard sleeve inputs produce `UNKNOWN` for that sleeve; they are never zero,
neutral, or forward-filled.

## Sleeve 1 — index structure

For each of SPY, QQQ, and IWM:

```text
CONSTRUCTIVE = Close > SMA20 > SMA50 and SMA20 > SMA20[T-5]
DEFENSIVE    = Close < SMA50 and SMA20 < SMA20[T-5]
MIXED        = otherwise
```

Strict comparisons remain strict. Sleeve state:

- `GREEN`: at least two CONSTRUCTIVE and zero DEFENSIVE;
- `RED`: at least two DEFENSIVE;
- `YELLOW`: every other fully evaluated combination;
- `UNKNOWN`: any required index feature is unavailable.

Store every index vote, moving-average value, five-session SMA20 change, and
failed predicate reason.

## Sleeve 2 — breadth

Across the exact point-in-time equity research universe, calculate:

```text
pct_above_sma20
pct_above_sma50
pct_constructive_structure
```

`pct_constructive_structure` is the fraction of valid supplied Structure Engine
states in `EMERGING` or `UPTREND`; store its separate valid denominator. Price
breadth requires at least 60% universe coverage and at least 100 valid members.
Structure breadth is evidence-only when unavailable and does not block price
breadth classification.

Price-breadth sleeve state:

- `GREEN`: pct_above_sma20 >= 0.55 and pct_above_sma50 >= 0.50;
- `RED`: pct_above_sma20 < 0.35 and pct_above_sma50 < 0.40;
- `YELLOW`: otherwise;
- `UNKNOWN`: coverage/count gate fails.

Equality is included only where the formula uses `>=`; a close exactly on an MA
counts neither above nor below.

## Sleeve 3 — leadership internals

Use the new Leadership/Group V1 evidence from T. Compute:

```text
strong_leadership_fraction = count(RS_comp >= 80) / valid_RS_comp_count
strong_rotation_fraction   = count(RS_rotation >= 80) / valid_RS_rotation_count
positive_rotation_fraction = count(rotation_delta > 0) / valid_rotation_delta_count
leading_group_fraction     = count(median_RS_comp >= 60) / valid_sub_industry_count
improving_group_fraction   = count(median_rotation_delta > 0) / valid_sub_industry_count
```

Group breadth uses rank-eligible `SUB_INDUSTRY` groups with valid medians only;
do not use overlapping themes in that denominator. Require at least 100 valid
symbols with 60% universe coverage and at least five eligible sub-industries.

Because cross-sectional percentiles make the first fraction relatively stable,
classification emphasizes rotation participation and group breadth:

- `GREEN`: strong_rotation_fraction >= 0.20,
  positive_rotation_fraction >= 0.50, leading_group_fraction >= 0.35, and
  improving_group_fraction >= 0.50;
- `RED`: strong_rotation_fraction < 0.10,
  positive_rotation_fraction < 0.35, leading_group_fraction < 0.20, and
  improving_group_fraction < 0.35;
- `YELLOW`: otherwise;
- `UNKNOWN`: any count/coverage gate fails.

Store all denominators and the strong-leadership fraction as context. Do not
blend RS_comp and RS_rotation into a new stock score.

## Sleeve 4 — volatility

Compute VIX close, SMA20, five-session percent change, and distance from SMA20.

- `GREEN`: VIX close < 20 and VIX close <= 1.05 * VIX SMA20;
- `RED`: VIX close >= 25 or VIX close >= 1.15 * VIX SMA20;
- `YELLOW`: otherwise;
- `UNKNOWN`: current VIX or full SMA20 is unavailable/nonpositive.

Apply RED precedence if a pathological input satisfies both sides. The thresholds
are hypotheses, not claims of universal optimality.

## Sleeve 5 — style and participation

Use 21-session simple price returns:

```text
SPY_R21, RSP_R21, QQQ_R21, QQQE_R21
broad_equal_weight_gap = RSP_R21 - SPY_R21
nasdaq_equal_weight_gap = QQQE_R21 - QQQ_R21
```

- `GREEN`: RSP_R21 > 0, QQQE_R21 > 0, and both gaps >= -0.03;
- `RED`: RSP_R21 <= 0, QQQE_R21 <= 0, and both gaps < -0.03;
- `YELLOW`: otherwise;
- `UNKNOWN`: any required endpoint is unavailable.

This sleeve measures participation, not whether growth or cap weighting is
morally preferable. Store all four returns and both gaps.

## Aggregate candidate and hysteresis

Map sleeve states to `GREEN=+1`, `YELLOW=0`, `RED=-1`; UNKNOWN has no score.
The normal aggregate candidate requires all five sleeves evaluated:

- `GREEN` candidate: index and breadth are GREEN, volatility is not RED, no
  sleeve is RED, and at least three sleeves are GREEN;
- `RED` candidate: index is RED and either breadth or volatility is RED, or at
  least three sleeves are RED;
- `YELLOW` candidate: every other fully evaluated combination;
- `UNKNOWN`: one or more sleeves are UNKNOWN.

State transitions:

- First fully evaluated session initializes `YELLOW`.
- `YELLOW -> GREEN` requires two consecutive GREEN candidates.
- `YELLOW -> RED` requires two consecutive RED candidates.
- `GREEN -> YELLOW` and `RED -> YELLOW` occur immediately on a YELLOW candidate.
- `GREEN -> RED` and `RED -> GREEN` are forbidden direct transitions; the first
  opposite candidate moves to YELLOW and resets the candidate streak.
- Remaining same-state candidates hold immediately.
- UNKNOWN emits no aggregate state for that session, retains the last confirmed
  state only as memory, and resets candidate continuity.

Same-day risk-off override:

```text
(at least two DEFENSIVE indexes and pct_above_sma20 < 0.30) or VIX close >= 30
```

When all inputs needed by the selected override branch are valid, it moves any
confirmed state directly to RED, sets `risk_off_override=true`, and resets the
candidate streak. It does not manufacture missing inputs for the other branch.

Expose previous state, entered date, sessions in state, candidate, candidate
streak, transition reason, sleeve counts, override flag, and all component
evidence.

## Versioning, identity, and APIs

Deliver frozen, finite-or-null, extra-field-forbidding input/evidence/output
schemas; immutable threshold policy; deterministic rule fingerprint; pure
feature calculators; and an explicit adapter from existing bar, universe,
Structure, and Leadership contracts.

Require exact session/source/universe alignment. Use explicit MarketDataSymbol
boundaries for ETFs and the versioned non-security identity for VIX. Reject
duplicate symbol/session observations, calendar inconsistencies, mixed basis,
future-effective universe evidence, and optional context from a mismatched T.

No provider client, I/O, publication, production writer, UI, actionability,
position sizing, or broker behavior belongs in this milestone.

## Verification

Add synthetic focused tests covering at minimum:

- every strict/inclusive threshold boundary in all five sleeves;
- all index-vote combinations and sleeve precedence;
- breadth coverage/count denominators and equality-to-MA handling;
- leadership/internal count gates, leading/improving sub-industry breadth,
  non-overlapping sub-industry denominators, and proof that themes cannot affect
  the internals sleeve;
- VIX 20/25/30 levels and 1.05/1.15 SMA ratios;
- style return/gap boundaries and exact 21-session endpoints;
- every aggregate candidate combination needed to prove precedence;
- initialization, all legal/forbidden transitions, interrupted streaks, UNKNOWN
  sessions, and same-day risk-off overrides;
- future mutation/no-look-ahead and T+1 eligibility semantics;
- exact identity, source, universe, and session alignment;
- frozen schema/threshold/fingerprint behavior;
- no input mutation, network access, production/staged writes, or changes to
  legacy outputs;
- complete regression coverage for Structure, Setup, and Leadership engines.

Run focused tests, then:

`.venv/bin/python -m pytest`

`git diff --check`

Document formulas, timing, thresholds, transition graph, missing-data behavior,
version identities, and representative synthetic paths. Label this V1
`experimental_uncalibrated` until later point-in-time empirical evaluation.

## Deferred work

Do not implement Watch/Trade/Act, extension integration, earnings vetoes, risk
sizing, portfolio heat, UI, ingestion, or publication. The validated September
security-master timestamp-precision publication blocker remains outside this task.
