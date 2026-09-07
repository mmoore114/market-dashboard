# Offline local Workstation materializer V1

AP-LOCAL-MATERIALIZER-001 connects explicitly selected local publications to the
existing pure engines and normalized Workstation V2. It performs no provider
lookup, source publication, repair, exposure/universe rebuild, or trade execution.
The actual laptop audit is **blocked**; no real snapshot was produced.

## Four modes

Prepare an operator-reviewed JSON `MaterializationPlanV1` outside production
storage. The frozen schemas are in
`src/market_dashboard/workstation/materialization/contracts.py`; all reject extra
fields and retain exact-case identities. Paths in a plan must be absolute. The
examples use operator-selected variables, not committed machine paths.

```bash
.venv/bin/python scripts/materialize_workstation_snapshot.py plan --plan "$LOCAL_PLAN"
.venv/bin/python scripts/materialize_workstation_snapshot.py audit --plan "$LOCAL_PLAN"
# Only after an audit with zero HARD_BLOCKER findings:
.venv/bin/python scripts/materialize_workstation_snapshot.py build \
  --plan "$LOCAL_PLAN" --receipt "$LOCAL_WORKSPACE/audit-receipt.json" \
  --plan-fingerprint "$EXACT_PLAN_FINGERPRINT"
.venv/bin/python scripts/materialize_workstation_snapshot.py validate \
  --snapshot "$LOCAL_WORKSPACE/review.local-snapshot.json" \
  --receipt "$LOCAL_WORKSPACE/build-receipt.json"
```

`plan` reads the supplied plan document, validates arguments/path layout, lists
required and absent optional roles, fingerprints the resolved plan, and prints
an exactly shell-quoted next audit command. It opens no source file/database,
makes no network request, and creates no directory or output. File hashes and
row/date bounds are deliberately verified during audit, not guessed in plan.

`audit` reads only declared artifacts and explicit peer copies, then checks source,
identity, publication, basis, calendar, population and replay gates. It writes
`readiness.json` and `audit-receipt.json`, with identical deterministic logical
content. It attempts pure replay only after foundational checks pass. A size or
canonical replay failure becomes a hard blocker; measured component sizes are
retained when the 24 MiB target is exceeded. Exit code 2 means blocked/refused;
zero means the requested operation succeeded.

`build` requires that exact successful audit receipt and plan fingerprint. It
checks every source byte hash before reading, independently repeats readiness
checks, replays, compares the audit/build logical output, and checks all source
hashes again. A source change requires a new reviewed audit; it is never accepted
by relabeling an old receipt. Existing output/report files are not overwritten.

The complete V2 result and canonical Decision/Risk parity are checked before
publication. A same-directory temporary JSON file is flushed/fsynced and loaded
through `SnapshotStore` before Linux `renameat2(RENAME_NOREPLACE)` atomically
publishes the target. The directory is fsynced. Unsupported no-replace rename
fails closed. Caught failures clean temporary and newly created output/receipt
files and preserve only a sanitized failure receipt. Process death can leave a
hidden temporary file, or an output without its build receipt; neither is a
validated build. Do not manually promote it. Inspect and remove only that failed
build's artifacts before a separately requested retry. Existing user artifacts
are preserved, including in a competing-writer race.

`validate` requires only the standalone V2 file and build receipt. It verifies
receipt/output hashes, byte limits, V2 graph integrity, logical digest, versions,
rules, exact record/funnel counts and every recorded canonical output field hash.
It independently recomputes Decision/Risk, extension, events and sizing from the
snapshot's canonical inputs. Historical Structure/Setup/Leadership/Regime replay
is bound by the audit and field hashes; a standalone snapshot does not contain
all historical source bars. Hash receipts detect corruption and drift; they are
not cryptographic authentication of a provider or protection against a caller
forging all inputs and receipts together.

## Explicit source contract

A plan records `artifacts`, `workspace`, `output`, `as_of_session`, exact
`action_session`, aware `freshness_deadline`, `VersionsV1`, and operating limits.
Each `ArtifactV1` names a role, logical version, exact `paths`, format, optional
allowlisted SQL table and equality selections, and explicit `parquet_copies`.
SQL values use bound parameters; identifiers are restricted. No SQL expression,
view-based external read, repository scan, filename-based identity join, or table
name-based adjustment inference is used.

