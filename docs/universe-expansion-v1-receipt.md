# Universe expansion verification receipt

Task: `AP-UNIVERSE-EXPANSION-001`. Final snapshot/deployment verification is in progress.

Reviewed PR #17 was merged with a merge commit at
`3a1499e2d22a7321c55dc4e03b4dba382d590aad`, preserving the source branch.
Expansion uses `codex/universe-expansion-v1` from that merged baseline.
No trading formulas, universe thresholds or original source clocks changed.

## Verified coverage

| Evidence | Count |
| --- | ---: |
| Deepvue union candidates | 11,374 |
| Exact compatible identities | 11,335 |
| Source-native non-security/breadth dispositions | 29 |
| Unresolved exact identities | 10 |
| Research-eligible candidates | 3,045 |
| Strict-trade candidates | 812 |
| Research candidates with ready history | 2,743 |
| Research candidates with short listed histories | 130 |
| Research candidates with missing sessions | 172 |
| Published acquisition population, including benchmarks | 3,077 |
| Current calculated research / trade / mapping | 2,743 / 776 / 333 |

Candidate eligibility and current calculated membership are separate: eligible
names lacking ready history remain in coverage but are not newly admitted.
Mapping instruments do not thereby become equity-trade candidates. Missing
taxonomy or themes never excludes an otherwise eligible stock. All 2,743 current
research members have hierarchy capture rows; 1,101 have theme membership.

Unresolved exact identities: APGE, BTOG, CRNX, GBF, HLX, JFB, NCSM, PRVT, YYGH, ZTEK.
Six further current identities resolve to unsupported exchanges. The private
manifest retains every candidate, source contribution, exclusion reason and exact
missing session. Research exclusion reasons overlap: ineligible exposure 6,027,
ineligible security category 5,652, missing market cap 7,669, price below minimum
1,596, missing price 151, market cap below minimum 621, unsupported exchange 6.
These are reason counts, not mutually exclusive populations.

## Acquisition and immutable publication

The bounded plan preceded HTTP. The acquisition completed 4,048 requests:
273 adjusted daily market summaries, 3,774 exact reference responses and one
complete split-event window with 899 events. The history window is August 6, 2025
through September 4, 2026, all 273 completed XNYS sessions. September 7 is not
a completed trading session. R252 requires 253 observations; 20 extra sessions
provide acquisition margin without changing the readiness rule.

All 27,573 retained OHLCV overlap rows matched exactly. Required artifacts and
readbacks are hash-bound to coverage manifest
`d4360e17d7270e0fa0dc205ab7e9c942ea8a2f4cffc6c7fcb806f104d8d74b59`.
Separate backups and the completion receipt admit the publication recoverably.
Raw responses, private manifests, machine paths and licensed data remain outside
Git. The original 1,383 protected baseline artifacts remain byte-identical.

## Recovery and validation

Linux kernel and user-session logs confirm a global OOM killed the Python build
(3,376,712 KiB anonymous RSS); its VS Code scope subsequently failed with OOM.
Linux remained running. The original progress log and operator recovery receipt
were not durable replay checkpoints. Verified acquisition survived; the original
engine computation could not be resumed. No acquisition was repeated.

Recovery established immutable, hash-bound per-symbol Structure/Setup checkpoints
before the one necessary full replay. All 2,743 shards subsequently passed a
separate typed audit against exact input-history bytes, source, calendar, corporate
actions and engine identities. Later construction attempts restored all shards
with engine execution explicitly forbidden. A narrowly checked compatibility
receipt admits only the downstream decision-validation change; original shards
remain unchanged.

The concrete allocation problems were full object-dtype Parquet readback copies,
quadratic expansion of shared Leadership/Regime/bootstrap inputs during decision
validation, retained consumed Setup graphs and identity caches, and whole-snapshot
JSON representations. Fixed-size readback, memoized model validation, early
release of consumed objects, disk-backed normalization and row-streamed archive
I/O preserve formulas, full evidence, fingerprints and all integrity checks.
The symbol API also required explicit V2 reference-based shared evidence:
AAPL's old expanded response would repeat at least 326,938,170 bootstrap bytes;
its complete local V2 response is 211,414 bytes, with all shared nodes accessible
by fingerprint-bound graph references. Retained snapshots keep V1 compatibility.

The measured successful attempt restored all 2,743 cached outputs, assembled all
288,756 normalized evidence nodes, serialized and independently read/validated
the archive. Earlier throttled attempts were stopped deliberately with no new
OOM, and their inputs/logs were retained. Spill files used disk rather than tmpfs;
no swap or ChromeOS settings changed.

| Measurement | Peak RSS (KiB) |
| --- | ---: |
| Construction and initial full graph validation | 1,491,356 |
| Complete construction, archive write and typed readback | 1,536,856 |
| Independent cold API validation/load | 1,112,372 |
| API endpoint probe | 1,138,396 |
| Standalone API during real browser checks | 1,136,264 |

The independent cold load took 56.84 seconds. Desktop (1366 px) and mobile
(390 px) real-snapshot tests both passed in 23.8 seconds, covering Groups, Brief,
Tape, AAPL detail, Sizer and Rules, without browser errors or page overflow.
The API service recorded no memory-high, maximum or OOM events. The full recovery
service used a 1,400 MiB soft / 1,600 MiB hard cgroup budget and a two-hour timeout,
outside the editor scope, with durable logs and both refresh workspace locks.

The successful artifact has 2,743 records: 2,489 NONE, 254 WATCH, zero TRADE/ACT.
Canonical bytes: 79,532,474. Archive transport including envelope: 26,042,957 bytes.
Logical fingerprint:
`4d8ca015e9deadc1ca7f26b53596134072720ae9714c2be89e778df8ca6798c6`.
Market observations remain September 4; actual evaluation was September 8 at
05:23:37.910472 UTC; action expiry remains September 8 at 13:30 UTC.
VIX completed-session input remains unpublished/UNKNOWN; no value or deadline was
invented. The recovered artifact is current within that original action window.

Focused verification includes 312 decision-engine/adapter/recovery tests, 21
current-group/recovery tests, and a final 82-test materialization/archive/API run.
Fourteen frontend component tests, production build, type/schema checks and two
fixture browser tests also passed. No repeated full-suite run. New captures and
machine-specific receipts remain private and separate from retained originals.

See [the coverage contract](universe-expansion-v1.md) for recovery compatibility,
archive bounds and scheduler deployment requirements. The PR remains unmerged.

Activation and pinned scheduler deployment completed at 05:37:16 UTC. The runtime
is detached commit `7de9858f055e7e79d26c6ac8a42896956497b43c`, with the tested frontend
and an isolated interpreter import path. The previous main runtime, snapshots and
three configuration/unit backups remain preserved and hash-verified. The timer is
enabled and active, dispatching every 15 minutes; the next supporting-input retry
is 06:23:37.910472 UTC. All 1,383 protected baseline paths were checked again after
recovery and remain byte-identical. There is no remaining recovery blocker; the
unpublished VIX input and existing incomplete/unresolved coverage remain explicit.
