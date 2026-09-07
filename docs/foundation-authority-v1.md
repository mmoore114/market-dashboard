# Foundation authority V1

**Subsequent operation:** the owner separately approved and completed the production
volume correction on September 6, 2026. See the latest PROJECT_STATE entry for
backup and corrected hashes and independent validation. The milestone results
below describe the original offline run before that approval. Its preserved
receipts retain the old production hash and are historical evidence. The actual
transaction also temporarily dropped and identically recreated the existing
ticker/date index, as required by DuckDB and verified in a full-copy rehearsal.

AP-FOUNDATION-AUTHORITY-001 establishes the reviewed XNYS calendar and adjusted
volume representation, and verifies a recoverable correction on a staged copy.
Production remains unchanged. No market-data request or real snapshot build ran.

## Reviewed source profile

`config/adjusted_source_authority_v1.yaml` and frozen `AdjustedAuthorityV1` define
`massive-adjusted-authority-v1`, reviewed September 6, 2026:

- Provider/dataset: Massive.com stock custom daily aggregates.
- `adjusted=true` means split-adjusted prices, not dividend total return.
- Volume uses matching provider-returned split-adjusted numeric values stored as
  DOUBLE. Existing reviewed fractional Parquet values are authoritative for those
  observed rows; rounded DuckDB BIGINT values are lossy derivatives.
- Transaction count remains integral.
- Representation authority does not authenticate absent historical responses,
  repair a database, establish a validity interval, or publish a source manifest.

