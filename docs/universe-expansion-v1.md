# Published universe coverage V1

AP-UNIVERSE-EXPANSION-001 is owner-authorized expansion, following the normal merge
of reviewed PR #17 at `3a1499e2d22a7321c55dc4e03b4dba382d590aad`.
It changes coverage and operations, not trading formulas or universe thresholds.
The original 75-stock bootstrap, original captures, source publications and
snapshots remain evidence with their original identities and clocks.

## Candidate and admission contracts

The candidate set is the exact union of the three hash-verified Deepvue stock,
hierarchy and theme CSVs in the repository capture manifest. Reconciliation uses
the complete retained provider identity catalogue, exact current ticker details,
and the existing compatibility boundary. It never case-folds or invents aliases.
The existing non-security/breadth dispositions, security categories, exposure
policy V3 and Aperture universe rules V1 remain authoritative. Current details
can identify OTC or inactive instruments; a returned ticker is not proof of
research or trade eligibility. Unknown market capitalization stays unknown.

`aperture-universe-coverage-v1` records every candidate, contributing captures,
identity disposition, independent research/strict-trade/mapping outcomes and
reason codes, listing date when available, observed history, exact missing
sessions, readiness, required benchmarks and the published acquisition population.
Missing taxonomy or themes is never an admission predicate. Separately published
Groups retain original parent paths, all four conflicts and many-to-many themes.

History acquisition covers 273 completed XNYS sessions. R252 requires 253 closes;
this is the readiness floor, with 20 additional acquired sessions as an operational
margin rather than an additional trading rule. The initial acquisition estimate
conservatively budgeted readiness at 273; the coverage receipt explicitly records
253 and the 273-session acquisition window. Confirmation, SMA200 and Setup lookbacks
fit within this history. Readiness also requires complete expected observations;
a gap cannot be disguised by counting an extra row elsewhere. Listing dates explain
pre-listing absence only when supplied by the provider. Unexplained absence stays
missing. Existing short-history bootstrap names are retained with their actual
history and UNKNOWN components; they are not relabeled history-ready.

Newly admitted research/mapping names must be history-ready. Other eligible names
remain visible in the coverage manifest with exact missing/short-history reasons.
This is explicit incomplete coverage, not a claim that those stocks are ineligible.
Required benchmarks and previously published coverage remain explicit. Research,
strict trade, history readiness and published coverage are different counts.

## Bounded acquisition and publication

The private `universe-expansion-plan-v1` records source hashes, original local
history hashes, candidate identities, market/action clocks and request/storage/time
estimates before HTTP. The existing Massive subscription supplies adjusted daily
market summaries, exact ticker details and a bounded complete split-event window.
Raw flat files are unadjusted and are not substituted. No new subscription,
authenticated Deepvue automation, or provider is introduced.

A batch uses four workers, at most four requests per second, three durable attempts
per exact job, no redirects, a 16 MB response bound, and a 1 GB free-space reserve.
401/403 stops acquisition; retryable failures remain bounded. Receipts reserve an
attempt before HTTP and bind sanitized, allowlisted compressed data by hash.
Successful jobs survive restart without another request or a new retrieval clock.
A changed plan or receipt fails closed. Provider errors and credential-bearing
URLs never enter logs. The command holds an exclusive acquisition lock.

All adjusted retained OHLCV overlaps must match exactly before mixing sources.
Identity/session duplicates, off-calendar observations, invalid OHLC ranges or
volume, and unconfirmed adjustment basis are refused. Confirmed split events are
passed to the existing EP quarantine. Absence from a split list does not establish
complete corporate-action coverage: remaining QA stays UNKNOWN. Adjusted bars
are never adjusted a second time.

Publication creates separate verified Parquet, identity-audit and corporate-action
artifacts, a hash-bound coverage manifest, a verified manifest backup and a final
completion receipt. The receipt is the admission boundary. Failed preparation
leaves resumable private staging, never an active partial generation. Original
nanosecond reference clocks and observed numerical values survive readback exactly;
null representations are normalized only for comparison.

Private configuration supplies `repository`, `workspace`, `inventory`, `master`,
`exposure`, `bars_directory`, and `credentials_file`. Use explicit absolute paths
locally; never commit that configuration or any generated artifact:

