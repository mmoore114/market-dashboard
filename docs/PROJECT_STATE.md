# Aperture — authoritative project state

Updated: 2026-09-05. Current milestone: approved engine contracts and Deepvue taxonomy import foundation.

## Read first

Read `AGENTS.md`, this file, and both canonical engine specifications before
engine work. Current instructions and explicit amendments supersede older
session summaries. Historical checkpoints remain evidence of prior work.

- [Structure contract](structure-state-engine-v1.md)
- [Setup contract](setup-classification-engine-v1.md)
- [Blocking specification decisions](engine-spec-open-issues.md)
- [Approved V1 engine decisions](engine-spec-decisions-v1.md)
- [Foundation and taxonomy audit](data-foundation-gap-report.md)
- [Deepvue audit status](deepvue_audit.md)

The engine specifications are complete recovered documents. The explicit owner
authorization and exact resolutions in `engine-spec-decisions-v1.md` make them
implementation-ready. Codex must use that decision overlay rather than infer
from conflicting recovered prose.

## Verified repository baseline

- Repository: `mmoore114/market-dashboard`.
- Foundation branch: `codex/aperture-foundation`.
- Inspected baseline: `d1192f66ecd9c5bd7142264db7d44096cf8be29b`.
- User confirmed laptop HEAD and origin match that commit.
- User's only reported local change is `.vscode/settings.json`; preserve it.
- Current code is Python under `src/market_dashboard/`, with `config`, `scripts`,
  `tests`, and a Streamlit diagnostic placeholder. No React/FastAPI monorepo is
  implemented. React/TypeScript plus a typed Python API remains the proposed
  interface direction; do not mechanically relocate the repository.

## Previously completed, as recorded in the August checkpoint

- Exposure-policy-v3 publication: 13,023 securities; v2 preserved.
- Corrected research/backfill universe: 1,787 instruments (1,424 common stocks,
  363 diversified ETFs); distinct from stricter equity-trade membership.
- Adjusted history: 63,279 rows, 100 tickers, 2024-01-02 through 2026-07-24.
- Original ranks 1–50 preserved; authorized v3 ranks 51–100 completed.
- Milestone 1 and hardening completed; checkpoint reports 314 passing tests.
- Milestone 2 was not started.

These are recorded validation results, not a fresh inspection of the laptop's
databases. No new ingestion or data-validation run occurred in this documentation
milestone. Dates are historical coverage, not a claim of current market freshness.

## Confirmed product decisions

- Preserve the vocabulary Market Context, Structure Engine, Setup Engine,
  Evidence Object, Decision Queue and Time Machine.
- Deterministic research and decision support remain separate from probabilistic
  AI. No brokerage execution.
- Structure: NEUTRAL, EMERGING, UPTREND, DETERIORATING, DECLINE. BASE is obsolete
  as a state name; this is not a linear-only transition graph.
- Setup: EP, CONTRACTION, TREND_PULLBACK, RANGE. Multiple objects are allowed;
  RECLAIM is evidence, with no primary/secondary setup ranking.
- Lifecycle includes RESOLVED; STALE is pre-trigger only. EP resolves after five
  following sessions without failure. Trigger references are committed by T-1.
- Keep structure, setup, leadership, extension, regime, actionability, sizing
  and portfolio context separate. Setup invalidation is not a trade stop.
- Existing configured thresholds remain versioned hypotheses. Do not replace
  them with remembered values from conversations.
- Massive is the market-data/security foundation. Aperture should own its dated
  classification and theme membership records, with Deepvue as a bootstrap and
  chart-review reference, not a required runtime dependency. Sub-industry CSV
  transfer is verified; parent hierarchy and theme membership remain unverified.

## Current milestone additions

- Completed authenticated Deepvue all-stock export inspection: 11,370 unique
  symbols, 5,462 meaningful Sub-Industry classifications, 164 labels, and two
  internally ambiguous group ranks.
- Added a dry-run-by-default Deepvue taxonomy normalizer and dated DuckDB/Parquet
  publisher. Raw proprietary exports remain local and uncommitted.
- Recorded the observed 31-theme catalog; constituent membership is still
  unverified and must not be invented.
- Closed S1-S6 and U1-U8 with exact formulas, timing, precedence, missing-data,
  identity, and lifecycle rules in `engine-spec-decisions-v1.md`.

## Prior documentation milestone

- Preserved both full source specifications verbatim in `docs/reference/`.
- Added canonical copies with NEUTRAL, RESOLVED and trigger-timing amendments.
- Registered mathematical, lifecycle, feature and migration blockers.
- Added a repository-grounded foundation report and Deepvue audit status.
- Added reading precedence to AGENTS and notices on older design documents.
- No engine code, immutable config, market data or machine settings changed.

Documentation validation: archived source files were compared byte-for-byte to
the recovered originals. The authored/canonical diff passes whitespace checks.
The unmodified archives retain Markdown two-space hard breaks, which standard
`git diff --check` reports as trailing whitespace; this is an intentional source
preservation exception. Python tests were not rerun for this documentation-only
change; the 314 result above remains the recorded baseline.

## Next work

1. Perform read-only local data inventory/validation through laptop Codex using
   the existing scripts. Confirm actual files, dates, adjustment policy and
   shared feature definitions before any new data build.
2. Pull the feature branch on the laptop, export the current all-stock Deepvue
   CSV locally, run the taxonomy importer in dry-run mode, reconcile coverage to
   the local Massive security-master snapshot, then explicitly publish.
3. Obtain or curate verified many-to-many theme membership separately; do not
   treat the observed theme catalog as membership.
4. Implement the approved shared features and engine contracts on a feature
   branch with boundary, state-path and no-look-ahead tests, preserving legacy
   outputs and version identities.

Real ingestion still requires a bounded dry run and separate explicit approval.
Use a pull request. Do not merge into main as part of this documentation task.
