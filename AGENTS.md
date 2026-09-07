# Repository Instructions

## Purpose

This repository contains Aperture, a local research and decision-support
workstation for daily U.S. equity swing and momentum trading. It is not a broker,
an autonomous trading bot, a charting platform, or a source of personalized
financial advice.

## Mandatory reading order

Before changing anything, read only this current-authority sequence first:

1. `AGENTS.md`
2. `docs/APERTURE_CURRENT_AUTHORITY.md`
3. `docs/PROJECT_STATE.md`
4. `docs/CODEX_NEXT_TASK.md`
5. `docs/LEGACY_BOUNDARY.md`

Read additional documents only when the current task or authority file routes to
them. Historical session reports, archived sources, old product contracts, and
completed task receipts are evidence, not current instructions.

If two documents conflict, follow the precedence in
`docs/APERTURE_CURRENT_AUTHORITY.md`. Do not reconstruct current rules from chat
memory or select whichever historical formula appears most detailed.

## Before editing

1. Run `git status --short --branch`.
2. Confirm the exact branch, baseline commit, task ID, and authorization boundary.
3. Preserve unrelated and user-owned changes, especially `.vscode/settings.json`.
4. Inspect the active code path before assuming a legacy field controls Aperture.
5. Stop for a material contract contradiction or action outside the authorization.

## Product boundaries

- Python owns ingestion, validation, storage, canonical calculations, and snapshot
  materialization.
- React/TypeScript and FastAPI form the primary Workstation interface.
- Streamlit is a legacy diagnostic/admin surface, not the primary product.
- Deepvue remains the chart-review, drawing, replay, and alerting workspace.
- Do not implement price charts, drawing tools, technical overlays, or a competing
  chart engine inside Aperture unless the owner explicitly reverses this decision.
- Do not add broker routing, automated orders, or unattended execution.
- Keep separate options-tradability work outside this repository.

## Domain model

Keep these concepts independent in code, storage, APIs, and UI:

- instrument and exposure classification;
- market-mapping, equity-research, and equity-trade universes;
- market regime;
- sector, industry, and theme leadership;
- relative and absolute strength;
- Structure state;
- extension;
- Setup family and lifecycle;
- actionability and vetoes;
- position sizing and portfolio heat;
- outcomes, journal, and benchmarks.

A Structure state is not a Setup. Extension is not Structure. A score is not an
entry signal. Setup invalidation is not a trade stop. `ACT` means perform
discretionary review; it is not an order instruction.

## Current and target engine authority

The current deployed prototype uses the versioned V1 Structure and Setup engines
documented in their implementation files. Those outputs must remain reproducible.

The owner has settled a target alignment that differs from parts of runtime V1:

- Structure should use the final Word specification's SMA20/SMA50 ATR-normalized
  model; EMA10 is context, not a Structure voter.
- Shock transitions should initially produce `EMERGING` or `DETERIORATING`, not a
  mature trend by themselves.
- Long-lived horizontal bases and tightening phases must not stale after only a
  few sessions solely because of age.
- The Git V1 no-look-ahead, frozen-reference, identity, event-order, lifecycle,
  missing-data, corporate-action, and corrected-replay safeguards remain accepted.

These are target decisions, not permission to relabel current V1 output. Implement
them only under a new version and an explicit task. Use
`docs/APERTURE_CURRENT_AUTHORITY.md` for exact status and remaining provisional
choices.

## Legacy boundary

Legacy Opportunity Score, Leadership Score, `trend_stage`, `price_action_state`,
EMA9, simple ATR, and the original Streamlit dashboard remain preserved for
compatibility and historical research. They must not vote in current Aperture
Structure, Setup, Actionability, or `WATCH/TRADE/ACT` decisions.

Do not delete or silently rewrite legacy outputs. Do not copy their labels or
thresholds into new Aperture work. See `docs/LEGACY_BOUNDARY.md`.

## Safety rules

- Never commit `.env`, credentials, API keys, DuckDB files, Parquet datasets, raw
  or processed market data, provider exports, ingestion manifests, licensed-data
  reports, generated snapshots, receipts, backups, virtual environments, caches,
  or machine-specific paths.
- Massive.com credentials stay local and server-side.
- Do not start a provider request or potentially costly ingestion without explicit
  user authorization. Use a bounded dry run first unless the active task explicitly
  authorizes a bounded fetch.
- Preserve point-in-time discipline and source provenance.
- Never invent, backdate, forward-fill, or silently drop observations or membership.
- Do not silently change thresholds, formulas, labels, version identities, or
  historical classifications.
- Never delete retained backups or protected historical artifacts without explicit
  authorization.

## Change discipline

- Keep pure calculation logic separate from ingestion, persistence, and UI code.
- Put thresholds in named, immutable, versioned configuration or policy objects.
- Return explicit nulls and reason codes.
- Add focused tests for boundaries, missing data, precedence, persistence,
  point-in-time behavior, and version isolation.
- Update current documentation in the same change as semantic code changes.
- Use a feature branch and draft pull request; do not develop directly on `main`.
- Do not merge a pull request unless explicitly authorized.

## Verification

Run the smallest relevant checks first. For Python changes, run the focused tests
and then the complete suite when practical:

```bash
.venv/bin/python -m pytest
git diff --check
```

For frontend changes, run the applicable component/browser tests, typecheck,
production build, schema synchronization, and lint/format checks.

Documentation-only work must at minimum verify links/paths, Markdown whitespace,
the declared authority chain, branch status, and the absence of unintended code or
data changes. Never claim a check passed unless its output was observed.
