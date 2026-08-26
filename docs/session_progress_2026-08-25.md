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

## Exposure-policy-v3 swing-universe milestone

The broad research and data-planning swing universe was built and validated
for snapshot `2026-07-26` under `exposure-policy-v3`. This snapshot uses the
existing $5 price, $50 million ADV20, observation-count, and session-coverage
requirements. It is not Aperture's later, stricter equity trade universe.

### Test gate

- Targeted swing-universe tests: 6 passed, 0 failed.
- Full test suite: 218 passed, 0 failed.

### Build and validation

- Source security-master snapshot: `2026-07-26`
- Source flat-file window: `2026-03-17` through `2026-07-24`
- Expected sessions: 90
- Total rows/tickers: 13,023 / 13,023
- Structurally eligible: 10,037
- Liquidity eligible: 1,787
- Core eligible: 1,787
- Duplicate snapshot/ticker/policy groups: 0
- Required-field nulls: 0
- Required metric nulls among core-eligible rows: 0
- DuckDB-only or Parquet-only rows: 0 / 0 across all 30 fields
- V3 swing-universe Parquet SHA-256:
  `7bd5687548975e04f901bb02f5e498aa637afad82d62d58eb57b383f9dc0d6c1`

Exposure-scope funnel counts:

| Exposure scope | All rows | Structurally eligible | Core eligible |
| --- | ---: | ---: | ---: |
| `direct_equity` | 5,302 | 5,100 | 1,424 |
| `diversified` | 4,968 | 4,937 | 363 |
| `non_equity` | 2,304 | 0 | 0 |
| `single_security` | 449 | 0 | 0 |
| `review_needed` | 0 | 0 | 0 |

Core counts by exchange:

- Nasdaq: 635
- NYSE: 857
- NYSE American: 5
- NYSE Arca: 249
- Cboe BZX: 41

Core counts by security category:

- Common Stock: 1,424
- ETF: 363

Exclusion counts:

- Included: 1,787
- ADV20 below $50 million: 5,872
- Latest close below $5: 1,409
- Fewer than 60 valid observations: 702
- Recent session coverage below 90%: 267
- Acquisition vehicle: 202
- Depositary receipt: 377
- Exchange-traded note: 51
- Exchange-traded vehicle: 88
- Preferred share: 430
- Right: 113
- Structured product: 158
- Unit: 301
- Unsupported fund: 333
- Warrant: 439
- Single-security product: 449
- Single-security ETF under the legacy structural category: 31
- Missing legacy structural category: 14

No core-eligible row had `single_security`, `review_needed`, or `non_equity`
exposure.

Observation and date coverage among structurally eligible rows:

- Valid observations: minimum 0, median 90, maximum 90
- Session coverage: minimum 0%, median 100%, maximum 100%
- Latest trading date range: `2026-06-04` through `2026-07-24`

### Publication and compatibility evidence

The v3 exposure publication remained `complete` with 13,023 rows and logical
fingerprint:

`fbb2e169e9c1e9896192fb0985efbb879c9861ab106b958d57a69276e56881d2`

The v2 exposure publication also remained `complete` with its original 13,023
rows and logical fingerprint:

`10fc63a5f77cdc559d23b8ab46ed863f43ad132169fcf16defe3a690dc510154`

The pre-existing swing-universe snapshot was an unversioned legacy artifact,
not an `exposure-policy-v2` partition. The schema migration preserved its
13,023 rows under `legacy-policy-v1`, with exact DuckDB/Parquet agreement. Its
Parquet SHA-256 remained unchanged:

`d0e2f3f643673f43f501e35954f8778a3529f527bc32f792e7ece0c4883a7134`

No v2-labeled swing-universe partition was created or reinterpreted.

### Preserved data state

- Adjusted bars remained at 31,550 rows and 50 tickers.
- Adjusted-bar dates remained `2024-01-02` through `2026-07-24`.
- Duplicate adjusted ticker/date groups: 0.
- Required adjusted OHLCV nulls: 0.
- Original ranks 1–50 remained represented by 50 manifest rows and 50
  distinct tickers.
- Manifest states remained 45 `completed` and 5 `skipped_current`.
- The existing 1,828-row adjusted-backfill plan was not rebuilt or changed.
- No ingestion ran and no Massive.com request occurred.

## Next controlled data milestone

Build and validate a corrected, policy-versioned adjusted-backfill plan from
the validated v3 swing universe. Identify the corrected next unfilled rank
range before any bounded dry run. Real ingestion still requires separate,
explicit approval.
