# Market Dashboard Development Progress — 2026-07-26

## Project purpose

This repository is a Python and Streamlit equity-research dashboard for:

- liquid swing-trading stock discovery;
- opportunity and tradability ranking;
- leadership analysis; and
- daily swing price-action classification.

Options analysis is not currently part of this project. Do not mix this
repository or its data workflows with separate options-related work.

## Development environment

- Chromebook Linux environment
- VS Code
- Codex as the local coding and execution agent
- GitHub as remote source control
- Development currently occurs directly on `main`
- Python 3.13.5
- Virtual environment: `.venv`
- Prefer `.venv/bin/python` for project commands
- Massive.com credentials exist only in the local `.env`
- `.env` is ignored by Git
- `.vscode/settings.json` is machine-specific and must remain uncommitted

## Important security and storage rules

Never commit:

- `.env` or API keys;
- DuckDB databases;
- Parquet datasets;
- raw or processed market data;
- ingestion manifests;
- virtual environments or caches; or
- generated datasets and local reports.

No real credentials have been found in tracked files or Git history.

## Major completed milestones

1. `b96f53acf27a2e394027da5bb96573dbc4bc958f`
   `feat: add production universe and resilient backfill pipeline`
   - Added the production security master, liquid swing universe,
     adjusted-history backfill plan, and resilient ingestion runner.
2. `3f3d12a6401fa4685f25bd1df7d232ed0e1c971b`
   `feat: add versioned exposure classification policy`
   - Separated provider facts from versioned derived exposure classification.
3. `bad695c41c70ad3bd1481acc3e2562e598186792`
   `fix: make exposure publication recoverable`
   - Added durable publication states, deterministic fingerprints, DuckDB
     transactions, Parquet validation, recovery, and downstream safety gates.
4. `feat: add resolved exposure policy v3`
   - This handoff is part of that commit. Its SHA is the commit containing this
     document; do not amend the commit merely to insert its own SHA.

## Existing production security master and universe

- Security-master snapshot: 2026-07-26
- Security-master rows/tickers: 13,023 / 13,023
- Structurally eligible under the legacy policy: 10,418
- Legacy liquid core universe: 1,828
  - Common stocks: 1,424
  - Standard ETFs under the legacy interpretation: 404
- Liquidity requirements:
  - latest close of at least $5;
  - 20-day average dollar volume of at least $50 million;
  - at least 60 valid observations; and
  - at least 90% session coverage.

The legacy universe and adjusted-backfill plan remain stored for auditability,
but they are not the final corrected-policy universe or plan.

## Adjusted-history progress

- Planned range: 2024-01-01 through 2026-07-24
- Completed real ingestion: legacy Tier 1 ranks 1–50
- Selected symbols: 50
- API requests: 45
- Already-current symbols: SPY, QQQ, NVDA, AAPL, and MSFT
- Failed requests: 0
- No-data responses: 0
- Every successful request completed on attempt 1 with HTTP 200

Current adjusted storage:

- `daily_bars`: 31,550 rows
- Distinct adjusted tickers: 50
- Maximum date: 2026-07-24
- Duplicate ticker/date groups: 0
- Required OHLCV nulls: 0
- Adjusted manifest: 50 rows
  - completed: 45
  - skipped-current: 5

Legitimate shorter-history symbols:

- SNDK: 356 sessions beginning 2025-02-24
- NBIS: 440 sessions beginning 2024-10-21
- GEV: 580 sessions beginning 2024-04-02

All 50 symbols have at least 252 sessions, and DuckDB and Parquet agreed.
Completed ranks 1–50 remain valid under the corrected policy. Do not delete
their adjusted bars. No real ranks 51–100 ingestion has occurred.

## Discovery of the exposure-policy defect

The legacy policy assumed Massive raw type `ETS` reliably identified
single-security ETFs. In practice, some genuine single-security ETFs arrived
as `ETF`, while diversified and non-equity products sometimes arrived as
`ETS`. Provider type was therefore both underinclusive and overinclusive.

