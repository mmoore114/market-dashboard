# AP-ENGINE-ALIGNMENT-001 completion receipt

Date: 2026-09-07. Branch: `codex/engine-alignment-v2`.
Implementation baseline: `a9c81aa048bc23d9247c8e9f3c76ef3aae17d92a`.
Delivery is a draft PR against main; merging and production activation are not
part of this assignment.

## Implemented versions and decisions

The source-only commit `71ef80d8637539d40ecdb7eda172db80adc50ce3` was cherry-picked
as `a463bce` without changing either pre-existing uncommitted file. The original
Word file hash and extraction verification are in the immutable
[source README](sources/final-word-spec/README.md). Text/JSON parity is tested.

- `structure-engine-v2` / `structure-features-v2` / `structure-thresholds-v2`:
  Word SMA20/SMA50 normalized inputs, median-ATR slopes, P20, confirmation and
  retention, and transitional-only D50 shocks. EMA10/SMA200 are context.
- `setup-engine-v2` / `setup-features-v2` / `setup-thresholds-v2`:
  closing-dispersion contraction, single 20-session range, 1-ATR geometry shift,
  mature-only pullbacks, 40/60-session limits, and explicit Word observation clocks.
- Existing V1 implementations and original snapshot bytes are preserved.
  Materializer dispatch, typed evidence, API detail and Rules select actual
  versioned computation. The original normalized evidence registry remains
  readable with stable type codes and an exact V1-only compatibility boundary.

Material source ambiguities, interpretations and retained safeguards are specified
in [the V2 contract](engine-alignment-v2.md). They include downside symmetry,
P20 equality, graph precedence, state-local counters, transitional exits,
pre-trigger cessation, and frozen prior-session pullback references. The small
comparison did not optimize thresholds or use future returns.

Structure rules fingerprint:
`b9c2ae96d1cf00ef23168af4ca188f41101f3823dc5e827216ca77b02897d071`.

Setup rules fingerprint:
`0f2acac1a4fa4546467db39098d33383212f0149f8bb9af1c660088e7f229aa2`.

## Observed verification

- Focused V2 semantic/integration tests: **43 passed**.
- Complete Python suite, run once outside the diagnosed AnyIO-restricted sandbox:
  **2,910 passed, 4 skipped**, 400.82 seconds. The four optional immutable local
  master-workspace cases were not enabled. Warnings concern Starlette/httpx
  deprecation and intentional invalid-version serialization in tamper tests.
- Frontend component tests: **13 passed**.
- Separate comparison browser suite: **2 passed**, at 1366px and 390px. Brief,
  Tape, Groups, symbol detail, Sizer and Rules worked over real local HTTP. Tests
  verified comparison labeling, preserved clocks, V2 versions and detail evidence,
  sizing fingerprint parity, and no browser page errors.
- TypeScript typecheck, production build, frontend ESLint/Prettier, scoped Python
  Ruff, OpenAPI export check, snapshot-schema export check, generated TypeScript
  synchronization and `git diff --check`: passed.
- Python formatting checks covered new V2 code and formatted integration files;
  the pre-existing style of the old decision contract body was left alone.
  No repository-wide legacy lint cleanup or mass-formatting occurred.
- Both temporary API/frontend listeners were absent after Playwright teardown.

## Separate local comparison snapshot

Artifact: `engine-comparison-2026-09-04.json`, in the operator's separate local
`aperture-engine-alignment-v2` workspace, alongside `build-receipt.json`. Neither
artifact nor per-symbol classification data is committed.

Logical fingerprint:
`e7e2b78be213dbf51919012bbc4ddbf34ee4e58ce495be8d50c45246aa386a73`.

- Size: **2,146,854 bytes**; replay: **482.74 seconds**.
- Labeled **ENGINE_VERSION_COMPARISON** and bound to the original V1 snapshot
  fingerprint `d10b6c0b62d403755aa7be08e8c378fb7b694c3c1254cbfcc2ff282b899b8012`.
- Original market T: **2026-09-04**; evaluation E:
  **2026-09-07 01:53:42.451047 UTC** (September 6 New York); action A:
  **2026-09-08**. Original population/evidence clocks are unchanged.
- Actual V2 generation: **2026-09-07 23:20:56.736750 UTC**.
- Original expiry: **2026-09-08 00:00 UTC**, unchanged. Validation and browser
  checks observed FRESH before that deadline. Afterward the same snapshot must
  be refused as stale by live surfaces. No clock override or freshness extension
  was used; this artifact is not a new market refresh.
- Rechecked **119 input/baseline/receipt hashes**, **66,951 bars**, foundation and
  population publication completion, and DuckDB/Parquet equality using read-only
  database access.
- **75** valid current Structure records, **914** not-yet-observed leading slots,
  **0** internal missing observations, **0** insufficient-history current states.
- Standalone loading, normalized evidence integrity and canonical decision/risk
  field parity passed.

## Classification comparison

At the same T, **28 of 75** Structure classifications changed:

| State | V1 | V2 |
|---|---:|---:|
| NEUTRAL | 19 | 16 |
| EMERGING | 3 | 6 |
| UPTREND | 20 | 24 |
| DETERIORATING | 14 | 5 |
| DECLINE | 19 | 24 |

Active setup family/direction/status sets changed for **63 symbols**. Counts below
are active instances across both directions, not mutually exclusive stock counts:

| Family | V1 | V2 |
|---|---:|---:|
| CONTRACTION | 18 | 31 |
| RANGE | 61 | 38 |
| TREND_PULLBACK | 31 | 45 |
| EP | 0 | 0 |

The action funnel changed from **66 NONE / 9 WATCH / 0 TRADE / 0 ACT** to
**63 NONE / 12 WATCH / 0 TRADE / 0 ACT**. Three symbols changed action state;
there was no promotion to TRADE or ACT.

The deterministic first-eight-symbol sample covered **1,008 symbol-sessions**
(126 per symbol, full-prefix warmup): **362** Structure labels differed.
V1 had **56** transitions; V2 had **69**. This sample does **not** demonstrate lower
churn, better returns, or more accurate trading signals. It supports a bounded
classification sanity review only. No threshold was optimized to these results.

## Preservation and remaining limits

All **1,383** protected baseline files remained byte-identical, including settings,
source data, original snapshots and retained backups. No provider requests,
production publications, source-data mutations, branch deletion, merge, chart
implementation, or UI redesign occurred. The existing settings modification stays
uncommitted. V1 remains the default engine selection.

The comparison is a bounded initial cohort, not a full U.S. universe study.
Group membership and earnings evidence remain incomplete. Material source gaps
have explicit versioned interpretations, but wider calibration remains future
work. Word pullback resolution has no arbitrary timeout, so an unfailed triggered
pullback can remain under observation until rebound. Operational freshness expires
at the original deadline; refreshing it requires a separately authorized task.
