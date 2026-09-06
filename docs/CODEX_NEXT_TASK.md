# Codex Next Task

**Task ID:** AP-WORKSTATION-SNAPSHOT-002

**Status:** READY

**Issued:** 2026-09-06

**Base commit:** `dc3b9e21688c7a3fffd37b621ee74cd5555c01dc`

## Handoff protocol

This file is the single current assignment for VS Code Codex.

1. Read `AGENTS.md`, `docs/PROJECT_STATE.md`,
   `docs/workstation-slice-v1.md`, and the completed engine contracts before
   editing.
2. Correct the bounded snapshot scalability defect without redesigning the
   approved UI or canonical engines.
3. Work autonomously unless a material contract contradiction, destructive
   action, or external publication would be required.
4. At completion, mark this task `COMPLETE`, add a concise completion record,
   update `docs/PROJECT_STATE.md`, commit, push, and open a draft PR targeting
   `codex/workstation-slice-v1` so it contains only this correction.
5. Return only the full commit SHA, focused/full Python totals, frontend and
   browser totals, typecheck/build/contract results, PR link, and any blocker.

Preserve `.vscode/settings.json`, `.env`, credentials, databases, Parquet/CSV
datasets, staged artifacts, generated local reports, and unrelated user changes.

## Defect and required outcome

The first Workstation slice is visually and functionally sound, but its canonical
snapshot cannot scale to the real research universe.

Observed independently from the committed GREEN fixture:

- 12 symbol/direction records serialize to approximately 8,739,961 compact JSON
  bytes;
- the average is approximately 728 KB per record;
- each record's nested `DecisionRiskOutputV1.inputs` repeats roughly 317 KB of
  cross-sectional Leadership output and 332 KB of Regime input/output;
- the current 32 MiB loader limit would therefore fail after only a few dozen
  records, far short of the approximately 1,787-name research universe.

Create and work on:

`codex/workstation-snapshot-v2`

The required outcome is a normalized, immutable snapshot that preserves every
user-visible canonical value and audit reason while storing shared cross-sectional
evidence once. Prove that at least 2,000 realistic symbol/direction records fit
comfortably inside the bounded standalone JSON contract.

Do not begin real data materialization in this correction.

## Normalized snapshot V2

Introduce a new schema identity, `workstation-snapshot-v2`. Do not silently change
the meaning of `workstation-snapshot-v1`.

V2 must separate:

### Shared snapshot evidence — stored once

- snapshot identity, mode, dates, freshness, source and calendar;
- every version and rules fingerprint;
- immutable Aperture rules;
- research-universe identity and provenance, with its symbol membership stored
  once if required for audit;
- complete Regime output and its shared inputs, stored once;
- cross-sectional Leadership/group context needed for audit and Brief/Groups,
  stored once or normalized into nonduplicated indexed records;
- group evidence and funnel counts;
- deterministic logical fingerprint.

### Per-symbol/direction evidence — stored once per key

Retain only evidence specific to that exact symbol/direction, including:

- exact symbol, direction, display name and nullable price/volume context;
- universe memberships and their reasons;
- Structure evidence for the symbol;
- Setup output/instances for the symbol;
- symbol Strength evidence, including raw 5/21/63/126/252 components,
  `RS_comp`, `RS_rotation`, and `rotation_delta`;
- sub-industry and theme references plus the evaluated group gate;
- direction-aware extension evidence;
- earnings coverage/event evidence;
- evaluated Regime gate referencing the shared Regime identity;
- complete decision ladder gates, setup action evidence, veto/reason codes and
  final NONE/WATCH/TRADE/ACT state;
- sizing input context/result needed for display and canonical what-if sizing.

Do not retain a complete nested `DecisionRiskOutputV1` if it recursively duplicates
shared Leadership, Regime, Universe, rules, or group populations. A compact frozen
record may be projected from that engine output, but every copied field must have
an explicit source and equality test.

Use stable IDs/fingerprints to bind each compact record to the exact shared
calendar, source, universe, Leadership, Regime, rules, and version context. Reject
missing, mismatched, dangling, duplicate, or contradictory references.

Do not solve this by gzip alone, by raising the size limit, or by deleting audit
evidence the Workstation contract requires. Normalization must remove structural
duplication before any optional transport compression is considered.

## Conversion and validation

Provide a pure V1-engine-output-to-V2 materialization function that accepts the
completed canonical engine outputs and shared evidence explicitly. It must:

- validate exact symbol/session/action/source/calendar/universe/version alignment;
- prove projected values equal their canonical source fields;
- preserve explicit nulls and all machine/human reasons;
- store shared evidence once regardless of input row order;
- sort symbol/direction and indexed shared records deterministically;
- reject inconsistent repeated copies rather than choosing first/last;
- leave every input object unchanged;
- produce the same logical fingerprint under input reordering and generation-time
  changes, while exact logical-content changes alter it.

The logical fingerprint must cover normalized logical content except the existing
top-level generation timestamp and fingerprint field. It must not depend on JSON
whitespace, dictionary insertion order, or source row order.

Update `SnapshotStore` to accept V2 only for newly generated local snapshots. If
V1 remains readable for an explicit compatibility reason, it must be clearly
bounded and must never be relabeled V2. Fixture development and all API views must
use V2 after this task.

## API and Sizer preservation

Keep the existing `/api/v1` transport behavior unless a schema correction is
strictly necessary. Brief, Tape, exact-symbol detail, Rules, errors, filters,
sorting and pagination must remain behaviorally compatible.

`POST /sizer` must continue to call the canonical Python `size_idea` function.
Construct its `SizingInputV1` from the compact record plus referenced shared
Regime/rules context; do not duplicate sizing formulas or accept a mismatched
symbol/direction/session.

If a requested Sizer direction has no exact record, either construct only the
direction-independent context through an explicitly tested adapter or return a
typed refusal. Never silently borrow direction-specific evidence from another
record.

Regenerate deterministic OpenAPI and generated TypeScript types only if the
public transport contract actually changes. Contract drift must continue to fail.

## UI preservation

The existing Workstation passed visual review. Preserve its information
architecture, responsive layout, fixture labels, accessibility, session-only
preferences, and designed failure states.

Regenerate the synthetic fixture and screenshots from normalized V2. Verify:

- Brief, Tape, detail, Sizer, and Rules render the same canonical values;
- 5-session/1-week and 21-session/1-month strength remain visible;
- every gate, setup and veto remains inspectable;
- mobile Tape remains intentionally scrollable/usable rather than clipping
  inaccessible columns;
- no canonical calculation moves into TypeScript.

Do not add Groups, Book, Journal, portfolio heat, charts, or unrelated styling in
this correction.

## Required scale and integrity evidence

Add a deterministic synthetic scale test with at least 2,000 distinct
symbol/direction records and realistic variation in states, setup counts, reasons,
groups, event evidence, and missing values.

The committed or generated compact V2 JSON for that test must:

- remain below 24 MiB uncompressed, leaving operational headroom under the current
  32 MiB loader limit;
- contain no duplicated full Leadership or Regime object per symbol;
- load and validate through `SnapshotStore` within a documented reasonable local
  bound without loosening validation;
- return correct Brief totals, Tape pagination/filters, symbol detail and Sizer
  context for first, middle and last keys;
- have deterministic bytes or canonical digest across repeated builds.

Do not commit the 2,000-record generated scale artifact if it is reproducible in a
temporary test directory. Record measured bytes, bytes per record, build time and
validation/load time in the completion documentation. Timing is diagnostic and
must not become a flaky hard assertion; the byte-size ceiling is a hard test.

Also record the normalized size of the existing 12-record GREEN fixture and the
percentage reduction from approximately 8,739,961 compact bytes.

## Verification

Add focused Python tests for:

- V2 frozen/extra-field-forbidding schemas;
- shared-evidence deduplication and exact reference binding;
- equality of every V2 projected field to canonical engine output;
- mismatched/dangling/duplicate shared identities;
- stable ordering and fingerprint determinism;
- explicit null and full reason preservation;
- compact Sizer adapter and canonical delegation;
- V1/V2 version refusal or explicitly documented compatibility;
- malformed, oversized, stale and future local snapshots;
- 2,000-record size/integrity/API behavior;
- no network/provider/database access and no production/staged writes;
- all completed-engine regressions.

Run the full existing Python, frontend component, and Chromium desktop/mobile
suites. Run OpenAPI/type synchronization, TypeScript typecheck, production build,
Python/frontend lint/format, and `git diff --check`.

Update `docs/workstation-slice-v1.md` or add a focused V2 document explaining the
normalized schema, reference integrity, migration, measured sizes, exact commands,
and why this correction is required before real local materialization.

## Deferred work

Do not implement real DuckDB/Parquet snapshot materialization, provider/event
retrieval, security-master or exposure publication, production data writes,
portfolio positions/heat, Groups, Book, Journal, remote hosting, authentication,
broker connections, or order execution.

The separate September security-master timestamp-precision publication blocker
remains deferred and does not authorize publication here.