```bash
.venv/bin/python -m market_dashboard.data.expansion plan --config "$EXPANSION_CONFIG"
.venv/bin/python -m market_dashboard.data.expansion acquire --config "$EXPANSION_CONFIG"
.venv/bin/python -m market_dashboard.data.expansion publish --config "$EXPANSION_CONFIG"
.venv/bin/python -m market_dashboard.data.expansion report --config "$EXPANSION_CONFIG" --details
```

`report` is read-only and makes no provider requests. Keep detailed per-symbol output
private; it lists every incomplete research name and its exact missing sessions.

## Daily refresh and current evidence

Refresh configuration explicitly pins `coverage_manifest` and
`coverage_manifest_sha256`. Without them the retained bootstrap path remains
available. The manifest, completion receipt, backup and all source hashes must
verify before acquisition. Membership reuse is checked independently first.

Every published covered symbol and required benchmark participates in incremental
acquisition. Adjusted market summaries acquire missing completed sessions plus an
overlap; exact current controls use resumable bounded parallel jobs. A delayed required daily bar is not cached as a completed job. Daily attempts
retain the existing three-attempt budget per UTC day; initial backfill attempts
remain bounded across restarts. Missing bars,
changed adjusted overlap, ambiguous identity/type changes or independent control
failures preserve the previous snapshot. Current rules recompute research/trade
eligibility, including existing retention safeguards. No unreviewed new ticker
can enter through daily prices. Admission of another name requires a new verified
coverage publication and completed backfill.

`CoverageContextV1` / `coverage-current-state-v1` and
`coverage-materialization-plan-v1` bind expanded current evidence to the published
coverage hash. API evidence includes that binding and a distinct reference-generation
identity. It does not claim that the entire retained reference catalogue was fetched
again. Price observations keep T, the actual evaluation is E and action is the next
XNYS session A. Membership source dates/age and original policy expiry remain
independent. Historical selection/rotation remains unavailable before its actual
contract permits it. Expanded prices do not imply complete earnings or VIX evidence.

## Scale and transport

Coverage keeps the complete identity audit in one hashed artifact. Pandas row
selection otherwise deep-copied the whole audit thousands of times. Current
population features use existing liquidity/volatility functions over their full
observed history, retaining only required current inputs between passes. Legacy
feature history is not redundantly rebuilt for current population admission.

Replay validates bars once for Regime, reuses each symbol's canonical final Setup,
and indexes per-symbol history. Where current-cohort analysis has no historical
Groups, the mandatory historical sub-industry gate makes Internals UNKNOWN;
unpersisted historical stock ranks cannot change Regime memory. Only that path
skips those ranks. Historical membership replays retain full calculation; T always
calculates complete Leadership. Expanded diagnostics avoid per-record serialization
of the same shared context; complete canonical evidence-node hashes and typed
integrity remain mandatory. Focused tests compare final canonical outputs and
Regime memory with the full replay.

`workstation-snapshot-archive-v1` is lossless transport for expanded normalized V2
snapshots. A small JSON envelope binds a sibling content-addressed gzip payload,
compressed/uncompressed hashes, exact record count and logical fingerprint. The
ordinary JSON limit remains 32 MiB. Archives keep the same compressed transport
bound, a per-record decode budget plus fixed catalogue allowance, an independent
512 MiB anti-decompression-bomb ceiling, and complete typed graph validation.
Path traversal, changed payloads, count/clock/context mismatches and decompression
overruns are refused. Activation and backups retain the verified payload before
atomically switching the envelope. Old plain JSON snapshots remain readable.

## Scheduler deployment

Development runs in an isolated worktree while the enabled timer remains on the
merged known-good implementation. A final deployment must be a detached, tested
commit with an explicit private `runtime_commit` pin and its own import environment.
The refresh guard refuses a different commit, a branch checkout or tracked changes
before acquisition. Switch the service/config under the existing exclusive lock,
with verified backups; keep the prior checkout and configuration available.

The timer dispatches every 15 minutes. Dispatch is distinct from acquisition
eligibility (actual XNYS close plus 45 minutes, or a bounded supporting-input retry).
The expanded service defaults to a bounded 90-minute timeout (configurable up to
120); the retained bootstrap default stays 30. This accommodates the measured
full-population replay plus bounded control acquisition/retries after removing
repeated calculations and copies. It is an operational budget, not permission to
extend snapshot expiry or accept an unverified output. Linux must be running. The timer neither guarantees provider publication nor wakes
a suspended host. See the completion receipt for observed deployment and timing.

