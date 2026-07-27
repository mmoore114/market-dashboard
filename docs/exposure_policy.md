# Versioned exposure policy

Massive ticker-reference fields are provider facts. In particular, the raw
`ETF` and `ETS` codes describe provider instrument types; they are not treated
as conclusive evidence that a product is or is not tied to one security.

Economic exposure is derived separately and keyed by provider snapshot date,
ticker, and policy version. The current policy identifier is
`exposure-policy-v2`.

## Exposure scopes

- `direct_equity`: an ordinary common stock. Existing common-stock behavior is
  unchanged.
- `single_security`: a fund or wrapper whose economic exposure is primarily one
  company/security. It is structurally excluded with reason
  `Single-security product excluded from core swing universe`.
- `diversified`: an index, sector, country, asset-class, commodity, rates,
  volatility, digital-asset, or diversified-basket product. Leveraged or
  inverse wording does not by itself change this classification.
- `non_equity`: an instrument outside the established common-stock/ETF core
  policy.
- `review_needed`: suspicious or unresolved exposure. It is excluded with
  reason `Exposure classification requires review`.

## Deterministic precedence

1. A dated explicit override.
2. The maintained classification registry.
3. A high-confidence name rule that extracts one underlying and validates that
   underlying against the same provider snapshot.
4. Raw provider type as a signal.
5. Conservative review status for unresolved suspicious products.

Issuer identity alone and generic words such as `2X`, `Bull`, `Bear`, `Long`,
`Short`, or `Daily` are never sufficient for single-security classification.

The maintained registry and overrides live in `config/exposure_policy.yaml`.
Overrides require a ticker, effective start, optional effective end, scope,
reason, and provenance. Overlapping definitions are rejected. Overrides are
the mechanism for intentional inclusion, exclusion, or review decisions.

## Rebuild workflow

For a new policy version:

1. Preserve the original provider snapshot.
2. Review and update the maintained registry and dated overrides.
3. Run `scripts/build_exposure_classification.py`.
4. Run `scripts/validate_exposure_classification.py`.
5. Build a swing-universe snapshot with the same `policy_version`.
6. Validate that no `single_security` or `review_needed` row entered the core.
7. Build and validate an adjusted-backfill plan carrying that version.
8. Dry-run bounded ingestion selections before any real request.

Derived Parquet paths include both snapshot date and policy version. New
DuckDB tables use policy-versioned stable keys. When a future authorized build
first upgrades existing unversioned tables, old rows are labeled
`legacy-policy-v1`; legacy universe rows are conservatively marked
`review_needed`. They remain auditable but are not treated as v2 conclusions.
The v2 universe and plan must then be rebuilt explicitly.

## Recoverable DuckDB and Parquet publication

DuckDB commits and filesystem renames cannot participate in one atomic
transaction. Exposure classifications therefore use an explicit publication
record keyed by `snapshot_date` and `policy_version`. Its controlled states are
`pending`, `complete`, and `recovery_required`. The record also stores the
expected row count, a deterministic logical SHA-256 fingerprint, the exact
final and staged Parquet paths, and a sanitized failure message.

Normal publication is:

1. Validate, canonicalize, and fingerprint the complete in-memory result.
2. Write and flush a same-directory staged Parquet file.
3. In one explicit DuckDB transaction, create the required tables, mark the
   publication pending, upsert its complete classification slice, remove stale
   rows for that identity, and record its count and fingerprint.
4. Atomically replace the final Parquet file with the staged file.
5. Compare every persisted field, stable key, row count, and fingerprint
   between DuckDB and the exact Parquet file.
6. Mark the publication complete in a short second DuckDB transaction.

Before the first DuckDB transaction commits, any exception rolls back the
entire slice and removes the staged file; an older complete publication remains
usable. After that commit, the committed DuckDB slice and recorded fingerprint
are authoritative for recovery. The state is never complete until the final
Parquet file has been verified. A failure in the post-commit window records
`recovery_required`, and downstream universe builds refuse to consume it.

Recover exactly one interrupted identity with:

```bash
python scripts/build_exposure_classification.py \
  --snapshot-date YYYY-MM-DD \
  --policy-version exposure-policy-v2 \
  --recover
```

Recovery validates the committed DuckDB slice against the recorded count and
fingerprint. It publishes a valid staged file when available, otherwise
regenerates Parquet deterministically from DuckDB. It also handles a final file
that was published before interruption and repairs a mismatched final file.
Recovery touches no other snapshot or policy partition and is idempotent.

After recovery, run:

```bash
python scripts/validate_exposure_classification.py \
  --snapshot-date YYYY-MM-DD \
  --policy-version exposure-policy-v2
```

The validator resolves only that policy-versioned path and checks publication
state, recorded count and fingerprint, duplicate and missing/extra keys,
field-level DuckDB/Parquet agreement, unexplained staged files, and extra
Parquet files. It reports disagreement and exits nonzero; it never repairs.
The swing-universe builder independently repeats the completeness and
cross-store agreement gate before reading classifications.
