# Security identity boundary v2 — exact-case precedence

This contract supersedes the blanket uppercase-reader block described in the
initial case audit. Exact reference identity and uppercase market-data identity
are separate domains. It does not change July's stored snapshot, historical
exposure policy results, bar keys, feature formulas or trade-universe invariants.

## Types and explicit conversion

`ReferenceTicker` is an immutable exact provider string. Case is identity-bearing;
it is never rewritten. `MarketDataSymbol` is a distinct immutable type whose value
must already be uppercase. Constructing one from a mixed-case string raises an
error. It is not a subclass or alias of `ReferenceTicker`.

`CompatibilityBoundary`, version `reference-to-market-data-v2-exact-precedence`, is constructed
from the complete dated reference identity set, before type or universe filtering.
Its explicit `convert(ReferenceTicker)` returns a `Conversion` containing either a
validated `MarketDataSymbol` or no symbol plus a reason. Unknown references return
`REFERENCE_NOT_IN_SNAPSHOT`. Duplicate exact reference identifiers are fatal.

`compatibility_projection(frame)` returns a separate compatible frame and an audit
row for every input reference. It never mutates the input, filters the master
layer or overwrites exact ticker keys. Multiple snapshot dates are rejected.
The compatible frame retains only explicitly convertible rows; its ticker values
are the resulting market-data symbols, identical to their original uppercase
reference strings.

| Reason | Conversion |
| --- | --- |
| COMPATIBLE | Exact uppercase stored identity maps to itself, even when a mixed-case neighbor exists |
| MIXED_CASE_REFERENCE_ONLY | No conversion; valid exact reference identity remains in master |
| AMBIGUOUS_NO_EXACT_IDENTITY | Reverse resolution found no exact stored identity; no casefold fallback, even for a single candidate |
| REFERENCE_NOT_IN_SNAPSHOT | No conversion; reference was not part of the boundary's complete input |

Casefold is used only to detect conversion ambiguity. It is never a reference
persistence key or an automatic join. TPC and BCPC map exactly to their own market-data symbols; TpC and BCpC
remain excluded from automatic conversion. All four remain separate master rows,
and both case-insensitive collision groups remain explicit reports. Exclusion from this projection does not mean
invalid, malformed, inactive or excluded from the security master.

Existing bar/feature/trading APIs remain uppercase market-data APIs. Their legacy
string normalization is an explicit convention within that domain, not an API
for converting reference identifiers. Callers moving from a complete reference
snapshot must first use the compatibility API. They must not send raw reference
rows directly to these domain APIs. A standalone uppercase string carries no
proof of compatibility with a reference snapshot; the conversion context matters.

## Reader migration map

Every reader named in the initial audit is classified below. “Migrated” means an
unsafe mixed-domain reader was changed to consume the explicit projection or to
preserve exact source case. Readers inside the uppercase market-data domain retain
their existing uppercase invariants.

| Reader | Classification and boundary |
| --- | --- |
| Security master normalization, persistence, reclassification | Exact reference-identity consumer; no ticker rewrite; exact duplicates fatal |
| Staged fetch, validation, fingerprinting, publication | Exact reference-identity consumer; emits separate projection and ambiguity reports |
| Massive reference client | Exact reference-identity consumer |
| DuckDB/Parquet master schema and unique keys | Exact reference-identity consumer; unchanged case-sensitive strings and `(snapshot_date,ticker)` keys |
| Security-master validation script | Exact reference-identity consumer |
| Deepvue taxonomy and theme importers | Previously unsafe source uppercasing; migrated to preserve symbol case (existing source whitespace cleaning remains). Theme importer uses the same cleaner. No stored snapshot was rewritten |
| Staged Deepvue reconciliation | Exact reference-identity consumer; exact symbols first, 29 exact disposition exclusions, no casefold matching, unapplied crosswalk separate |
| ExposurePolicy.classify_snapshot | Previously unsafe mixed-domain consumer; migrated by projecting the complete reference input before classification. Its output attributes retain every-row projection diagnostics |
| ExposurePolicy.classify_record / classification persistence | Uppercase market-data consumer; now validates uppercase ticker/underlying inputs instead of coercing reference ticker case |
| Exposure registries, overrides, underlying/name candidates | Uppercase market-data/trading consumer; existing versioned policy normalization unchanged, used only after the reference boundary |
| Swing-universe master/exposure/bar joins | Previously unsafe mixed-domain consumer; migrated to a connection-local projected master relation built from the entire dated master before filtering and joining |
| Exposure validation script | Previously unsafe mixed-domain consumer; migrated to projected master joins and projected expected-row count |
| Exposure build script | Reference adapter into `classify_snapshot`, which projects the complete dated input. Exposure publication remains a separate explicit workflow; not invoked here |
| Legacy master ingestion CLI | Exact reference-identity consumer; automatic exposure classification/publication removed. Prints exposure publication disabled |
| Daily ingestion / Massive daily client | Uppercase market-data consumer; not a reference conversion API. Existing uppercase request/storage invariants unchanged |
| Flat daily processing | Uppercase market-data consumer; existing market-data chunk normalization and keys unchanged; no reference-master join |
| Equity features | Uppercase market-data consumer; existing grouping and feature invariants unchanged |
| Aperture universe models and rules | Uppercase market-data/trading consumer; existing validation unchanged |
| Daily-storage validator / flat stress report | Uppercase market-data diagnostic consumer; existing filename/argument conventions unchanged |
| Tests | Separate exact-case and uppercase-domain fixtures, explicit conversion/rejection, collision exclusion and no automatic exposure-publication tests |

