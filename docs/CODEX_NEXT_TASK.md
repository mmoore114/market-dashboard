# Codex Next Task

**Task ID:** AP-LEADERSHIP-001

**Status:** COMPLETE

**Issued:** 2026-09-06

**Base commit:** `3c7ebd9264675dd7d42103c75c5e609625f66a25`

## Handoff protocol

This file is the single current assignment for VS Code Codex.

1. Read `AGENTS.md`, `docs/PROJECT_STATE.md`, and every authoritative source
   listed below before editing.
2. Work through the bounded milestone autonomously. Use the exact formulas and
   boundaries in this assignment where older documents describe only candidates.
3. Ask the user only if authoritative contracts materially conflict, a required
   input cannot be represented without changing a protected data contract, or an
   external/destructive action is required.
4. At completion, mark this task `COMPLETE`, add a concise completion record,
   update `docs/PROJECT_STATE.md`, commit, push, and open a draft PR targeting
   `codex/setup-engine-v1` so the PR contains only this milestone.
5. Return only the full commit SHA, focused and complete-suite test totals, PR
   link, and any genuine blocker. Keep detailed evidence in the repository.

Preserve `.vscode/settings.json`, `.env`, credentials, databases, Parquet/CSV
datasets, staged artifacts, generated reports, and all unrelated user changes.

## Milestone

Implement deterministic Strength/Leadership and Group Ranking V1 as a pure,
point-in-time calculation layer.

Create and work on:

`codex/leadership-engine-v1`

Base it on this handoff branch after pulling the task commit. Preserve Structure
Engine V1 at `29de3ef5abffe887dcc7d42af7e93feecd370165` and Setup Engine V1 at
`3c7ebd9264675dd7d42103c75c5e609625f66a25` unchanged.

## Authoritative sources

Read and follow:

- `AGENTS.md`
- `docs/PROJECT_STATE.md`
- `docs/aperture_product_contract.md`, especially Strength and research-universe
  separation
- `docs/architecture_decision.md`, especially group aggregates, snapshot fields,
  and point-in-time processing
- `docs/data-foundation-gap-report.md`
- `docs/deepvue_audit.md`
- `docs/security-identity-boundary.md`
- `docs/structure-engine-implementation-v1.md`
- `docs/setup-engine-implementation-v1.md`
- existing feature, benchmark, ranking, taxonomy, theme, universe, and leadership
  code and tests

This milestone creates new opt-in V1 contracts. Do not overwrite or silently
reinterpret the existing 20/60/120-session SPY-relative features or legacy
`Leadership Score`.

## Layer boundaries

Keep these outputs distinct:

- raw multi-window returns;
- cross-sectional return percentiles;
- SPY excess returns already present in the repository;
- beta-adjusted residual strength versus QQQ;
- individual-stock strength evidence;
- sector, industry, sub-industry, and theme membership;
- group aggregate metrics and ordinal ranks;
- Structure Engine and Setup Engine context.

Do not implement market regime, extension permission, earnings policy,
actionability, trade entry policy, risk, sizing, portfolio heat, or an opportunity
score. Leadership may describe a stock or group; it may not declare it tradable.

## Individual strength contract

Use exchange-session rows and point-in-time research-universe membership. For
session T, compute only from bars and memberships available by T.

### Returns

Use close-to-close simple price returns on the repository's consistent
split-adjusted price basis:

```text
R5   = Close[T] / Close[T-5]   - 1
R21  = Close[T] / Close[T-21]  - 1
R63  = Close[T] / Close[T-63]  - 1
R126 = Close[T] / Close[T-126] - 1
R252 = Close[T] / Close[T-252] - 1
```

These are the V1 trading-session definitions of one week, one month, three
months, six months, and twelve months. Do not substitute calendar offsets.
Preserve the actual source/adjustment metadata in evidence.

### Cross-sectional percentiles

Rank each return independently across the point-in-time research universe on T.
Use average ranks for ties and map deterministically to 0–100:

```text
percentile = 100 * (average_rank - 1) / (valid_count - 1)
```

Lowest valid value is 0 and highest is 100. When `valid_count == 1`, emit 50.
Missing values remain null and are excluded from the denominator. Store valid
counts and universe-policy/snapshot identity for every ranked component.

### Composite RS

Implement the approved initial hypothesis as a new versioned output:

```text
RS_comp = 0.50 * percentile(R63)
        + 0.30 * percentile(R126)
        + 0.20 * percentile(R252)
```

