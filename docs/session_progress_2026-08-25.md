# Aperture Session Progress — 2026-08-25

## Branch and milestone purpose

- Branch: `codex/aperture-foundation`
- Milestone: publish and validate `exposure-policy-v3` for the
  `2026-07-26` security-master snapshot.
- Scope was limited to the exposure-classification publication milestone.

## Test gate

The relevant exposure-policy, v3/versioning, and persistence tests ran before
the production publication was built:

- Tests collected: 55
- Tests passed: 55
- Tests failed: 0

## Exposure-policy-v3 publication

Publication completed successfully with these results:

- Publication state: `complete`
- Rows: 13,023
- Distinct tickers: 13,023
- Duplicate rows: 0
- `direct_equity`: 5,302
- `diversified`: 4,968
- `non_equity`: 2,304
- `single_security`: 449
- `review_needed`: 0

Publication identity and integrity:

- Logical fingerprint:
  `fbb2e169e9c1e9896192fb0985efbb879c9861ab106b958d57a69276e56881d2`
- Parquet SHA-256:
  `ad96705b5bccc46151ebf03101408cc79267ac9ed36f4e0b2c9386ba089fcdac`
- Policy-config SHA-256:
  `3fb4bb9a2a295354784f970f3727449dca67818d1518c8e3b5a2e4ea27d6824a`

DuckDB and Parquet agreed exactly:

- Recorded row count matched DuckDB and Parquet.
- Recorded logical fingerprint matched DuckDB and Parquet.
- No missing or extra keys were found.
- No field mismatches were found.
- No invalid scopes or invalid underlying tickers were found.
- No classification methods, policy reasons, or provenance values were
  missing.
- No staged or extra Parquet publication files remained.

## Exposure-policy-v2 immutability

The v2 publication was revalidated after publishing v3 and remains unchanged:

- Publication state: `complete`
- Rows: 13,023
- Distinct tickers: 13,023
- DuckDB and Parquet agreement: exact
- Logical fingerprint:
  `10fc63a5f77cdc559d23b8ab46ed863f43ad132169fcf16defe3a690dc510154`
- Parquet SHA-256:
  `b1ef22138da6bc0954eb29acd84fa82ca50314ba01e5dfe7b8bfbad767a25dd6`
- Policy-config SHA-256:
  `d5e6c0ba7c19ae7d39ceaf9939d079d9233ab5852401ef118f6be753a9a2f346`

The v2 partition retained its original scope counts and remains independently
reproducible.

## Work intentionally not performed

- The swing-universe snapshot was not rebuilt.
- The adjusted-backfill plan was not rebuilt.
- No ingestion job was run.
- No Massive.com request was made.
- No generated data or database artifact is part of this documentation
  checkpoint.

## Next milestone

Rebuild and validate the swing universe for snapshot `2026-07-26` using
`exposure-policy-v3` explicitly.

The next milestone should confirm that:

- the v3 exposure publication is required and complete;
- single-security and `review_needed` products cannot enter the core universe;
- eligible diversified products remain available for market mapping;
- non-equity products remain excluded from the equity core universe;
- membership counts, exclusions, duplicate keys, nulls, date coverage, policy
  identity, and DuckDB/Parquet agreement are reported; and
- the completed adjusted bars for the original ranks 1–50 remain untouched.

Do not rebuild the adjusted-backfill plan until the v3 swing-universe snapshot
has passed validation.
