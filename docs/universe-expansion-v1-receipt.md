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

A VSCode crash interrupted the second full build after 2,700 of 2,743 engine
replays, before any snapshot publication. Verified acquisition survived and the
existing scheduler remained enabled on the known-good checkout. A separate
recovery build reuses those inputs and reruns deterministic engine replay.

Recovery checks: 96 focused Python tests passed (82.22 seconds), including
selection, coverage, acquisition resumption, required daily inclusion, missing
bars, runtime guards, current-cohort parity and failed-publication preservation.
Fourteen frontend component tests passed. No repeated full-suite run.

See [the coverage contract](universe-expansion-v1.md) for commands, archive bounds
and scheduler deployment requirements. Final real-snapshot scale measurements,
desktop/mobile results and scheduler switch remain pending in this receipt.
