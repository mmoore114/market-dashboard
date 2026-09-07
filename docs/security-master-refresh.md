# Staged security-master refresh v1

This workflow is separate from `ingest_security_master.py`. The legacy CLI now
publishes only the master; its automatic exposure-publication step was removed by
the identity-boundary migration. The staged workflow never invokes that path, an
exposure builder, historical bars or engines.
Only `fetch` can construct a network client. All paths are local; staging must be
outside the repository and production storage, with no symlink components or
nested directories. Local paths and licensed reports remain outside Git.

## Modes and approval boundaries

`plan` requires an explicit snapshot date after July 26, 2026, positive request
budget, at least 1,000 records, source taxonomy/theme CSVs and the reviewed 23-row
crosswalk CSV. It reads July's database and Parquet to verify exact agreement,
copies input evidence/configuration into staging and hashes it. Existing identical
plans are reusable; different plans cannot overwrite a workspace. It performs no
provider requests or production writes.

Example commands below use operator-selected environment variables for local
paths. Setting these variables is not approval to fetch or publish.

```bash
.venv/bin/python scripts/refresh_security_master.py plan \
  --workspace "$REFRESH_WORKSPACE" --snapshot-date 2026-09-05 \
  --max-requests 20 --max-records 20000 \
  --taxonomy "$DEEPVUE_TAXONOMY" --themes "$DEEPVUE_THEMES" \
  --crosswalk "$PROPOSED_CROSSWALK"

# Requires separate bounded-fetch approval; not executed during implementation.
.venv/bin/python scripts/refresh_security_master.py fetch \
  --workspace "$REFRESH_WORKSPACE"

.venv/bin/python scripts/refresh_security_master.py validate \
  --workspace "$REFRESH_WORKSPACE"

# Requires separate production-publication approval.
.venv/bin/python scripts/refresh_security_master.py publish \
  --workspace "$REFRESH_WORKSPACE" --confirm-publication
```

`fetch` uses only GET `https://api.massive.com/v3/reference/tickers`, with stocks,
us, active=true, the explicit snapshot date, limit=1000 and ascending ticker sort.
It authenticates from the server-side local environment. Transport retries and
redirects are disabled. Pagination must stay on the same origin and exact path;
scope changes, credentials in next URLs, unknown query parameters and repeated
URLs are rejected. Pagination query strings/cursors are never saved.

Each request reserves room for a full 1,000-row page before it starts. Therefore
non-multiple record budgets may leave unused capacity, and a short page with a
next URL may still hit the conservative reservation cap. Attempts, including
failed requests, count against the request budget. A remaining next URL at either
cap makes the snapshot incomplete. Invalid first-page schemas/scopes stop before
another request. Completed pages survive HTTP, transport, schema and pagination
failures. HTTP diagnostics use the shared bounded redaction helper; transport
failures record a fixed category without exception text. A workspace with fetch
evidence cannot refetch automatically. Restart requires approval and a new
workspace; there is deliberately no cursor resume or hidden retry.

July's 13,023 rows imply approximately 14 pages at 1,000 rows/page; 20 requests and
20,000 records are proposed ceilings, not a promise about the new provider result.
Current endpoint entitlement and pagination behavior remain unverified until the
separately approved first request. A rejected or incomplete fetch must not publish.

## Offline validation and identity evidence

Validation checks the immutable input hashes, plan binding, every page hash and
count, request outcomes/budgets, normal pagination termination, record schema,
scope/date, ascending ticker order and conflicting duplicate keys. Every exact-case duplicate row is fatal. Provider ticker case is preserved
without normalization; non-unique casefold collision groups are diagnostic only. Optional
listing dates cannot be after the snapshot; provider update timestamps are parsed.
Missing required fields reject the snapshot rather than invent facts.

Staging outputs are:

- `plan.json`, copied inputs and `fetch.json` with sanitized request provenance;
- numbered page JSON artifacts containing only allowlisted reference fields;
- `security_master.parquet` using the existing 18-field master schema;
- `report.json` with request/page/raw/distinct/duplicate counts, active counts,
  snapshot date, type/exchange/classification-reason counts, missing/colliding
  composite and share-class FIGIs, and ticker differences from July;
- `taxonomy-reconciliation.csv` and `themes-reconciliation.csv`, preserving every
  source row/field and recording exact-symbol match status and denominator flags;
- `unapplied-crosswalk.csv`, preserving the 23 proposals, their original evidence,
  local July dual-FIGI evidence and explicit proposal/quarantine status;
- `validation.json`, binding input, page, report and candidate artifact SHA-256s
  and deterministic logical/exact content fingerprints.

Logical fingerprints sort columns and rows, normalize nulls and exclude
`ingested_at` and `last_updated_utc`. Exact fingerprints include every field and
are used for database/Parquet comparison. Identical staged validation reruns are
deterministic; collection timestamps remain provenance, not logical identity.

