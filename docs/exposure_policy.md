# Versioned exposure policy

Massive ticker-reference fields are provider facts. In particular, the raw
`ETF` and `ETS` codes describe provider instrument types; they are not treated
as conclusive evidence that a product is or is not tied to one security.

Economic exposure is derived separately and keyed by provider snapshot date,
ticker, and policy version. The configured default is `exposure-policy-v3`.
The published `exposure-policy-v2` configuration and output remain immutable
and explicitly selectable.

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

The immutable v2 registry lives in `config/exposure_policy.yaml`. V3 lives in
`config/exposure_policy_v3.yaml`, explicitly extends v2, and adds only dated
review resolutions. The generic loader expands those resolution groups into
ordinary overrides before constructing the policy.
Overrides require a ticker, effective start, optional effective end, scope,
reason, and provenance. Overlapping definitions are rejected. Overrides are
the mechanism for intentional inclusion, exclusion, or review decisions.

## Policy v3 review resolutions

The completed 2026-07-26 review resolved all 136 products that v2 withheld as
`review_needed`. Mutating v2 would have invalidated its published fingerprint
and audit history, so the decisions created `exposure-policy-v3`:

- 85 `single_security`
- 37 `diversified`
- 14 `non_equity`
- 0 `review_needed`

Every resolution is effective from 2026-07-26 and records
`manual_issuer_prospectus_review_2026-07-26` provenance. Single-company
wrappers carry their validated underlying ticker and remain excluded from the
core universe, including option-income, WeeklyPay, leveraged, inverse, and
autocallable wrappers tied to one company.

ETF-on-ETF exposure follows the referenced fund's economic breadth: ARKK,
DRAM, and XOVR wrappers remain diversified because their reference products
hold multiple securities. Multi-company option-income funds and portfolios of
autocallables are also diversified; option-based or leveraged construction
alone does not make a product single-security. Crypto, commodity, and Treasury
products are `non_equity`.

The default policy path is configured in `config/settings.yaml`. Commands can
reproduce v2 or select v3 explicitly:

```bash
python scripts/build_exposure_classification.py \
  --snapshot-date YYYY-MM-DD \
  --policy-config config/exposure_policy.yaml

python scripts/build_exposure_classification.py \
  --snapshot-date YYYY-MM-DD \
  --policy-config config/exposure_policy_v3.yaml
```

Future manual resolutions must create another immutable policy file with a new
version. They must not edit the meaning of a policy that has already been
published.

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
  --policy-version exposure-policy-v3 \
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
  --policy-version exposure-policy-v3
```

The validator resolves only that policy-versioned path and checks publication
state, recorded count and fingerprint, duplicate and missing/extra keys,
field-level DuckDB/Parquet agreement, unexplained staged files, and extra
Parquet files. It reports disagreement and exits nonzero; it never repairs.
The swing-universe builder independently repeats the completeness and
cross-store agreement gate before reading classifications.
