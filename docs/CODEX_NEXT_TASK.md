# Codex Next Task

**Task ID:** AP-STRUCTURE-001  
**Status:** COMPLETE\
**Issued:** 2026-09-06  
**Base commit:** `f2a16e311682e974dd1243f4f7733378dbe8aaa1`

## Handoff protocol

This file is the single current assignment for VS Code Codex.

1. Read `AGENTS.md`, `docs/PROJECT_STATE.md`, and every authoritative contract referenced below before editing.
2. On this first task, update `AGENTS.md` so future Codex sessions always read `docs/CODEX_NEXT_TASK.md` immediately after `docs/PROJECT_STATE.md`.
3. Work through the entire bounded milestone autonomously. Do not stop for routine implementation choices already settled by repository contracts.
4. Ask the user only when authoritative contracts materially conflict, a required rule is genuinely absent, or an external/destructive action would be required.
5. At completion, change this task's status to `COMPLETE`, add a concise completion record, update `docs/PROJECT_STATE.md`, commit, and push the milestone branch.
6. The user-facing completion response should be short: full commit SHA, test totals, and any genuine blocker. Detailed evidence belongs in the repository.

Preserve `.vscode/settings.json`, `.env`, credentials, databases, Parquet/CSV datasets, staged artifacts, generated reports, and all unrelated user changes.

## Milestone

Implement the complete deterministic Aperture Structure Engine V1.

Create and work on:

`codex/structure-engine-v1`

Base it on the current handoff branch after pulling this task-file commit.

## Authoritative sources

Read and follow:

- `AGENTS.md`
- `docs/PROJECT_STATE.md`
- `docs/aperture_product_contract.md`
- `docs/architecture_decision.md`
- `docs/structure-state-engine-v1.md`
- `docs/setup-classification-engine-v1.md` only to preserve the structure/setup boundary
- `docs/engine-spec-decisions-v1.md`
- `docs/engine-spec-open-issues.md`

The decision overlay supersedes older candidates and archived sources. Do not reconstruct rules from chat history or redesign settled formulas.

## Required terminology

The only Structure Engine V1 states are:

- `NEUTRAL`
- `EMERGING`
- `UPTREND`
- `DETERIORATING`
- `DECLINE`

`BASE` is obsolete. Do not introduce, restore, or emit it.

## Implementation scope

Deliver:

- pure production calculation logic;
- explicit, versioned input and output schemas;
- deterministic state classification;
- documented hysteresis and transition behavior;
- insufficient-history and missing-data behavior;
- reason codes and evidence fields explaining every classification;
- point-in-time evaluation using only information available at the evaluated session;
- integration with existing market-data and security-identity boundaries;
- unit, threshold-boundary, transition, missing-data, point-in-time, and regression tests;
- concise implementation documentation with formulas, transition rules, and representative outputs.

Keep structure separate from setup classification, market regime, group/industry/theme leadership, actionability, risk, position sizing, and composite opportunity scoring.

Do not implement EP, CONTRACTION, TREND_PULLBACK, or RANGE in this milestone.

## Verification and completion

Run focused tests during development. At the end run:

`.venv/bin/python -m pytest`

`git diff --check`

Commit only reviewed source, configuration, documentation, and tests. Push `codex/structure-engine-v1`. Do not merge or publish externally.

## Deferred publication blocker

The 2026-09-05 staged security-master artifact is valid but production publication is separately blocked because Parquet `last_updated_utc` preserves nanoseconds while the current DuckDB `TIMESTAMP` column stores microseconds, producing 13,146 post-publication field differences.

Record this as deferred. Do not fix it during AP-STRUCTURE-001. Do not publish the security master, build exposure classification, apply any of the 23 crosswalk proposals, make provider requests, or alter staged/production data.

## Completion record

Implemented on `codex/structure-engine-v1`, based on handoff commit `b846d2a`.
The new pure engine, strict versioned schemas, daily-bar adapter and explicit
reference boundary implement the approved S1–S6 rules independently of legacy
classifiers. See [implementation and acceptance evidence](structure-engine-implementation-v1.md).
AGENTS now requires reading this assignment immediately after PROJECT_STATE.

Validation: 176 focused tests passed (149 new structure tests plus 27 existing
feature/identity regressions); the complete suite passed all 557 tests.
Whitespace checks passed. Production/staging contents and machine settings were
verified unchanged. The nanosecond publication blocker remains deferred;
no provider requests, data publication, exposure build or crosswalk application
occurred. Commit identity is the milestone commit containing this record.