MUU and SNXX exposed the defect during the ranks 51–100 dry run. Forty
confirmed single-security conflicts existed in the legacy 1,828-symbol
universe. Five were in legacy Tier 1: MUU, SNXX, TSLL, NVDL, and PLTD. None
were in the completed ranks 1–50 batch.

## Exposure-policy-v2

- Immutable policy: `config/exposure_policy.yaml`
- Version: `exposure-policy-v2`
- Derived table: `security_exposure_classification`
- Stable key: `snapshot_date + ticker + policy_version`
- Controlled scopes:
  - `direct_equity`
  - `single_security`
  - `diversified`
  - `non_equity`
  - `review_needed`

Published production result:

- Rows/tickers: 13,023 / 13,023
- Publication state: `complete`
- Logical fingerprint:
  `10fc63a5f77cdc559d23b8ab46ed863f43ad132169fcf16defe3a690dc510154`
- Parquet SHA-256:
  `b1ef22138da6bc0954eb29acd84fa82ca50314ba01e5dfe7b8bfbad767a25dd6`
- Configuration SHA-256:
  `d5e6c0ba7c19ae7d39ceaf9939d079d9233ab5852401ef118f6be753a9a2f346`

V2 scope counts:

- `direct_equity`: 5,302
- `diversified`: 4,931
- `non_equity`: 2,290
- `review_needed`: 136
- `single_security`: 364

V2 must remain reproducible and must never be silently reinterpreted.

## Recoverable publication protocol

Publication states are `pending`, `complete`, and `recovery_required`. After
the DuckDB transaction commits, its classification slice and recorded
fingerprint are authoritative. Parquet is staged on the same filesystem,
atomically published, and compared field-by-field with DuckDB before the
publication becomes complete.

Downstream builders reject an absent, incomplete, or inconsistent publication.
Recovery is bounded by snapshot date and policy version. A DuckDB commit and a
filesystem rename cannot be one physical transaction, so the project uses
explicit recoverability and validation rather than claiming cross-store
atomicity.

Recovery command:

```bash
.venv/bin/python scripts/build_exposure_classification.py \
  --snapshot-date YYYY-MM-DD \
  --policy-version POLICY_VERSION \
  --recover
```

## Exposure-policy-v3

- New immutable policy: `config/exposure_policy_v3.yaml`
- Version: `exposure-policy-v3`
- V3 explicitly extends v2.
- The configured default now selects v3.
- V2 remains unchanged and explicitly selectable.
- V2 and v3 can coexist for the same security-master snapshot.
- All resolutions are effective from 2026-07-26.
- Provenance: `manual_issuer_prospectus_review_2026-07-26`

Final resolution of the 136 v2 review records:

- `single_security`: 85
- `diversified`: 37
- `non_equity`: 14
- `review_needed`: 0

Important controls:

- BRKW → BRK.B
- JPO → JPM
- AIYY → AI
- HYNX → SKHY
- SPAX and YSPC → SPCX
- OARK is diversified through ARKK exposure.
- RAM and DRAL are diversified through DRAM exposure.
- XOVL is diversified through XOVR exposure.
- CHPY is a diversified semiconductor portfolio.
- BTCZ and BUCK are non-equity.
- TQQQ, SQQQ, SOXL, SOXS, QLD, and UPRO remain diversified.

V3 has been implemented and tested in memory. It has not been built as a
production classification. No v3 publication record or Parquet output exists.

## Current test status

- Targeted v3, versioning, persistence, recovery, and swing tests:
  61 passed in 15.63s
- Full suite: 218 passed in 39.11s
- `git diff --check`: passed
- Credential scan: passed
- Machine-path scan: passed

## Exact stopping point

- V3 implementation is complete and ready for its milestone commit.
- V2 production output is complete and unchanged.
- V3 production classification has not been built.
- The legacy universe and adjusted-backfill plan have not been rebuilt under
  v3.
