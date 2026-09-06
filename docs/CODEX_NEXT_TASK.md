# Codex Next Task

**Task ID:** AP-DECISION-RISK-001

**Status:** COMPLETE

**Issued:** 2026-09-06

**Base commit:** `0baffb58507d00b4cab3c245e66dda32dba03e26`

## Handoff protocol

This file is the single current assignment for VS Code Codex.

1. Read `AGENTS.md`, `docs/PROJECT_STATE.md`, and every authoritative source
   listed below before editing.
2. Implement the exact V1 hypothesis in this assignment as new opt-in contracts.
   Preserve all completed engine and legacy outputs.
3. Work autonomously unless contracts materially conflict, required data cannot
   be represented safely, or external/destructive action is required.
4. At completion, mark this task `COMPLETE`, add a concise completion record,
   update `docs/PROJECT_STATE.md`, commit, push, and open a draft PR targeting
   `codex/regime-engine-v1` so it contains only this milestone.
5. Return only the full commit SHA, focused and complete-suite test totals, PR
   link, and any genuine blocker. Keep detailed evidence in the repository.

Preserve `.vscode/settings.json`, `.env`, credentials, databases, Parquet/CSV
datasets, staged artifacts, generated reports, and unrelated user changes.

## Milestone

Implement the deterministic Decision & Risk Layer V1, composing the completed
Universe, Structure, Setup, Leadership/Group, and Market Regime engines into:

- direction-aware extension evidence;
- earnings/event eligibility evidence;
- the `WATCH -> TRADE -> ACT` decision ladder;
- transparent per-idea risk sizing.

Create and work on:

`codex/decision-risk-v1`

Base it on this handoff branch after pulling the task commit. This layer remains
decision support only. It must not place orders or select a single “best” setup.

## Authoritative sources

Read and follow:

- `AGENTS.md`
- `docs/PROJECT_STATE.md`
- `docs/aperture_product_contract.md`, especially Extension, Action ladder,
  Risk contract, and Earnings veto
- `docs/architecture_decision.md`
- `config/aperture_rules_v1.yaml` and its immutable loader
- completed Structure, Setup, Leadership, and Regime implementation contracts
- existing universe, extension, sizing, decision, and rule code/tests

Where older candidate prose is incomplete, the exact rules below freeze the new
`decision-risk-v1` experimental hypothesis. Keep every component and veto visible;
do not create or consume an opportunity score.

## Timing and alignment

A session-T decision uses only evidence available at the completed T close and is
eligible for discretionary action no earlier than T+1. Require exact symbol,
session, source, calendar, universe, engine-version, and rules-fingerprint
alignment. Reject future-effective evidence and mixed data bases.

The layer accepts caller-supplied point-in-time inputs and performs no I/O,
network access, calendar inference, event lookup, or publication.

## Direction-aware extension

For an explicitly evaluated direction:

```text
signed_extension_sma50_atr = direction_sign * (Close - SMA50) / WilderATR14
direction_sign = +1 LONG, -1 SHORT
```

Use the existing configured bands without changing them:

- below 0: `BELOW_REFERENCE`;
- 0 <= extension < 3: `ENTRY_ZONE`;
- 3 <= extension < 5: `HEALTHY`;
- 5 <= extension < 7: `EXTENDED`;
- extension >= 7: `EXTREME`;
- missing/nonfinite/nonpositive denominator: `INSUFFICIENT_DATA`.

New-entry extension eligibility is inclusive from 0 through 4.8 ATR. Store close,
SMA50, Wilder ATR14, signed extension, direction, state, band boundaries, version,
and exact reason. Preserve the existing extension functions and legacy columns;
add direction-aware V1 alongside them.

## Earnings/event evidence

Accept a typed, caller-supplied event record with:

- exact MarketDataSymbol;
- event type (`EARNINGS` for V1; schema must be extensible later);
- scheduled exchange session;
- timing (`BEFORE_OPEN`, `AFTER_CLOSE`, `DURING_SESSION`, `UNKNOWN`);
- confidence (`CONFIRMED`, `ESTIMATED`, `UNKNOWN`);
- source, source event ID, observed-at timestamp, and source-as-of timestamp;
- cancellation/replacement status and optional replacement ID.

Also require a typed caller-supplied event-calendar coverage record containing at
least the covered session range, source/as-of time, and completeness status. An
empty event list is `CLEAR` only when this coverage explicitly proves a complete,
fresh calendar through action session `T+5`. Missing, stale, incomplete, or
insufficiently ranged coverage is `UNKNOWN` and blocks `ACT`.