These owner-reviewed decisions implement the handoff's references:
[Massive custom bars](https://massive.com/docs/rest/stocks/aggregates/custom-bars),
[exchange_calendars](https://github.com/gerrymanoim/exchange_calendars), and
[release 4.13.2](https://github.com/gerrymanoim/exchange_calendars/releases/tag/4.13.2).
No additional provider documentation or market-data request was needed.

## Calendar

The direct dependency is pinned to `exchange-calendars==4.13.2`. Installation
added only its missing resolver-required dependencies: pyluach 2.3.0, toolz 1.1.0,
tzdata 2026.3, and korean_lunar_calendar 0.4.0. Existing numpy/pandas were retained.
Only package-installation network access was used, in addition to authorized Git
publication. Calendar generation and validation are offline.

`xnys_calendar.generate_xnys(start, end)` uses a fresh XNYS implementation instance
and returns the unchanged `CalendarV1`. It checks the exact installed version,
identity, ordered unique sessions, request bounds and aware closes, converting
closes to UTC. Local close evidence uses America/New_York, including DST and early
closes. Supported adapter bounds are 1990–2100 and at most 3,653 calendar days per
request; these are operational limits, not research thresholds. Invalid/empty
ranges and naive clocks are refused. Observed bar dates never define sessions.

The actual candidate covers January 2, 2024 through September 8, 2026: **673
sessions**, including **six early closes**. Independent regeneration agrees
exactly. Its canonical JSON bytes and logical fingerprint are both:

`951e46f98b60d704a82fcceed8a6b9fa33fbe029aa47a912769a21b0a4e7537d`.

The historical July 24 / July 27 pair is calendar-adjacent. At the explicit plan
clock, the calendar-only latest completed T is September 4, with next session
September 8; Labor Day is excluded. This is **not** a feasible materializer target.
The immutable rules effective date remains August 25, 2026. Master, exposure,
universe, adjusted bars, benchmarks, spot and provenance must independently be
valid for a chosen post-effective-date T. July identity is never back-projected,
and the unpublished September master is never consumed.

## Writer and downstream audit

New `daily_bars` tables store volume as DOUBLE. Ordinary ingestion preflights an
existing schema before requests or writes, and rechecks before Parquet/DuckDB
writes. Existing BIGINT or otherwise incompatible volume columns produce
`ADJUSTED_VOLUME_MIGRATION_REQUIRED`; ordinary ingestion never alters them.
The backfill runner checks before creating a job manifest. Materializer auditing
adds an explicit hard blocker for a selected native integer-volume table while
retaining its read-only diagnostics.

| Consumer | Result |
|---|---|
| API mapping | Numeric `v` retained; booleans, nonfinite/negative values, nonrepresentable integer-to-DOUBLE values and fractional transaction counts refused. |
| pandas / Parquet | Volume explicitly float64; fractional values preserved. Valid transaction counts use nullable Int64. |
| Daily DuckDB writer | New DOUBLE schema; existing incompatible schema refused before mutation. No auto-migration. |
| Feature storage | Both new `daily_equity_features` and `latest_equity_snapshot` volume definitions are DOUBLE; existing incompatible tables fail before any feature writes or additive column migration. |
| Pure liquidity/features | Arithmetic and rolling calculations already retain fractional values. No formula or threshold changed. |
| Structure/Setup adapters and replay | Existing float-valued volume inputs and means are retained. Integer conversions apply to session/count fields, not volume. |
| Leadership/Regime/Decision/V2 | Existing canonical float contracts, projections and normalized graph semantics unchanged. |
| Flat-file raw layer | Separate unadjusted dataset; existing numeric representation remains separate and unchanged. |
| Hashing/comparison | Exact scalar integer/float comparison and complete field fingerprints retained; no rounding tolerance introduced. |

Existing feature tables may also require a separately reviewed correction/rebuild.
Correcting `daily_bars` alone does not authorize overwriting historical feature
outputs or unblock an incompatible feature-table schema. Legacy formulas, engine
versions, immutable Aperture rules, original Parquet files and recorded outputs
are preserved. Successful-workflow synthetic fixtures now declare the supported
DOUBLE schema; dedicated tests verify refusal and preservation of legacy BIGINT.

`MassiveClient.last_response_evidence` and ingestion summary `response_evidence`
provide frozen `adjusted-response-evidence-v1` records. They allowlist endpoint
class, exact ticker, requested/returned adjusted flags, source version, requested
and observed bounds, row count, HTTP status and mapped-artifact fingerprint.
Missing returned flags stay null. Contradictory flags, redirected responses,
unexpected pagination and mismatched identities are refused. Raw bodies, headers,
keys, full URLs/query strings and arbitrary provider metadata are never retained.
The backfill manifest can retain these sanitized records in a separate
`adjusted_response_evidence` table, keyed by job/ticker and full receipt digest.
No existing production manifest was opened for writing in this milestone.

## Offline plan / simulate / validate

The frozen `FoundationAuthorityPlanV1` embeds the exact original reconciliation
selection, a `VolumeMigrationPlanV1`, the reviewed profile SHA256, explicit calendar
end and aware evaluation clock. Plans use literal JSON so planning has zero file,
database or network reads and no filesystem writes. The shell's explicit plan
read in these examples occurs before the CLI; programmatic callers can pass
in-memory models to the pure describe functions.

```bash
.venv/bin/python scripts/foundation_authority.py plan \
  --plan-json "$(cat "$AUTHORITY_PLAN")"
.venv/bin/python scripts/foundation_authority.py simulate \
  --plan-json "$(cat "$AUTHORITY_PLAN")"
.venv/bin/python scripts/foundation_authority.py validate \
  --plan-json "$(cat "$AUTHORITY_PLAN")"
```

There are deliberately no production `apply`, `publish` or `fetch` modes.
`describe_migration`, `simulate_migration` and `validate_migration` also expose the
narrow copied-only workflow programmatically, including durable interruption and
recovery boundaries. Simulation output stays directly beneath the explicit
workstation staging workspace; original inputs cannot overlap it. Symlinks and
unsafe paths are refused, and initial copied-database publication uses atomic
no-replace creation. A competing output is never overwritten.

Simulation checks the original source hashes and BIGINT schema, requires identical
unique non-null `(ticker,date)` keys and all non-volume fields, and replaces only
volume from the exact Parquet values in memory before creating a **new** database.
All production connections are read-only with DuckDB external access disabled.
The copied database's metadata binds its exact plan/source hashes. Durable states
are `pending`, `recovery_required` and `complete`; interrupted copies remain
unusable until verified recovery. The actual staged run exercised a pending
interruption, post-replacement recovery-required state, verified recovery and an
identical no-op. Complete reruns validate read-only and preserve database bytes.
Changed inputs, incompatible schemas, duplicate/null/missing/extra keys,
non-volume differences and output corruption are refused.

Actual simulation results:

- **63,279 rows**, with all original keys retained.
- **11,607 fractional values restored**; zero remaining field mismatches against
  all 100 declared Parquet copies, zero duplicate keys and invalid/null OHLCV.
- Volume DOUBLE and transactions BIGINT; no production schema alteration.
- Logical row fingerprint:
  `922654711bd0040fab863afa35631fafc86f859ad6df944184dd49c96ee3076b`.
- Staged database SHA256:
  `c1aefcb29535570a7be9069d8ed86898085e343f7e341b443c54358de2cdf386`.

Physical database bytes bind this particular simulation; logically identical
independent databases need not have identical physical layouts. Validation
recomputes complete field equality and source bindings, not just a stored digest.
Receipts detect drift/corruption, not an adversary forging every source and receipt.

The private evidence contains exact backup and SHA verification argument arrays,
maintenance prerequisites, ordered transactional ALTER/UPDATE/verification SQL,
conditional commit/rollback instructions, and full-backup restore arguments for
later approval. The transaction must not commit unless its all-field difference
query returns zero. Retain exclusive maintenance through post-apply verification
or rollback, check for active connections/WALs, and preserve unrelated tables and
sidecars. These statements are a reviewable plan; this code cannot dispatch them.

## Reconciliation outcome and boundaries

The existing reconciliation is rerun with the pinned calendar adapter and reviewed
profile. Original receipts and the previous reconciliation bundle remain unchanged.
All **eight original finding identities** are conserved:

| Finding | Current disposition |
|---|---|
| Calendar missing | Resolved by independently verified pinned candidate; not published. |
| Legacy universe copy disagreement | Remains resolved by lossless DATE equivalence. |
| Adjusted bars copy disagreement | Representation authority established; still requires separately approved production correction/publication. |
| Source manifest missing | Requires local evidence review: semantic fields are established, missing historical facts remain UNKNOWN. |
| Legacy universe is not Aperture schedule | Requires publication after identity, dated market cap, effective membership and retention prerequisites. |
| Master after historical T | Historical timing constraint remains; current validity is not inferred from an old snapshot. |
| Required benchmark missing | QQQE remains absent; separate bounded acquisition needed. |
| Spot missing | Requires reviewed non-security provider identity/dataset/endpoint/entitlement before any acquisition. |

Thus two original findings are resolved and six remain blocked: two for local
review, two for publication/correction, and two for bounded acquisition. The
separate rules-effective-date finding remains correct for historical T. A separate
`PRODUCTION_VOLUME_CORRECTION_UNAPPLIED` finding makes representation authority
and production state explicit.

The historical SPY, QQQ, IWM and RSP copies each cover all **642 expected sessions**
through July 24, with no gaps and sufficient benchmark warmup. QQQE lacks all 642.
Research coverage remains unknown without a valid dated population; spot identity
and history remain absent. Provider/dataset, split-adjusted price, no dividend
return adjustment and matching numeric volume semantics are now established.
Observation/fetch/publication times, validity/freshness intervals and complete
source bindings remain UNKNOWN. The candidate is still not a complete `ManifestV1`.

Authority plan fingerprint:
`a93986a0ca3a782b42e519480b4b8e53f62ebdae8c843211ce3c3fb31953f126`.
Independent authority evidence fingerprint:
`c48a1d5705d8b8cc0cd940b14077d5f2276a13c229feeffa63866a770551964c`.
All **348 protected pre-work files** retained their SHA256s, including original
production data, prior audit evidence, September provider staging, environment
and user settings. Private calendars, plans, copied databases and reports stay
outside Git.

The optional conditional current-bar fetch was not used: zero HTTP attempts and
zero provider records. It is unnecessary to establish this offline authority and
cannot cure the missing identity/population/spot evidence. No VIX, master,
market-cap, taxonomy or event request occurred.

**Next bounded action:** review and separately approve only the exact staged
BIGINT-to-DOUBLE production correction, with verified backup and an exclusive
maintenance window. Calendar/provenance publication, derived-feature rebuilding,
current bars/QQQE acquisition and an identity-valid Aperture schedule remain
separate boundaries. No real snapshot build is authorized.

PROJECT_STATE records final observed test totals. Coverage includes pinned-calendar
holidays/early closes/timezones, fractional API/storage/features, old-schema
refusal, metadata allowlisting, pure planning, recovery/no-op/input drift, null and
non-volume mismatch refusal, no production writes and unchanged snapshots/engines.
