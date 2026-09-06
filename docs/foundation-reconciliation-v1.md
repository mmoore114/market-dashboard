# Offline foundation reconciliation V1

AP-FOUNDATION-RECONCILE-001 reconciles the exact original eight local audit
findings. One finding is resolved by verified evidence; seven remain blocked.
This is not a successful materializer audit or authorization to build a snapshot.

## Workflow and authority

`scripts/reconcile_foundation.py` provides `reconcile-plan`, `reconcile`, and
`reconcile-validate`. The frozen `ReconciliationPlanV1` embeds the original
materialization plan, exact audit receipt SHA256, explicit local evidence and
legacy ingestion-receipt selections, protected-file inventory, and output name.

The CLI accepts literal JSON so **planning performs zero file/database reads and
zero writes**. In the example, the shell reads the explicitly selected plan before
invoking the CLI; that shell read is not part of plan mode. Programmatic callers
can supply the frozen model directly to `describe_reconciliation`.

```bash
.venv/bin/python scripts/reconcile_foundation.py reconcile-plan \
  --plan-json "$(cat "$FOUNDATION_PLAN")"
.venv/bin/python scripts/reconcile_foundation.py reconcile \
  --plan-json "$(cat "$FOUNDATION_PLAN")"
.venv/bin/python scripts/reconcile_foundation.py reconcile-validate \
  --plan-json "$(cat "$FOUNDATION_PLAN")"
```

Production reads reuse the bounded materializer readers: read-only DuckDB,
external access disabled, one thread, 512 MiB query-memory limit, exact table and
bound selection values, explicit Parquet copies and no-follow file reads.
Reconciliation verifies the original receipt digest, original plan fingerprint,
and every original source hash. Previously absent sources must still be absent;
new or changed publications require a new scope rather than silently replacing
this audit's inputs. Unpublished provider staging cannot supply evidence.

The output is one private, deterministic JSON bundle directly beneath the existing
`aperture-staging/workstation-local-snapshot-v1` workspace. Existing files cannot
be replaced. Sections contain the resolved plan, input/hash receipt, conserved
ledger, copy comparisons, calendar evidence/candidate, provenance matrix and
candidate manifest, universe prerequisites, identity intersection, coverage,
next actions, and before/after preservation proof. Opaque hashes protect the
explicit environment/settings/provider-staging files without parsing their
contents or admitting them as research evidence. No market rows, local paths,
private manifests or reports belong in Git.

Validation checks the bundle digest, then independently recomputes all evidence,
including source hashes and the exact eight dispositions. Changing findings and
resealing only the report does not bypass it. Receipts establish reproducibility
and drift detection, not cryptographic provider authentication. Code, runtime
versions, local sources, and any installed calendar implementation must remain
consistent for identical evidence. Exit zero means reconciliation/validation
succeeded; it does **not** mean the workstation is build-ready.

## Exact finding ledger

Finding identity is `(source, code)`; repeated codes are not merged.

| Original source and code | Disposition | Evidence and bounded action |
|---|---|---|
| bars / DUCKDB_PARQUET_DISAGREEMENT | REQUIRES_LOCAL_REVIEW | Same 63,279 keys; 11,607 volume differences. Review volume representation and source semantics before separately authorizing any correction. |
| calendar / SOURCE_MISSING | REQUIRES_LOCAL_REVIEW | Neither supported calendar package is installed and the declared artifact is absent. Supply a reviewed, pinned offline calendar implementation; dependency acquisition needs separate authority if no wheel is available. |
| manifest / SOURCE_MISSING | REQUIRES_LOCAL_REVIEW | No complete price/dividend/matching-volume or publication attestation. Review the field-by-field unknowns and actual local receipts; do not self-attest. |
| spot / SOURCE_MISSING | REQUIRES_BOUNDED_ACQUISITION | `$VIX` non-security identity contract exists, but provider/dataset/source symbol is unknown. Select that exact identity before issuing a capped spot-history request plan. |
| universe / DUCKDB_PARQUET_DISAGREEMENT | RESOLVED_BY_VERIFIED_EVIDENCE | All 13,023 keys and all fields agree under explicitly versioned lossless DATE equivalence. No dataset repair is warranted by this finding. |
| universe / LEGACY_UNIVERSE_NOT_EQUITY_RESEARCH | REQUIRES_PUBLICATION | Dated market cap, complete identity intervals, effective sessions and prior trade membership are unavailable. Obtain those prerequisites before candidate generation and separately approved publication. |
| security_master / MASTER_SNAPSHOT_AFTER_AS_OF | REQUIRES_LOCAL_REVIEW | Latest bars precede the earliest selected master/exposure date. Choose an identity-valid target and necessary approved inputs; never project July 26 backward. |
| bars / REQUIRED_MARKET_SERIES_MISSING | REQUIRES_BOUNDED_ACQUISITION | QQQE is absent from both stores. The private conditional aggregate specification covers only QQQE; it authorizes zero requests. |

The JSON ledger uses the full required `REMAINS_BLOCKED_...` state names.
One separate new finding, `APERTURE_RULES_AFTER_CANDIDATE_T`, records that immutable
`aperture-rules-v1` becomes effective August 25, after candidate T=July 24.
The original population remains exactly eight.

## Copy comparison evidence

