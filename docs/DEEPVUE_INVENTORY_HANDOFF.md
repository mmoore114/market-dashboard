# Deepvue hierarchy capture and local inventory handoff

Task: AP-DEEPVUE-INVENTORY-001
Status: READY after the active engine-alignment task completes
Date: 2026-09-07
Scope: local file inventory and documentation only

The owner authorized gathering missing Deepvue hierarchy lists and documenting
how Codex finds the captures in Chromebook Downloads shared with Linux.
Do not interrupt or replace AP-ENGINE-ALIGNMENT-001.

## Captured sources

See deepvue_capture_manifest_2026-09-07.json for exact filenames, hashes,
sizes, capture dates, coverage and conflicts. The raw files are supplied privately
in deepvue_taxonomy_package_2026-09-07.zip, not committed to this public repository.

September 7's direct screener export now has all four hierarchy fields:
Sector (11 labels), Group (25), Industry (73), Sub-Industry (164).
11,368 unique symbols total; 5,461 have Sector/Group/Industry and 5,458
have Sub-Industry. Missing classifications remain explicit.
This resolves the earlier absence of parent fields in the September 5 export;
it does not guarantee universal stock coverage or historical membership.

Four child labels map to multiple parents. Preserve original per-symbol rows
and flag these conflicts; do not force a label-level hierarchy without review.
The package also preserves the September 5 stock export and 31-theme capture:
1,794 nonempty symbol memberships plus an empty Bitcoin-theme marker.
Those files have not been refreshed to September 7.

## Browser operation receipt

Authenticated Deepvue UI export; no hidden endpoint extraction.
A separate new column set named Untitled Column Set (2) was created and its
four hierarchy fields selected. The UI saves those selections automatically.
Existing saved screens and column sets were not overwritten.
The capture did not publish production data or build a snapshot.

## Laptop continuation

1. After engine alignment completes, use an isolated worktree or a separate
   branch for this task. Read the current repository authority.
2. Locate the downloaded ZIP in the Linux-visible shared Downloads directory.
   Determine the actual mounted path; do not assume it exists at a guessed path.
3. Verify archive entries are safe and extract to a new private staging directory
   without overwriting existing artifacts. Verify each file against the manifest.
4. Inventory existing earlier Deepvue captures by filename and hash; do not delete
   duplicates. Record matches, missing files and exact verified local paths.
5. Keep a durable private local inventory with absolute paths. Commit portable
   filenames, hashes, coverage, capture dates, and an environment-root recipe
   such as DEEPVUE_SOURCE_DIR plus relative filenames. The owner has authorized
   path documentation; do not include credentials or raw exports in Git.
6. Verify row counts, unique symbols, theme empty marker, hierarchy conflicts,
   and point-in-time/source dates. Resolve discrepancy reports, not trading rules.
7. Update docs/deepvue_audit.md to distinguish the earlier September 5 capture
   from this newly available September 7 hierarchy. Link this manifest.
8. Commit and push documentation on a feature branch and open a draft PR.
   Do not merge. Return commit, PR, private inventory path, portable root recipe,
   hash verification, and remaining source gaps.

No engine changes, imports with --publish, production mutations, provider
requests, historical backfill, taxonomy conflict resolution, or snapshot rebuild
are authorized by this inventory handoff. No full application test suite is needed.