- Real adjusted ingestion stopped after legacy Tier 1 ranks 1–50.
- `.vscode/settings.json` remains local-only and must not be committed.

## Next-session sequence

1. Verify Git state and read this handoff.
2. Build the production exposure classification for snapshot 2026-07-26 and
   policy `exposure-policy-v3`.
3. Validate complete publication, 13,023 rows/tickers, DuckDB/Parquet
   agreement, expected v3 scope counts, and zero `review_needed`.
4. Confirm the v2 partition, fingerprint, and Parquet hash remain unchanged.
5. Build a new policy-versioned swing-universe snapshot under v3.
6. Validate that no single-security or review-needed product entered the core,
   diversified products remain eligible, and non-equity products remain
   excluded.
7. Build a new policy-versioned adjusted-backfill plan under v3.
8. Validate continuous ranks and corrected tier boundaries.
9. Confirm every completed legacy ranks 1–50 symbol remains in corrected
   Tier 1.
10. Identify the corrected next unfilled rank range; do not assume legacy
    ranks 51–100 map exactly.
11. Dry-run the next corrected 50-symbol batch with explicit policy v3.
12. Review the dry run before authorizing real API requests.
13. Do not begin Tier 2 or Tier 3 without explicit approval.
14. Do not build the full Tier 1 feature snapshot until the approved Tier 1
    ingestion stage is complete.

## Useful commands

Select explicit v2:

```bash
.venv/bin/python scripts/build_exposure_classification.py \
  --snapshot-date 2026-07-26 \
  --policy-config config/exposure_policy.yaml
```

Select or build explicit v3:

```bash
.venv/bin/python scripts/build_exposure_classification.py \
  --snapshot-date 2026-07-26 \
  --policy-config config/exposure_policy_v3.yaml
```

Validate v3:

```bash
.venv/bin/python scripts/validate_exposure_classification.py \
  --snapshot-date 2026-07-26 \
  --policy-version exposure-policy-v3
```

Recover v3:

```bash
.venv/bin/python scripts/build_exposure_classification.py \
  --snapshot-date 2026-07-26 \
  --policy-version exposure-policy-v3 \
  --recover
```

Build and validate the v3 swing universe:

```bash
.venv/bin/python scripts/build_swing_universe.py \
  --snapshot-date 2026-07-26 \
  --security-master-snapshot-date 2026-07-26 \
  --start 2026-03-17 \
  --end 2026-07-24 \
  --policy-version exposure-policy-v3

.venv/bin/python scripts/validate_swing_universe.py \
  --snapshot-date 2026-07-26 \
  --policy-version exposure-policy-v3
```

Build and validate the corrected adjusted-backfill plan:

```bash
.venv/bin/python scripts/build_adjusted_backfill_plan.py \
  --plan-snapshot-date CORRECTED_PLAN_YYYY-MM-DD \
  --source-universe-snapshot-date 2026-07-26 \
  --start 2024-01-01 \
  --end 2026-07-24 \
  --policy-version exposure-policy-v3

.venv/bin/python scripts/validate_adjusted_backfill_plan.py \
  --plan-snapshot-date CORRECTED_PLAN_YYYY-MM-DD \
  --policy-version exposure-policy-v3
```

Run a bounded dry run only after the corrected plan exists:

```bash
.venv/bin/python scripts/run_adjusted_backfill.py \
  --plan-snapshot-date CORRECTED_PLAN_YYYY-MM-DD \
  --tier 1 \
  --start-rank NEXT_START_RANK \
  --end-rank NEXT_END_RANK \
  --batch-size 50 \
  --max-symbols 50 \
  --job-id POLICY_V3_JOB_ID \
  --start 2024-01-01 \
  --end 2026-07-24 \
  --policy-version exposure-policy-v3 \
  --stop-on-error \
  --dry-run
```