The versioned exact disposition lists seven `NON_SECURITY_MARKET_SERIES` and 22
`DEEPVUE_BREADTH_INDICATOR` identifiers. No regex generalizes this to new symbols.
All source records remain preserved; the 29 are explicitly excluded from matching
and denominators. Blank theme placeholders remain source rows, not securities.
The accepted taxonomy totals are 11,370 source rows, 29 non-security records,
11,341 security candidates, 5,462 classified and 5,879 unclassified candidates.

The 231 previously identified current/new supported identities are assessed by
exact source ticker against the newly fetched snapshot. They are not appended
from prior lookup reports. Any still absent identifiers remain unmatched.
All 23 crosswalks remain unapplied: 21 ordinary proposals, NXH to BBBY quarantined
for exchange review, SEPQ to TUGN quarantined for CIK review. TUNG is not a
candidate. STLN to TOI and VMRK to EQR remain ordinary reviewed proposals.
Dual-FIGI evidence is checked against exactly one July row; missing or conflicting
evidence is reported unresolved, never replaced by name similarity. A proposal
can match a current snapshot ticker naturally without applying a historical alias.

FIGI absence/collisions and unknown classification codes are review findings,
not automatic identity merges or instrument exclusions. They do not by themselves
invalidate a well-formed provider snapshot. Review these reports before granting
publication approval; classification policy itself has not changed.

## Recoverable offline publication

Publication additionally requires established reader compatibility and
deterministic exact-case conversion. Failed exact round trips or unsafe readers
block publication with no CLI override. Collision reports alone are not blockers
under v2 exact-case precedence; reverse casefold fallback stays prohibited. See
[the identity audit](security-master-case-audit.md). It also requires
`--confirm-publication`, an unchanged validated receipt and
its exact artifacts. Before writes, it verifies July's logical content, every
field against DuckDB and original Parquet bytes. It targets only the new date.
The production database must already exist. No exposure table is modified.

1. Copy the validated Parquet to a pending file in the target partition, fsync it
   and verify its hash against the receipt.
2. In one DuckDB transaction replace only the target date and insert a `pending`
   row in the separate `security_master_publication` table.
3. Atomically rename Parquet, fsync the directory, verify every DuckDB/Parquet
   field and recheck July. Mark the publication `complete`.
4. Failure after database commit leaves `pending` on process death or
   `recovery_required` on a caught failure. Rerunning publication with the original
   exact validated artifact completes recovery. A different artifact is rejected.
   Failure before commit leaves the original database unchanged.

An identical same-date logical artifact is a no-op after checking existing
DuckDB/Parquet equality; existing timestamps and bytes are retained. Different
same-date logical content is rejected unless a separately approved revision
supplies `--authorize-revision EXISTING_LOGICAL_FINGERPRINT`. This argument must
be the exact old fingerprint, not a boolean. An orphan existing Parquet partition
is rejected for manual recovery.

DuckDB and the filesystem do not share an atomic transaction. Existing readers do
not yet enforce the new state table: publication/recovery must occur in a
maintenance window, with consumers held until `complete`. Interrupted publication
must be recovered before other changes. Adding a universal reader publication
gate is a separate compatibility decision, not part of this workflow.

## Implementation validation boundary

Tests use mocked HTTP responses and temporary synthetic production databases.
They explicitly block HTTP sends/socket connections for plan, validate and publish
and check zero calls, including interrupted publication recovery. No real fetch,
production publish, crosswalk application, ingestion, commit or push is part of
implementation validation. Separate approval is required for the bounded fetch;
review its complete validation/reconciliation reports before any publication.

## Reference-to-market-data compatibility projection

The [versioned identity boundary](security-identity-boundary.md) supersedes the
blanket mixed-case publication block. Validation now produces a separate
`compatibility-projection.csv` and compatibility counts without changing the exact
reference Parquet. Both master publication paths block failed exact conversion or
an unresolved reader migration; v2 preserves uppercase exact precedence and
retains collision evidence without allowing reverse casefold fallback. Legacy master ingestion no longer automatically
publishes exposure classifications. Uppercase bar/feature/trading invariants are
unchanged; their reference adapters use the explicit projection.


## Current-foundation precision publication

AP-CURRENT-FOUNDATION-001 completed the separately authorized September publication.
The confirmed publisher preserves UTC nanoseconds in `last_updated_utc` using
TIMESTAMP_NS. A transactional exact-DDL replacement retains July values, table
constraints and index definitions; raw September Parquet bytes are unchanged.
First publication, interruption/recovery, identical no-op, changed-date-content
refusal and July preservation passed against the immutable real artifact before
production publication. See [current foundation V1](current-foundation-v1.md)
for exact counts, fingerprints, backups and the independent verification result.
