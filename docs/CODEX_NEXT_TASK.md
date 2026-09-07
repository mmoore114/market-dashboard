# Codex Next Task

**Status:** NO ACTIVE IMPLEMENTATION TASK

**Updated:** 2026-09-07

**Current authority:** `docs/APERTURE_CURRENT_AUTHORITY.md`

**Working prototype baseline:** `401e1b0afd6ad2a4678af4f1040014b5c9b568e9`

The prior `AP-CURRENT-BOOTSTRAP-001` assignment is complete. Its full receipt is
preserved in project history and the versioned bootstrap documentation. Do not
rerun it or infer a new assignment from a completed milestone.

## Proposed next milestone

`AP-ENGINE-ALIGNMENT-001` is proposed but not authorized by this file.

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

## Not authorized until explicitly started

- engine or threshold changes;
- production publication or migration;
- provider acquisition;
- historical relabeling;
- deletion of legacy code or evidence;
- UI redesign;
- PR merging.

When the owner is ready, create a repository handoff with an exact branch, baseline,
acceptance criteria, data boundary, and version names. Until then, agents may review
the current prototype but must not begin implementation based solely on this
proposal.