There are no remaining identified unsafe **reference readers** in the audited
repository call paths. `UNSAFE_REFERENCE_READERS` is an explicit fail-closed
migration registry: adding an unresolved reader blocks both publication paths.
It is not a CLI override. New or external consumers must be audited against this
contract before use; the registry does not establish compatibility for unknown
callers.

## Publication and reconciliation gates

Both public master publication paths verify deterministic exact uppercase
round trips and explicit mixed-case exclusions and consult the unsafe-reader
registry before production writes. The staged publisher also
requires the compatibility version on its validation receipt. A mixed-case row
without a collision is valid master content and may be excluded from consumer
projection; mixed case alone is no longer a blanket publication blocker.

Collision groups alone no longer block publication compatibility. Exact-case
precedence yields zero ambiguous automatic conversions for the current snapshot.
Reverse casefold resolution remains blocked: `resolve_reference` returns the
exact stored ReferenceTicker first, including an exact mixed-case request; every
non-exact input returns no reference and AMBIGUOUS_NO_EXACT_IDENTITY. Candidate
identifiers are diagnostics only. No confirmation/revision bypasses an actual
unsafe-reader or round-trip compatibility failure. Publication itself still
requires separate explicit approval.
Legacy master publication no longer invokes exposure publication, and staged
publication remains independent of exposures. No publication was executed here.

Deepvue exact uppercase TPC still matches exact reference TPC in reference-layer
reconciliation, and TPC is also compatible with the consumer projection. These
are different questions. Diagnostic alias annotations never change exact match
status. All 29 source-native non-security records are handled through the exact
versioned disposition. All 23 historical crosswalks remain unapplied proposals,
including NXH/BBBY and SEPQ/TUGN quarantines.

## Staged outputs and immutability

Revalidation emits `compatibility-projection.csv`: every reference ticker, nullable
market-data symbol, reason, compatibility version and security type. `report.json`
includes totals, exclusion types/reasons and publication blockers. The receipt
binds the projection artifact as well as the exact reference Parquet.

The reference fingerprint and Parquet hash must remain unchanged. Only derivative
validation/projection reports change. Raw numbered pages, fetch state, copied input
artifacts and July's logical/physical snapshot remain untouched. Revalidation is
offline with HTTP/socket calls blocked.

## Legacy ingestion compatibility impact

The legacy ingestion command now publishes the master only. A successful command
no longer guarantees that an exposure snapshot exists or was refreshed. Its CLI
prints `exposure publication: not performed (disabled; separate workflow required)`. Existing
automations that depended on the former combined side effect must explicitly
schedule and validate a separately authorized exposure workflow; master success
must not be treated as exposure success. The CLI regression test verifies that
ExposureClassificationStore.persist is never called. This decoupling remains in
place under v2; no exposure publication occurred during this refinement.

Observed v2 projection: 13,155 exact references; 12,751 compatible symbols; 404
MIXED_CASE_REFERENCE_ONLY exclusions (354 PFD, 30 SP, 20 RIGHT); zero ambiguous
automatic conversions; two retained case-insensitive collision groups. Reference
Parquet bytes and logical fingerprint are unchanged.
