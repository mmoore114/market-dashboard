# Deepvue private inventory completion

Task: `AP-DEEPVUE-INVENTORY-001` — COMPLETE, draft PR delivery only; do not merge.

Verified: 2026-09-07 23:41 UTC. Authority remains
[APERTURE_CURRENT_AUTHORITY.md](APERTURE_CURRENT_AUTHORITY.md), under
[AGENTS.md](../AGENTS.md). Scope comes from the owner-authorized
[handoff](DEEPVUE_INVENTORY_HANDOFF.md) at
`699347c241904012136dd398eedc657034051375`.

Work uses the isolated `codex/deepvue-inventory-001` branch based on that handoff
and main `a9c81aa048bc23d9247c8e9f3c76ef3aae17d92a`. The completed engine work
remains on `codex/engine-alignment-v2` at
`5abc233e186d73ee56d1f54376fef45beead6e61`, in [draft PR #15](https://github.com/mmoore114/market-dashboard/pull/15).
This inventory does not revise engine authority or bring engine changes into its PR.

## Package verification

ZIP filename: `deepvue_taxonomy_package_2026-09-07.zip`; 347,525 bytes.
SHA-256: `dbcd924a6357f21645db75516943e16e4ce4a96e7a0e4e1f3adc5cffb3909b7f`.
This is the locally observed archive hash; the handoff supplies independent hashes
for its CSV contents, not an independently authenticated archive hash.

All five archive entries were checked before extraction: exact expected names,
no absolute or traversal paths, no duplicate entries, symlinks, special files or
encrypted entries; bounded sizes and CRC verification passed. Extraction used
exclusive file creation in a new private directory outside Git, with directory
permissions 0700 and files 0600. Existing artifacts were not overwritten.
The packaged manifest is semantically identical to the
[repository capture manifest](deepvue_capture_manifest_2026-09-07.json).
Its original `LAPTOP_PATHS_PENDING_VERIFICATION` is capture-time status; this
completion record supersedes that status without rewriting the captured manifest.

| Portable source filename | Capture date | Bytes | Rows | Verified |
| --- | --- | ---: | ---: | --- |
| `deepvue_hierarchy_2026-09-07.csv` | 2026-09-07 | 558087 | 11368 | SHA-256, headers, unique nonblank symbols |
| `deepvue_all_stock_export_2026-09-05.csv` | 2026-09-05 | 818176 | 11370 | SHA-256, headers, unique nonblank symbols |
| `deepvue_theme_membership_2026-09-05.csv` | 2026-09-05 | 28783 | 1795 | SHA-256, headers, unique theme/symbol pairs |

Exact CSV hashes, hierarchy coverage, capture timestamp and all four parent
conflicts are in the linked manifest; recomputation matched every declared value.
Theme checks found 31 themes, 30 populated, 1,794 nonempty memberships and 1,323
unique nonempty symbols. The one empty-symbol row is Bitcoin; it is not a stock.
No discrepancy required changing source rows or dates.

## Portable local path recipe

Locate Downloads through the Chromebook Files application's Linux sharing and the
actual mounted filesystem. The Linux home Downloads directory was absent on this
machine; the shared Downloads mount was verified directly. Do not assume a mount
path from a prior machine. Keep absolute paths solely in the private `inventory.json`.

Set `DEEPVUE_INVENTORY_FILE` to that private inventory's actual absolute path. Then:

```bash
export DEEPVUE_SOURCE_DIR="$(python3 -c 'import json, os; print(json.load(open(os.environ["DEEPVUE_INVENTORY_FILE"]))["source_dir"])')"
test -f "$DEEPVUE_SOURCE_DIR/deepvue_hierarchy_2026-09-07.csv"
sha256sum "$DEEPVUE_SOURCE_DIR/"*.csv
```

Export `DEEPVUE_INVENTORY_FILE` before running this recipe. Compare the printed
hashes with the repository manifest. Source paths are always
`${DEEPVUE_SOURCE_DIR}/<filename>` from the table. The private inventory records
absolute archive/extraction paths, each file's hash/size/date, search roots and
availability, earlier captures and duplicates, verification time and coverage.
Do not commit the ZIP, raw CSVs or private inventory.

## Earlier captures and preservation

Within the verified shared Downloads, prior staging and repository data search
roots, `Screener.csv` matches the packaged September 5 stock export exactly.
`Screener (1).csv` and `Screener (2).csv` in Downloads' existing trash also match;
all three remain in place, without deletion, movement or restoration. The earlier
`deepvue_theme_membership_2026-09-05.csv` matches the packaged theme capture.
No missing expected package files or mismatched earlier captures were found.
The new hierarchy was located in the ZIP, with no earlier standalone copy found
in these search roots. This is a bounded local inventory, not an exhaustive scan
of every device or cloud account.

All 1,383 retained baseline files, including source data, original snapshots,
backups and the user-modified settings file, passed byte-hash preservation checks.
The separate engine-comparison artifacts and engine branch were preserved.
Documentation links, authority chain, portable path recipe, Git whitespace and
documentation-only diff were checked. No application tests or rebuilds were needed.

## Remaining source gaps

The [updated audit](deepvue_audit.md) distinguishes September 5 and September 7.
Missing classifications remain explicit; four parent-label conflicts remain
unresolved. September 5 themes and stock metrics are not September 7 refreshes.
Historical membership, revision identifiers, GICS license/equivalence and universal
coverage remain unverified. No runtime membership publication or snapshot rebuild
was performed; Groups' existing missing-evidence state is unchanged.
No blocker remains for this inventory task. Any publication, conflict resolution,
provider request or historical backfill requires a separate authorization.