| Role | Required representation and use |
|---|---|
| bars | DuckDB table or explicit Parquet file list; exact `ticker,date,open,high,low,close,volume`, optional UTC bar timestamps and basis columns |
| spot | Separate DuckDB/Parquet `series_id,date,close`; versioned canonical spot-volatility identity in the manifest, never an equity/master lookup |
| calendar | `CalendarV1`: explicit ordered sessions and one aware actual close per session, including early closes; identity/version and byte hash |
| manifest | `ManifestV1`: explicit source/basis, matching split-adjusted-volume attestation, spot identity, calendar hash and source bindings |
| security_master | Complete exact dated reference snapshot, including mixed-case rows; `ticker,snapshot_date`, optional display name, exact peer copies |
| exposure | Published snapshot with exact ticker/date/policy/scope; native DuckDB use additionally requires explicit `publication_table` |
| universe | `UniverseScheduleV1`: dated `ResearchUniverseV1` revisions plus exact existing `UniverseMemberships`, master/exposure versions and immutable Aperture rules hash |
| taxonomy / themes | Optional published `GroupScheduleV1` of dated canonical SUB_INDUSTRY/THEME memberships, explicit catalog and exact reconciled security members |
| events | Optional `EventsV1` containing canonical event records and symbol-scoped coverage |
| proposals | Optional `ProposalsV1`: exact symbol/direction, T/T+1, aware observed-at, caller provenance and nullable canonical sizing proposal |
| corporate_actions | Optional explicit dated QA records with observation time and evidence; absent QA remains UNKNOWN, quarantining EP |

A `SourceBindingV1` binds each source except the manifest itself to its ordered
artifact hashes (primary paths then peer copies), all-column logical fingerprint,
row count/date bounds, `complete` publication state, observation/fetch/publication
timestamps, valid identity interval, freshness deadline, and exact master,
exposure and universe-policy versions. The manifest itself is hashed in the audit.
Its explicit source contract records provider/dataset, split-adjusted prices,
dividend treatment and matching volume convention. A legacy ingestion manifest's
`adjusted=true` flag is insufficient. Missing bindings or differing copies block.

Tabular logical fingerprints include every column and exact non-session timestamp
precision. Session-date fields normalize DATE and midnight timestamp storage
representations; other timestamp precision differences remain detectable.
Physical file hashes additionally bind all bytes, including future rows excluded
from T replay. Manifest hashes must describe the complete selected input slice.

Native exposure publication checks require one `complete` publication row, its
expected row count and the existing canonical classification fingerprint. This
also checks DuckDB/Parquet equality when those copies are declared. Legacy master
storage lacks a universal publication-state reader: a complete source attestation
and exact copies are required, never an inferred completion from file existence.
The September staged master remains forbidden input. Its nanosecond/microsecond
publication issue is neither repaired nor bypassed. Earlier master snapshots
must be dated no later than T and have an attested valid interval covering T;
their age is retained when the attestation is available.

The broad legacy `swing_universe_snapshot` is accepted for **audit diagnostics
only**, to report its row/date/hash/copy state. It always produces
`LEGACY_UNIVERSE_NOT_EQUITY_RESEARCH`; it cannot be relabeled as the new two-
universe contract. Preparing/publishing those memberships is a separate data task.

Exact `ReferenceTicker` conversion uses the existing complete compatibility
boundary. Case collisions must match explicitly documented collision groups.
There is no uppercasing, casefold join, FIGI/name alias, proposed crosswalk, raw
Deepvue read, or inferred hierarchy. Unmatched/contradictory supplied memberships
are blockers. Raw source reconciliation and non-security disposition must occur
in the existing publication workflow before supplying standardized groups.

## Replay and gaps

```text
explicit verified local artifacts
  -> full symbol history -> canonical Structure and Setup replay
  -> dated cross-section -> canonical strength, groups and rank history
  -> every prior supplied session -> canonical five-sleeve Regime and memory
  -> exact T + caller's next calendar session -> Decision/Risk
  -> streamed SymbolRecordV1 -> materialize_v2 -> strict standalone loader
```