Sources: [Massive adjusted market summaries](https://massive.com/docs/rest/stocks/aggregates/daily-market-summary),
[Massive split events](https://massive.com/docs/rest/stocks/corporate-actions/splits).

## Crash recovery and memory bounds

A progress counter is not a replay checkpoint. Expanded current-only replay now
writes immutable per-symbol Structure/Setup shards before reporting progress.
Shards bind the observed history and schema, source, calendar, as-of session,
corporate actions, selected engine versions and implementation digest. Payload
hashes and the closed typed engine contracts are verified on reuse. Incompatible
inputs select a different shard; a corrupt matching shard fails closed. Historical
replay is not silently reduced to final-state shards. Evaluation-time membership,
Leadership, Regime, decision gates and snapshot freshness are rebuilt with their
actual clocks; cached price-engine output never extends an action deadline.

Expanded evidence normalization uses a temporary SQLite index with a bounded page
cache. Hashed nodes are converted one at a time to the existing normalized V2
index. Canonical fingerprinting and archive writing traverse evidence rows without
creating a whole-snapshot dictionary or JSON string. Archive reading verifies the
bounded decompressed bytes on disk, then parses and validates individual graph
rows. Every node hash, reference, type, cycle, population, provenance, gate and
logical fingerprint check remains required. Existing JSON and archive version
identities and size limits are unchanged. The final normalized and decoded typed
graphs still occupy memory; the real population must pass measured construction
and API loading before deployment.

Run long recovery work in a user-systemd service outside the editor scope, with
durable stdout/stderr, memory accounting, a finite timeout and a memory ceiling
selected from available laptop headroom. Stop the existing refresh dispatcher,
confirm its service is inactive, and acquire both old and recovery workspace
locks. Restore the prior timer state on every exit, including failures. Preserve
prior snapshots, input publications, checkpoints and deployment backups. System
swap and host configuration are separate operator decisions.

Input Parquet readback compares every row and field in fixed-size batches with
exact numeric equality, avoiding simultaneous full object-dtype frames. Recovery
spill storage must be on the disk-backed workspace when the host mounts `/tmp`
as tmpfs; the expanded replay uses the checkpoint workspace for normalization.

Expanded symbol detail uses `/api/v2/symbols/{symbol}` (`symbol-detail-v2`).
The canonical local fields are unchanged; shared Leadership and Regime inputs
become index-and-hash references into the validated normalized graph. Every
canonical output also has its complete graph reference. `/api/v2/evidence` exposes
all nodes in bounded pages and requires the snapshot fingerprint, refusing a page
from a different activated snapshot. This preserves full evidence without expanding
bootstrap provenance quadratically in a single symbol response. The browser uses
the V2 view. The V1 symbol route remains available for retained snapshots; expanded
coverage receives an explicit `409 NORMALIZED_SYMBOL_DETAIL_REQUIRED` migration
response before serialization. Snapshot storage and engine versions are unchanged.

Decision-input revalidation also walks the frozen model graph with invocation-local
identity memoization. Every distinct nested model is reconstructed through its
validators, including unvalidated `model_copy` values. Repeated shared identities
reuse that validated result; they do not expand the entire Leadership/Regime graph
into a Python dictionary for each symbol. Decision formulas and engine fingerprints
are unchanged.

The initial checkpoint digest conservatively covered all Aperture and feature
modules. A `replay-code-compatibility-v1` receipt can reuse those shards across
changes restricted to the two downstream decision adapter/orchestrator modules.
It binds the prior complete file-hash map and current digest; every other source
file, all input history bytes, source, calendar, corporate actions and engine
versions must match. Any price-engine change refuses compatibility. Original shards
are read in place and never relabeled or overwritten. Construction plan and manifest
are persisted atomically before replay/assembly, including failed attempts.

Consumed per-symbol Setup outputs and validation identity caches are released
before assembling the normalized table. The builder drops its canonical identity
cache before table conversion, so normalization and typed validation do not retain
an unnecessary second complete set of source objects. The receipt reports both
the combined construction/readback peak and an independent API cold-load peak.