All 100 declared bar Parquet files were compared against DuckDB across every
column, including timestamps and optional fields. Both stores have 63,279 rows
from January 2, 2024 through July 24, 2026, with no store-only keys, duplicate
keys, required OHLCV nulls, or invalid OHLCV. Only volume differs: 11,607 fractional
Parquet values equal the DuckDB values after rounding, with maximum absolute
difference 0.5. The current writer declares DuckDB volume as BIGINT. This is
consistent with coercion; it does not independently prove provider semantics or
select a canonical copy. Both original stores remain untouched.

The universe has 13,023 rows in both stores with no missing keys or field-value
mismatches after lossless DATE normalization. Its original logical digests differ
because the materializer normalizes only `date` and `snapshot_date`, while other
schema-declared DATE fields can arrive as Python dates or midnight timestamps.
`foundation-date-equivalence-v1` names the additional legacy DATE columns, rejects
non-midnight/timezone-bearing values, and preserves all other timestamp precision.
Raw fingerprints, normalized fingerprints, storage dtypes and representation
changes are reported separately. No tolerance, rounding, timestamp truncation,
or row omission is used to establish universe equality. Numeric comparison also
preserves exact integer values above `2**53`; mixed integer/float columns cannot
hide differences through vectorized float coercion.

This comparison version is local to reconciliation. Existing materializer
fingerprints and historical audit receipts retain their original meaning; their
comparison behavior has not been changed. A subsequent materializer integration
must explicitly adopt the reviewed DATE equivalence before that original
representation finding disappears from a newly generated audit. The separate
missing Aperture schedule continues to prohibit a build either way.

July's master and exposure copies agree across all fields. Exposure-policy-v3
has a native complete publication with matching count and classification
fingerprint. Complete master publication/validity attestations remain unknown;
file agreement does not manufacture them.

## Calendar, provenance, population and coverage

Only installed `exchange-calendars` or `pandas-market-calendars` implementations
can generate an XNYS candidate. The bundle records package version, timezone,
exact sessions and aware closes, early closes, candidate digest and exact T/T+1
adjacency. Observed bar dates are never an exchange calendar. On this machine,
both implementations and the explicitly declared calendar artifact are absent;
therefore missing-session counts, exact warmup and expected acquisition rows
remain null, even for series with many observed rows.

The local ingestion receipt contains 100 records: 95 completed and five
skipped-current. Its actual job timestamps and request bounds are retained.
The current client endpoint/adjusted flag and writer's integer declaration are
hashed configuration evidence only. They cannot attest dividend treatment,
matching split-adjusted volume, complete artifact observation/fetch/publication
times, identity validity, or freshness. The incomplete candidate manifest is
explicitly not a `ManifestV1` and cannot be loaded as approved provenance.

Aperture research/trade rules are `aperture-universe-v1`, defined by the immutable
rules file and pure `evaluate_universes`. Legacy eligibility is never substituted.
The selected master has no market-cap column; complete dated input/interval and
prior trade-membership evidence are also absent. No candidate schedule was made.
The necessary intersection is empty even before those further checks: all bar
sessions are on/before July 24 and selected master/exposure snapshots are July 26.
There are **zero feasible T/T+1 pairs** with these selected artifacts.

SPY, QQQ, IWM and RSP each have 642 observations in both stores over the recorded
bar range. QQQE has zero. Copy selection does not change their observed session
coverage. Calendar gaps/warmup and the research denominator remain UNKNOWN.
Spot is a separate `spot-volatility-identity-v1` / `$VIX` /
`spot_implied_volatility_points` contract, with no inferred security, ETF, or
futures proxy.

The conditional QQQE specification spans January 2, 2024 through July 24, 2026:
one aggregate request maximum, no retries/redirects, and a conservative 935-record
calendar-day ceiling. Expected exchange-session rows remain unknown pending the
calendar. These are audited historical coverage bounds, not a proposal to extend
all data to a guessed new T. Choosing a later valid T requires a revised plan.
The spot specification preserves the same diagnostic bounds but has request cap
zero until provider identity/endpoint is established. Research acquisition has
request and record caps zero until a valid population exists. No specification
is executable or approved by this milestone.

## Observed validation and next action

The actual plan fingerprint is
`da2aea802c5c9bad05dc49d191daa094950c4e3ecad56f99d6eb2d61dc19aaf2`.
The independently recomputed private evidence fingerprint is
`15e72badc9e2456a861a11b3bf4ba4d21fe05a1aa2a17cc2ced43586cfe5cd00`.
All 344 explicitly protected pre-work files matched their original hashes.
This includes the previous audit evidence in addition to production data,
September provider staging, environment and settings.

The exact next bounded action is an **offline operator review of the staged
volume/provenance matrix and calendar-source selection**. Decide the volume
convention supported by existing source evidence and select a pinned XNYS
implementation. Unsupported semantics stay unknown. If acquiring a calendar
package or source documentation is necessary, issue a separately bounded
assignment. Do not repair/publish data, acquire market history, or retry a real
snapshot build under this assignment.

See PROJECT_STATE for final observed regression totals. Focused tests cover
zero-I/O planning, blocked network access, read-only native storage, no-clobber
staging, conserved findings, date/timestamp distinctions, invalid/null/duplicate
rows, early closes, absent benchmarks/spot, identity intervals, deterministic
receipts, resealed-report tampering and protected-file preservation. Existing
Python, API/schema, frontend and synthetic browser regressions remain required.