The orchestrator calls existing feature adapters and pure engine functions. It
introduces no alternative ATR, average, return, state, rank, gate or sizing
formula. Structure/Setup replay processes one symbol's history at a time. Only
small optional leadership contexts and final Structure evidence survive that
pass. Daily cross-sectional/regime populations are released as replay advances;
group history retains the needed 20-session window. The final per-symbol Setup
replay and Decision/Risk output are streamed into V2, so no full duplicated V1
population is retained per symbol. Replay itself opens no files and is tested
with file APIs and network transport blocked.

Structure/Setup require 250 prior rows, obtained from the immutable Structure
threshold object; Leadership's longest horizon requires 253 calendar slots.
Regime index/breadth require the existing 50-session average, style its 21-session
endpoint return, and spot its 20-session mean. Coverage lists required/valid/
missing counts, first/last observations and actual calendar gaps. Departed research
members are checked through their last effective member session; no post-departure
history is invented or required. Missing calendar
or universe evidence prevents a truthful denominator/engine-coverage calculation;
audit reports the foundation blocker instead of inventing a calendar/population.
Future bars are excluded before numerical and identity adaptation, so mutating
T+1 cannot rewrite T. Source bytes remain bound independently.

An important existing contract limit is explicit: Decision/Risk checks
Structure `prior_sessions` and Setup instance indices against the **shared
calendar index**, while existing bar adapters index supplied rows. A later-listed
symbol or an internal missing bar can make these contracts disagree. This
materializer reports `REPLAY_CALENDAR_INDEX_UNREPRESENTABLE`; it never shifts
indices, fills prices, synthesizes sessions, suppresses the symbol, or infers
whether a missed setup failure occurred. A contiguous short common calendar
prefix is representable: canonical insufficient-history evidence remains present
for every research member. Supporting heterogeneous listing/gap histories needs
a separately reviewed adapter/engine identity amendment or verified missing data.

Optional missing groups, corporate-action QA, earnings or proposals are evidence
gaps, not automatic whole-snapshot blockers. The canonical engine controls each
UNKNOWN/refusal. Earnings CLEAR requires fresh complete explicit coverage through
T+5; an empty event list alone is insufficient. Event/proposal identities and
observations are validated, and future event revisions cannot establish past
clearance. No entry, stop, account equity or buying power is invented. LONG rows
are retained for the complete research population; an explicitly supplied SHORT
proposal adds its exact direction. SHORT promotion remains capped by existing
policy. Interactive Sizer continues to use canonical what-if sizing.

Only LOCAL_SNAPSHOT is produced. FRESH requires a not-expired explicit deadline
supported by every required source's freshness attestation; otherwise the artifact
is STALE. No session TTL is invented. The live loader rechecks expiry and refuses
historical routes while preserving health. Generating a new timestamp cannot
make stale source evidence current. Operational generation time is excluded from
the existing logical snapshot fingerprint; evidence availability timestamps and
source hashes remain binding provenance.

## Operating limits and receipts

Defaults: 2,000 current/historical distinct research symbols, two million selected
rows per tabular source, 2 GiB per explicitly read source file (configurable only
within schema bounds), one-symbol Structure/Setup batches, 512 MiB read-only
DuckDB query memory, 24 MiB uncompressed materializer target and unchanged 32 MiB
loader ceiling. Overflow fails; no ranked/promoted subset replaces the population.
Receipts expose output/component bytes, per-engine coverage, source/rules hashes,
records/sessions/symbols, funnel, gap count, canonical field hashes, replay timing
and process peak RSS. Timing/RSS are diagnostics, not performance guarantees.
The normalized loader still creates its private decoded cache; its measured scale
behavior remains documented in the V2 contract.

Inputs use no-follow reads and O_NOATIME where supported/permitted. DuckDB opens
strictly read-only with external access disabled, one thread and a memory bound;
it creates no WAL, checkpoint or production temporary table. DuckDB's internal
file-open atime behavior remains OS-dependent; the code does not restore atime
by writing source metadata. Source bytes are hashed before and after.