All three components are required. Do not renormalize weights around missing
inputs. Emit explicit insufficient-data reasons.

### Short-term rotation pulse

Preserve one-week and one-month strength as an independent swing-horizon view:

```text
RS_rotation = 0.40 * percentile(R5)
            + 0.60 * percentile(R21)

rotation_delta = RS_rotation - RS_comp
```

Both short-term components are required for `RS_rotation`. Do not fold them into
`RS_comp`; the slow composite should continue to describe established leadership
while `RS_rotation` and `rotation_delta` reveal recent acceleration or
deceleration. Do not turn rotation_delta into an entry signal or an uncalibrated
categorical label. Store the raw returns, percentiles, denominators, pulse, and
delta so the UI can sort and display them transparently.

### Residual RS versus QQQ

Estimate beta using the most recent 252 close-to-close daily returns ending at T,
with at least 126 overlapping finite observations:

```text
beta_252_qqq = covariance(stock_daily_return, qqq_daily_return)
               / variance(qqq_daily_return)
residual_R63_qqq = R63_stock - beta_252_qqq * R63_QQQ
```

Use sample covariance and sample variance on the exact overlapping sessions.
If QQQ variance is zero/nonfinite, overlap is insufficient, or R63 is missing,
emit null with a specific reason. Then percentile-rank valid residuals across the
same point-in-time research universe using the exact percentile method above.
Store beta, overlap count, benchmark return, raw residual, residual percentile,
and benchmark identity. Do not winsorize, neutralize by sector, or replace QQQ
with SPY in V1.

### Evidence-only context

Include, without folding it into RS_comp:

- distance from the 63-session and 252-session closing high;
- existing 20/60/120-session return and SPY-excess fields when supplied;
- current Structure Engine state when supplied;
- active Setup Engine families/statuses when supplied.

Missing optional context must not suppress valid strength calculations.

## Group membership and aggregation

Accept explicit dated membership rows with a versioned group type:

- `SECTOR`
- `INDUSTRY`
- `SUB_INDUSTRY`
- `THEME`

Never infer a parent sector or industry from a Deepvue sub-industry label.
Deepvue currently supplies verified `SUB_INDUSTRY` and many-to-many `THEME`
snapshots; sector/industry calculations remain empty until explicit memberships
are supplied. A stock may contribute independently to every dated theme to which
it belongs.

For each `(session_date, group_type, group_id)`, emit:

- total point-in-time member count;
- valid RS_comp count and coverage fraction;
- median and 75th percentile RS_comp;
- valid RS_rotation count and coverage fraction;
- median RS_rotation and median rotation_delta;
- fraction of valid members with RS_comp >= 80;
- median residual-RS percentile and its valid count;
- fraction UPTREND and fraction UPTREND-or-EMERGING when structure is supplied;
- triggered-setup member count by family when setup evidence is supplied;
- explicit missing-context fields/reasons.

Coverage is valid RS_comp count divided by total point-in-time members. Medians
use the arithmetic midpoint for an even valid count; 75th percentiles use linear
interpolation between ordered observations. Structure fractions use only members
with valid supplied structure context and must also report that denominator.
Triggered-setup counts are integer member counts, not fractions and not instance
counts when one member has overlapping instances of the same family.

Group rank V1 is deliberately narrow and decomposable. Rank groups within the
same type and session by median RS_comp, descending, with average ordinal rank
for ties. A group is rank-eligible only when it has at least five valid RS_comp
members and at least 60% member coverage. Noneligible groups retain metrics but
receive null rank and explicit reasons. Do not create an opaque group score.

Also emit a separate `group_rotation_rank` by median RS_rotation using the same
five-valid-member and 60%-coverage gates. This is a short-horizon rotation rank,
not a replacement for the established-leadership group rank. Preserve both and
store `rotation_rank_advantage = leadership_rank - rotation_rank`, so positive
means the group is ranking better short term. Do not blend them into one score.

For supplied consecutive group snapshots, also emit:

- rank change from five sessions earlier;
- rank change from twenty sessions earlier;
- consecutive sessions in the top quintile of eligible groups;
- the exact membership snapshot/effective date used on each session.

Define rank change as `prior_rank - current_rank`, so positive means improvement.
Top quintile means average ordinal rank less than or equal to
`ceil(0.20 * eligible_group_count)`. A streak resets when the group is ineligible,
outside that boundary, or the supplied exchange-session output has a gap.