Compute `sessions_until_event` from the supplied exchange calendar. For a
decision at T close, an event on T after close is distance 0; an event on the next
exchange session is distance 1. A before-open or during-session event on T is
already past for the T-close decision and must not veto T+1. UNKNOWN timing on T
is conservatively treated as distance 0.

The configured five-session hard veto applies when a live CONFIRMED or ESTIMATED
earnings event has effective distance 0 through 5 inclusive. Use distinct veto
reasons for confirmed and estimated dates. An event with UNKNOWN confidence or
missing timing/date/source freshness makes earnings eligibility `UNKNOWN` and
blocks ACT with a separate reason; it is not silently treated as safe.

If multiple live events exist, evaluate all, retain all evidence, and let the
nearest effective veto win only for summary display. Do not delete farther events.
Cancelled events do not veto but remain in evidence. Replacements must be explicit;
never infer them by ticker/date proximity.

## Strength eligibility

For LONG:

```text
established_strength = RS_comp >= 60
new_rotation = RS_comp >= 40 and RS_rotation >= 80 and rotation_delta >= 15
strength_eligible = established_strength or new_rotation
```

For SHORT, V1 decision promotion is disabled by policy. Preserve SHORT setup and
extension evidence, but cap the symbol at `WATCH` with `SHORT_PROMOTION_DISABLED`.
Do not delete or relabel short evidence.

Missing required strength components produce `STRENGTH_UNKNOWN`, never zero.
Store both branches and their exact threshold results. Do not alter RS_comp or
RS_rotation.

## Group eligibility

Use the symbol's explicit point-in-time `SUB_INDUSTRY` membership only. Themes
remain display context and never substitute for the structural group gate.

A group is `NOT_LAGGING` when:

- it has a valid leadership rank and eligible-group count;
- `leadership_rank <= ceil(0.80 * eligible_group_count)`.

Otherwise classify it as `LAGGING` or `UNKNOWN` with explicit reasons. Missing or
unresolved sub-industry membership is UNKNOWN and blocks TRADE. A strong theme
cannot override a lagging/missing sub-industry in V1.

Also expose group rotation rank, rotation-rank advantage, and theme memberships
as nonvoting context.

## WATCH -> TRADE -> ACT ladder

Produce exactly one symbol/direction decision state: `NONE`, `WATCH`, `TRADE`, or
`ACT`. Also emit per-setup action evidence for every active setup instance; never
rank a primary setup.

### WATCH — all required

- current equity-trade-universe membership is eligible;
- LONG Structure state is `EMERGING` or `UPTREND`;
- strength is eligible under either branch above.

SHORT evidence may reach WATCH only when trade-universe eligible and Structure is
`DECLINE`; it cannot promote farther in V1.

### TRADE — WATCH plus all required

- confirmed Market Regime state is `GREEN` or `YELLOW` and its
  `eligible_from_session` is the decision/action session being evaluated;
- sub-industry group is NOT_LAGGING.

`RED`, `UNKNOWN`, stale, same-session-ineligible, or misaligned regime evidence
blocks TRADE with distinct reasons.

### ACT — TRADE plus all required

- at least one LONG Setup instance is `NEAR_TRIGGER` or `TRIGGERED`, evaluated,
  not replay-required, and nonterminal;
- direction-aware extension is eligible from 0 through 4.8 ATR inclusive;
- earnings eligibility is explicitly clear beyond five sessions;
- a valid nonzero per-idea size is available under the risk contract below.

`FORMING` setups remain visible but do not promote ACT. Emit every qualifying
setup ID and family. ACT means “perform discretionary review now,” not “buy.”

Evaluate every gate even after a failure so the output contains the complete
veto/reason set. The achieved state is the highest rung whose requirements all
pass. Do not let a lower-rung failure be overridden by a higher-rung input.

## Per-idea risk sizing

Accept explicit caller-proposed entry and stop prices. The Decision layer does not
choose an entry. Provide a separate default-stop helper:

```text
LONG_default_stop  = entry - 1.6 * WilderATR14
SHORT_default_stop = entry + 1.6 * WilderATR14
```

Setup invalidation levels remain separate evidence and must never silently become
trade stops.

Use account equity—not remaining buying power—as the risk base:

```text
base_risk_dollars = account_equity * 0.0025
allowed_risk = base_risk_dollars * regime_multiplier
regime_multiplier: GREEN 1.0, YELLOW 0.5, RED 0.0
stop_distance = abs(entry - stop)
risk_based_shares = floor(allowed_risk / stop_distance)
pilot_shares = floor(risk_based_shares / 3)
```

