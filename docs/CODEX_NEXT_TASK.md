# Codex Next Task

**Status:** COMPLETE — DRAFT PR DELIVERY, DO NOT MERGE

**Updated:** 2026-09-07

**Current authority:** `docs/APERTURE_CURRENT_AUTHORITY.md`

**Working prototype baseline:** `401e1b0afd6ad2a4678af4f1040014b5c9b568e9`

**Completed assignment:** `AP-ENGINE-ALIGNMENT-001`, explicitly authorized by the
owner on 2026-09-07.

**Implementation baseline:** `origin/main` at
`a9c81aa048bc23d9247c8e9f3c76ef3aae17d92a`.

**Branch:** `codex/engine-alignment-v2`.

The prior `AP-CURRENT-BOOTSTRAP-001` assignment is complete. Its full receipt is
preserved in project history and the versioned bootstrap documentation. Do not
rerun it or infer a new assignment from a completed milestone.

## Authorized milestone

Implement explicitly versioned Structure/Setup V2, with explicit version selection
through materialization and API evidence. Preserve V1 computation and snapshots.

Intended scope:

1. Implement a newly versioned Structure candidate aligned to the final Word
   SMA20/SMA50 specification, with EMA10/SMA200 context-only and transitional-only
   shock overrides.
2. Preserve the current Structure V1 implementation and historical outputs.
3. Retain accepted Git V1 safety, timing, identity, lifecycle, corporate-action,
   missing-data, and corrected-replay behavior.
4. Implement the settled long-lived Setup ages: RANGE up to 60 sessions and
   CONTRACTION initially up to 40 sessions while the formation remains valid.
5. Run a bounded side-by-side classification sanity comparison on existing local
   data for only the genuinely provisional decisions listed in
   `APERTURE_CURRENT_AUTHORITY.md`.
6. Record changed classifications and obvious churn/reachability effects; do not
   optimize thresholds against future returns.
7. Select and document the coherent new version, rebuild one local snapshot, and
   verify the existing Workstation against it.

## Verified source and implementation

The source blocker is resolved. The owner supplied source-only commit
`71ef80d8637539d40ecdb7eda172db80adc50ce3`, cherry-picked as `a463bce` while
preserving this active assignment and the existing settings modification.

Read `docs/sources/final-word-spec/README.md`, the complete text and structural
JSON transcription, and `docs/engine-alignment-v2.md`. The original Word SHA-256
is `3e8de86756299a91a592eb9a78431896e783e7d8500d6c1254d93f28f6567965`.
The recovered earlier EMA10-voting specifications are historical evidence only.

Structure/Setup V2 are implemented with explicit materialization and API version
selection. V1 modules and the retained snapshot are preserved. Source ambiguities
and selected interpretations are documented in the V2 contract. Full verification,
the separate comparison snapshot, and desktop/mobile Workstation smoke checks
are complete. See `docs/engine-alignment-v2-receipt.md` for observed results.

This receipt does not authorize merging, routine refresh, recalibration, or a
production default switch. Deliver the reviewed changes in a draft PR against
main. Preserve settings and all protected artifacts. Do not rerun completed
materialization or tests merely because the historical scope below lists them.

## Verification and delivery boundary

- Add focused semantic, lifecycle, shock, transition, and V1/V2 isolation tests.
- Use a bounded comparison on identical existing inputs for provisional decisions;
  do not optimize against future returns or search broad parameter grids.
- Run relevant integration checks and the Python suite once when practical, using
  bounded groups where sandbox restrictions block local AnyIO/TestClient wakeups.
- Build a separate, honestly identified comparison snapshot with the original
  evidence, evaluation, and action clocks; preserve stale-data protections.
- Verify through the Workstation and stop services afterward.
- Update authority, project state, and a completion receipt when implemented.
- Commit, push, and open a draft PR against main when deliverable; do not merge.

No provider acquisition, production source-data changes, historical relabeling,
legacy deletion, chart implementation, or UI redesign is authorized. Preserve the
existing `.vscode/settings.json` modification, snapshots, backups, and protected
local artifacts exactly. No formula may be reconstructed from summaries.
