# V2 defaults and Groups activation completion

Task: `AP-V2-GROUPS-ACTIVATION-001`.
Code/publication complete; real populated snapshot blocked by input clocks.

## Reviewed integration and defaults

PR #15 head `5abc233e186d73ee56d1f54376fef45beead6e61` and PR #16 head
`12cad5ffef233256c2ded9d64a970e670b2ec711` matched owner-reviewed commits.
Both were mergeable with CLEAN status and no reported required checks. They were
marked ready and merged with normal merge commits, exact head matching, no admin
bypass and no branch deletion. Merge commits: `95aa627852c70d01af8b4e56b028d6803ddbb9be`
and `ca4153b41ee3fea1ef2266cec2970701bee8ca0a`, respectively.

New feature branch `codex/v2-groups-activation` starts at the latter main commit.
`VersionsV1` now defaults to the coherent reviewed V2 pair and rule fingerprints.
Explicit `VersionsV1.v1(...)` retains historical generation; serialized plans and
snapshots retain their explicit selection. V1 synthetic migration fixtures remain
explicitly V1. No reviewed formula, threshold, lifecycle or rule fingerprint changed.
See [the engine contract](engine-alignment-v2.md) for unchanged semantics; its
V1-default statement records the earlier milestone's delivery boundary.

The added GROUP enum level changes the schema registry fingerprint. Exact retained
prototype and reviewed V2 registry fingerprints remain accepted with unchanged type
codes/column layouts. Both real retained snapshots were loaded and their original
logical fingerprints verified unchanged.

## Dated publication and cohort coverage

All three source hashes were reverified against the
[capture manifest](deepvue_capture_manifest_2026-09-07.json), using the private
[inventory recipe](deepvue_inventory_2026-09-07.md). Hierarchy source date is
September 7; themes remain September 5. Local publication completed September 7
at 23:53:11.514821 UTC. Effective/known membership session is September 8, with
valid-through September 8. No historical membership is claimed or backfilled.

| Actual cohort | Symbols | Sector | Group | Industry | Sub-industry | Has theme | Theme memberships |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Research | 75 | 75 | 75 | 75 | 75 | 58 | 114 |
| Strict trade | 49 | 49 | 49 | 49 | 49 | 40 | 84 |

These are the retained published Aperture cohorts, not all Deepvue symbols.
All cohort symbols have exact hierarchy rows. The 17 research and nine trade
symbols without theme assignments remain unassigned; absence is not evidence of
exclusion. Across the full capture, 5,907 symbols lack parent fields and 5,910 lack
sub-industry. None was imputed or removed from its source table.

Catalogs contain 11 sectors, 25 groups, 75 industry paths, 170 sub-industry paths
and 31 themes (including empty Bitcoin). JSON-array path identities preserve each
row's original parents, including nulls. The 73 industry and 164 sub-industry
labels produce more paths because of the four retained conflicts:
Retail REITs, Health Care REITs, Real Estate Management & Development, and Ground
Transportation. No canonical parent was selected; theme memberships remain
many-to-many with their original 1,794 memberships and 1,323 unique symbols.

The exact-case identity/disposition boundary preserves unresolved members and
non-securities as explicit evidence; it does not silently convert or discard them.
The full original hierarchy and raw captures remain available privately.
Materialization validates/selects schedules independently for each hierarchy level.
The existing Leadership V1 aggregation and minimum-member/coverage gates supply
supported RS/leadership metrics; unsupported ranks/history remain null with reasons.
Groups renders level/search controls, parent paths, source/effective/known dates,
member lists and missing/coverage explanations. Deepvue remains the chart companion.

## Private publication and recovery

Set `APERTURE_GROUPS_DIR` to the private local `aperture-v2-groups-activation`
workspace supplied in the delivery. Its `publication-receipt.json` records exact
absolute paths and SHA-256 values; none of these files is committed.

- `published.duckdb`: separate local database copied from the verified original.
- `backup/before.duckdb`: independent byte-identical pre-publication backup.
- `hierarchy/source_as_of_date=2026-09-07/symbol_hierarchy.parquet`.
- `themes/source_as_of_date=2026-09-05/theme_catalog.parquet` and
  `theme_membership.parquet`.
- `taxonomy-schedule.json` and `themes-schedule.json`: typed GroupScheduleV1 inputs.
- `intent.json` and `publication-receipt.json`: prepared/complete local receipt.

Existing DeepvueThemeStore and a separate hierarchy store use dated DuckDB
transactions and atomic Parquet replacement. The old sub-industry/rank tables are
preserved. Readback verified database/Parquet equality, normalizing only date
representation for comparison. The initial verification stopped on Python date
versus DuckDB timestamp representation; resumed verification used already-published
files without repeating writes. No source value was corrected.

Rollback is limited to this new workspace: after verifying the receipt's backup
hash, restore its private database copy from `backup/before.duckdb` and deactivate
the new schedule/Parquet paths. Preserve them for audit. Original production data
needs no rollback because it was never mutated. The reusable hierarchy CLI defaults
to validation and requires source hash, explicit publication paths and an independent
matching database backup for writes. Future materialization must bind these schedule
hashes and actual publication clocks in its source manifest; receipt completion
alone does not grant freshness or historical coverage.

## Verification and live snapshot limit

Focused V2 semantics and activation: 48 unique tests passed (43 retained V2, five
new activation tests). Relevant materialization, Workstation compatibility,
leadership, Deepvue and foundation integration: 272 passed. A focused published-
groups check also passed after correcting a schedule-variable collision discovered
by the new multilevel integration test. No complete Python suite was repeated.
Frontend components: 13 passed. Typecheck, production build, lint, OpenAPI/schema
and generated-type synchronization, scoped Python lint/format and Git whitespace
checks passed. Desktop/mobile populated Groups smoke: two passed using clearly
labeled synthetic fixture evidence; no claim of a live populated snapshot.

No real snapshot was built. The September 7 hierarchy cannot be selected for
September 4 market evidence, and the retained snapshot expiry at September 8
00:00 UTC is unchanged. Required inputs: verified adjusted bars through a completed
eligible session (earliest September 8) for the research cohort and required
benchmarks, contract-valid spot volatility (retained series ends September 3),
and valid current control/publication bindings. Use the true availability/evaluation
time and next XNYS action session, September 9 for September 8 evidence. Preserve
the explicit current-cohort bootstrap boundary unless actual historical membership
is supplied; later sessions require attested membership validity beyond September 8.

All protected original source data, settings, captures, snapshots, engine comparison
artifacts and retained backups remain byte-identical. No provider request, production
source-data mutation, chart implementation or merge of the new feature PR occurred.