Require stop below entry for LONG and above entry for SHORT. Show stop distance in
dollars, percent, and ATR; full/pilot shares, position costs, planned dollar risk,
equity percentage at risk, and unused risk dollars.

Available buying power is a capital constraint, not the risk denominator:

```text
affordable_shares = floor(available_buying_power / entry)
capital_constrained_shares = min(risk_based_shares, affordable_shares)
```

Report both sizes and `CAPITAL_CONSTRAINED` when applicable. Never increase risk
because buying power is high or reduce the 0.25% risk base merely because capital
is already deployed.

Sizing must refuse or return explicit invalid status for nonpositive/nonfinite
equity, buying power, entry, stop, ATR, stop distance, zero shares, RED/UNKNOWN
regime, same-session-ineligible regime, and active earnings veto/unknown status.
Do not use margin or fractional shares in V1.

## Contracts and outputs

Deliver frozen, finite-or-null, extra-field-forbidding contracts for:

- extension input/evidence;
- event input and event/earnings eligibility evidence;
- strength and group gate evidence;
- per-setup action evidence;
- symbol/direction decision evidence;
- sizing input/result;
- complete daily Decision & Risk output.

Keep veto codes machine-readable and human explanations separately available.
Include formula, threshold, engine, feature, universe, source, and calendar
versions plus deterministic fingerprints.

Provide pure adapters from existing Universe, Structure, Setup, Leadership/Group,
Regime, rules, and feature contracts. Do not modify those engines or infer missing
outputs. Input objects/frames must remain unchanged.

## Verification

Add synthetic focused tests covering at minimum:

- every extension band and inclusive 4.8-ATR boundary for LONG and SHORT;
- event timing on T before open/after close/unknown and exact session distances
  0, 1, 5, and 6;
- confirmed, estimated, unknown, cancelled, replacement, multiple-event, stale-
  source, and missing-event-evidence behavior, including the rule that an empty
  event list without explicit complete coverage never becomes `CLEAR`;
- both strength branches and every equality boundary;
- group 80th-percentile boundary, ties, missing membership, invalid group ranks,
  and proof themes cannot vote;
- every WATCH, TRADE, and ACT gate independently and in combination;
- RED/UNKNOWN/same-session regime vetoes and T+1 timing;
- FORMING versus NEAR_TRIGGER/TRIGGERED setups, replay-required evidence,
  terminal instances, and multiple qualifying setup IDs without priority;
- default and explicit stops, LONG/SHORT orientation, 0.25% equity risk, Green/
  Yellow/Red multipliers, floor boundaries, pilot sizing, zero-share refusal,
  available-capital constraints, and proof buying power never changes risk base;
- complete reason accumulation rather than short-circuiting;
- point-in-time/future-mutation invariance and exact cross-engine alignment;
- frozen schemas, fingerprints, no mutation, no network, no I/O, and no production
  or staged writes;
- full regression suites for Universe, Structure, Setup, Leadership, and Regime.

Run focused tests, then:

`.venv/bin/python -m pytest`

`git diff --check`

Document formulas, state ladder, timing, veto precedence, sizing examples,
version identities, missing-data behavior, and representative synthetic paths.
Label the new policy `experimental_uncalibrated`.

## Deferred work

Do not implement portfolio-level heat/concentration limits, position management,
trade exits, journal, API, UI, ingestion, publication, or brokerage behavior.
The validated September security-master timestamp-precision publication blocker
remains outside this task.


## Completion record

AP-DECISION-RISK-001 is implemented on `codex/decision-risk-v1` from exact handoff
commit `370d5cdb79dde61854a89ace457f80edb5696a61`. The new opt-in contracts compose
unchanged engine evidence into direction-aware extension, explicit earnings
coverage, the complete WATCH/TRADE/ACT gate set and per-idea sizing. All setup
instances remain visible, SHORT promotion is capped at WATCH, and entry/stop
proposals remain caller-owned.

Observed verification: **306 focused tests** and **2,641 complete-suite tests**
passed; whitespace checks passed. All 336 protected production/staging/settings
files matched their pre-work SHA-256 inventory. No completed engine, immutable
configuration or legacy output contract changed. See
[the implementation contract](decision-risk-implementation-v1.md) for formulas,
timing, freshness attestations, veto precedence and synthetic sizing examples.
No milestone implementation blocker remains. The unrelated security-master
precision publication blocker and all listed deferred work remain outside scope.
