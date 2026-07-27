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