Output must be standalone outside the repository/production/provider workspaces.
The prescribed `aperture-staging/workstation-local-snapshot-v1` layout is narrowly
accepted by the live loader; other staging and Deepvue paths remain refused. JSON
content must still pass the full V2 contract. Machine paths, source rows, raw
provider artifacts, financial proposals and credentials stay outside Git.
Diagnostics never copy exception text from libraries or proprietary row values.

## Observed laptop readiness — 2026-09-06

One plan and one read-only audit used the configured local database, July 26
master/exposure/legacy-universe slices, and explicit peer Parquet files including
100 adjusted bar files. The candidate T was the recorded last adjusted session,
2026-07-24; candidate action 2026-07-27 could not be certified without a supplied
calendar. The candidate deadline was historical, not a current/live assertion.

- Adjusted bars: 63,279 rows, 2024-01-02 through 2026-07-24, zero duplicate keys
  and zero required OHLCV nulls; exact DuckDB/Parquet content disagrees.
- July 26 master: 13,023 rows, zero duplicate/null identity keys, exact copies
  agree; its date follows the candidate T, so it cannot establish T identity.
- Exposure-policy-v3: 13,023 rows; native publication complete, existing
  publication count/fingerprint verified and exact copies agree.
- Legacy policy-v3 universe slice: 13,023 diagnostic rows, zero duplicate/null
  keys, exact copies disagree; it is not a dated Aperture research/trade schedule.
- Explicit calendar, adjustment/provenance manifest and spot-volatility paths
  are missing. One mandatory benchmark is absent from adjusted bars; the selected
  Parquet-copy inventory also lacks QQQE. Without
  calendar/research membership, per-engine denominator coverage is unverifiable.
- Five optional source gaps: taxonomy, themes, events, proposals and corporate
  actions. These do not independently prohibit a truthful snapshot.

Result: **8 hard-blocker findings**, five optional evidence gaps. No real build,
validation/startup against real data, repair, ingestion or publication occurred.
All **337 protected files (112,487,134 bytes)**, including production data,
September security-master staging, environment file and user VS Code settings,
had identical before/after SHA256s. Git status and working diff also matched
exactly across the audit. Private `plan.json`, `resolved-plan.json`, readiness/
receipt, command result and preservation proof remain in the authorized local
workspace. They are intentionally not committed.

Plan fingerprint:
`24409534801c6498d2351378ed65e83b704b4ab5abecf28c86f714576c2b609c`.
Audit receipt fingerprint:
`f298ad3c7d4afedc7241a361428b75912887995a2d2710bb878c56a0a959d61b`.

The next bounded data action is a separately scoped **offline foundation
reconciliation**: identify the authoritative adjusted-bar and legacy-universe
copies, provide an authoritative exchange calendar and reviewed basis/publication
manifest, and establish a published identity-valid Aperture research/trade schedule
for an explicitly selected T. Then assess exact missing benchmark/spot/research
coverage under that calendar. Any repair, membership publication or bounded fetch
requires its own assignment/authority. Do not retry this blocked build or consume
the unpublished September artifact.

## Verification commands

```bash
.venv/bin/python -m pytest tests/test_materialization.py tests/test_workstation.py tests/test_workstation_v2.py tests/test_workstation_scale.py -q -s
.venv/bin/python -m pytest -q
.venv/bin/python -m api.export_openapi --check
.venv/bin/python -m api.export_snapshot_schema --check
.venv/bin/ruff check src/market_dashboard/workstation scripts/materialize_workstation_snapshot.py tests/test_materialization.py tests/materialization_fixtures.py
.venv/bin/ruff format --check src/market_dashboard/workstation scripts/materialize_workstation_snapshot.py tests/test_materialization.py tests/materialization_fixtures.py
npm --prefix web test
npm --prefix web run typecheck
npm --prefix web run build
npm --prefix web run lint
cd web
npm run test:browser
cd ..
git diff --check
```

The Python tests cover four modes, explicit plans, native read-only storage,
publication/identity/basis/calendar gates, missing evidence, dated membership
revisions, canonical full-history parity, future mutation, field/receipt tampering,
atomic failure cleanup, no-clobber publication, normalized bounds and API refusal.
Existing workstation scale, component, desktop/mobile browser and contract
regressions remain required. See PROJECT_STATE for final observed test totals.
