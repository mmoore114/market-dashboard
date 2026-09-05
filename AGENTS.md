# Repository Instructions

## Purpose

This repository is the local research and decision-support engine for Aperture, a transparent daily-chart momentum and growth swing-trading workflow. It is not a broker, autonomous trading bot, or source of personalized financial advice.

Keep equity research in this repository. Do not mix in separate options-tradability work.

## Non-negotiable safety rules

- Never commit .env files, API keys, credentials, DuckDB databases, Parquet datasets, raw or processed market data, ingestion manifests, generated reports containing licensed market data, virtual environments, caches, or machine-specific paths.
- Massive.com credentials remain local and server-side.
- Never start a real Massive.com ingestion or other potentially costly external-data job without explicit user approval. Use a bounded dry run first.
- Preserve point-in-time discipline: form a signal using information available at session T close and evaluate fills no earlier than T+1.
- Do not add broker routing, automated order submission, or unattended trade execution.
- Do not silently change thresholds, formulas, labels, or historical classifications. Version changes that alter research meaning.

## Current environment

- Chromebook Linux
- VS Code with Codex
- Python 3.13.5 locally; project supports Python 3.11+
- Virtual environment: .venv
- Prefer .venv/bin/python for commands
- GitHub is the remote source of truth
- Work on a feature branch and use a pull request; do not develop new Aperture work directly on main

Before editing:

1. Run git status --short --branch.
2. Read docs/PROJECT_STATE.md first, then README.md, docs/session_progress_2026-07-26.md, docs/session_progress_2026-08-25.md, docs/aperture_product_contract.md, docs/deepvue_audit.md, and docs/architecture_decision.md.
3. Preserve unrelated or user-owned changes.
4. Confirm the requested milestone and its acceptance criteria.

For structure/setup work, also read docs/structure-state-engine-v1.md,
docs/setup-classification-engine-v1.md, and docs/engine-spec-open-issues.md.
Explicit amendments in those contracts supersede older design candidates and
the archived sources under docs/reference/. Do not implement unresolved rules
by assumption. Update docs/PROJECT_STATE.md after meaningful milestones.

## Required verification

For Python changes, run the smallest relevant test set first, then the full suite when practical:

~~~bash
.venv/bin/python -m pytest
~~~

Also run:

~~~bash
git diff --check
~~~

For data-pipeline changes, use the existing validation scripts and report row counts, date ranges, duplicate keys, nulls, publication state, fingerprints, and DuckDB/Parquet agreement as applicable.

Do not claim a command, data build, deployment, or test passed unless its output was actually observed.

## Domain modeling rules

Keep these concepts separate in code and storage:

- instrument/exposure classification;
- research universe and trade universe;
- market regime;
- sector, industry, and theme leadership;
- relative and absolute strength;
- structural stage;
- extension;
- setup;
- action state;
- position sizing and portfolio heat;
- trade outcomes and benchmark performance.

A structural stage is not a setup. Extension is not a stage. A high score is not an entry signal. A setup is not actionable until all relevant universe, regime, group, extension, earnings, and risk checks pass.

Prefer explicit component fields and reason codes over opaque composite scores. Any composite score must remain decomposable, versioned, and labeled experimental until validated.

## Compatibility and migration

- Existing exposure-policy-v2 results are immutable and must remain reproducible.
- Exposure-policy-v3 extends v2 and is the configured default.
- Do not delete the completed adjusted bars for the original ranks 1-50.
- Keep legacy fields only when necessary for backward compatibility and mark their replacement clearly.
- Add new metrics alongside old metrics when definitions differ. For example, do not silently replace the existing simple rolling ATR with Wilder ATR.

## UI direction

The primary Aperture interface will be a dense React and TypeScript application. Python remains the computation, ingestion, validation, and API layer. Streamlit may remain as an internal diagnostic/admin surface, but it is not the target production experience.

The primary review flow is:

Brief -> Groups/Tape -> Stock detail -> Sizer/Book -> Rules/Journal

Deepvue remains the preferred chart-review, drawing, replay, and alerting workspace. Aperture should complement it with proprietary rules, ranking, state, sizing, journaling, and benchmarking rather than duplicate every charting feature.

## Change discipline

- Keep pure calculation logic separate from ingestion, persistence, and UI code.
- Put thresholds in named, versioned configuration or immutable policy objects.
- Add tests for threshold boundaries, missing data, precedence, persistence, and point-in-time behavior.
- Use concise commit messages that identify the milestone.
- Update relevant documentation in the same change when formulas or state semantics change.