Do not forward-fill across absent trading-session outputs. A changed membership
snapshot applies only from its effective session forward; historical group
outputs retain the membership version used then.

## Identity, schemas, and reproducibility

Deliver frozen, extra-field-forbidding, finite-or-null schemas for:

- calculation source and universe provenance;
- per-symbol strength input/evidence;
- membership input;
- group evidence and rank history;
- complete daily output.

Use uppercase `MarketDataSymbol` only at the bar/feature boundary. Reference
identity conversion must remain explicit through the existing compatibility
boundary. Preserve exact source taxonomy/theme symbols and the 29-record
non-security disposition. Do not apply any of the 23 crosswalk proposals.

Version formulas and thresholds separately and include deterministic rule
fingerprints. Reject duplicate symbol/session bars, duplicate membership keys,
non-monotonic or ambiguous effective dates, mixed source bases, future-effective
memberships, and universe membership that is not valid as of the ranked session.

The pure APIs must perform no I/O, network calls, publication, or mutation of
input frames/objects. Provide adapters for existing bar, universe, taxonomy,
theme, Structure Engine, and Setup Engine contracts without changing them.

## Verification

Add focused synthetic tests covering at minimum:

- exact 5/21/63/126/252 return boundaries and insufficient history;
- point-in-time and future-mutation invariance;
- average-rank ties, singleton populations, missing-value denominators, and
  deterministic 0–100 endpoints;
- complete and missing-component RS_comp behavior;
- complete and missing-component RS_rotation behavior, rotation_delta, and proof
  that short-term inputs never change RS_comp;
- beta overlap alignment, sample covariance/variance, zero benchmark variance,
  minimum 126 observations, and QQQ residual calculation;
- cross-sectional residual percentiles without look-ahead;
- exact membership effective dating and revision/version preservation;
- many-to-many themes and no invented parent hierarchy;
- group medians, 75th percentiles, breadth fractions, coverage, and five-member/
  60%-coverage rank boundaries;
- independent group leadership and rotation ranks, including newly strong groups
  whose long-term rank remains weak;
- group tie ranks, five-/twenty-session rank changes, and top-quintile streaks;
- optional structure/setup context never changing RS values;
- exact reference versus market-data identity behavior;
- no mutation, no network access, and no production/staged writes;
- preservation of all legacy Leadership Score, Structure Engine, and Setup Engine
  tests.

Run the smallest focused tests during development, then:

`.venv/bin/python -m pytest`

`git diff --check`

Document formulas, versions, schemas, point-in-time semantics, missing-data
behavior, representative symbol/group outputs, and the explicit distinction from
legacy Leadership Score.

## Deferred work

Do not ingest new bars or memberships, publish snapshots, run universe-wide
calibration, or implement the UI in this milestone. The validated September
security-master timestamp-precision publication blocker remains deferred and is
outside this task.


## AP-LEADERSHIP-001 completion record

Completed on `codex/leadership-engine-v1` from the requested handoff commit
`28be4e88acc49610e04749f9487c1dbdc6bf3e40`. The new opt-in pure layer includes
5/21/63/126/252-session returns, independent slow RS and 5/21-session rotation,
QQQ residual percentiles, explicit dated membership adapters, independent group
ranks and gap-aware history. Frozen evidence preserves denominators, source and
universe provenance, exact identities, missing context and rule versions.

Verification: **165 focused tests passed** (49 features, 32 ranking, 36 groups,
48 adapters); **1,058 complete-suite tests passed**. `git diff --check` passed.
All 336 protected production/staging/settings files match their pre-work hashes.
Legacy Leadership Score, Structure Engine and Setup Engine source/tests remain
unchanged. The exact 29 non-security identifiers stay preserved and excluded
from security denominators; all 23 crosswalks remain unapplied.

See [the implementation contract](leadership-engine-implementation-v1.md) for
formulas, APIs, missing-data semantics, examples and reproducibility, and
[PROJECT_STATE](PROJECT_STATE.md#ap-leadership-001-completion-record) for the
complete milestone file inventory. No AP-LEADERSHIP-001 blocker remains.
The separate September master timestamp-precision publication issue is deferred.
No provider request, ingestion, publication, exposure build, calibration or
trading-policy work occurred. Draft PR target remains `codex/setup-engine-v1`;
no merge is authorized by this completion.
