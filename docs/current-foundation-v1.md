# Current foundation V1

Historical milestone receipt. The subsequent [current bootstrap](current-bootstrap-v1.md)
resolves the representation blocker below and builds the first real snapshot.

AP-CURRENT-FOUNDATION-001 completed the safe acquisition, correction, publication,
and feature prerequisites. **The first real snapshot remains blocked by the
historical population/replay contract.** No schedule or snapshot was published,
and no production API was started. This is not a live/current Workstation result.

## Published foundation

| Input | Independently verified result |
|---|---|
| September master | 13,155 exact reference identities; September 5 artifact and fingerprint unchanged; publication complete. |
| Adjusted bars | 66,951 rows, 101 symbols, January 2, 2024–September 4, 2026; 14,743 fractional volumes; zero duplicate keys or full-field Parquet differences. |
| Calendar | exchange-calendars 4.13.2 / XNYS; 682 sessions through September 21, 2026, with actual aware closes and early closes. |
| Spot | FRED VIXCLS / canonical `$VIX`; 671 non-null XNYS observations through September 3. September 4 remains missing/UNKNOWN. |
| Reference facts | 75 current ticker-detail records for the covered common stocks, with market caps present; provider market-cap as-of timestamps remain UNKNOWN. |
| Exposure | exposure-policy-v3 for September 5; 12,751 compatible identities, with 404 incompatible exact reference identities preserved separately in the master. |
| Derived features | 66,951 daily rows and 101 latest rows; DOUBLE volume; full-field parity with the existing feature pipeline's calculations. |
| Provenance | Published `current-foundation-provenance-v1`, binding current artifacts, actual retrieval/publication receipts and explicitly unknown historical facts. Not a falsely completed canonical materializer manifest. |

The initial reviewed backfill plan contains 100 symbols. The required ETF set adds
only QQQE after deduplication. SPY, QQQ, IWM, RSP and QQQE each cover all 672 XNYS
sessions through September 4. This bounded population is not the full U.S. market.

## Exact timestamp publication

The immutable September source contains nanosecond `last_updated_utc` values.
The confirmed master publisher now uses TIMESTAMP_NS, representing UTC with no
implicit timezone conversion, truncation, or rounding. Within its transaction it
copies existing rows into an exact-DDL shadow table, changes only that column's
precision, and preserves constraints and index definitions before inserting the
September slice. DuckDB cannot recreate the dropped UNIQUE index after a simple
ALTER in the same transaction; a full-table transactional replacement avoids that
problem while preserving July values.

Real-artifact tests repeat first publication, identical no-op, staged/committed/
renamed interruptions, recovery, changed-same-date refusal, exact comparison and
July preservation on disposable copies. The actual publication held an exclusive
maintenance connection through backup, publication and checkpoint. A fresh
read-only connection independently verified the result.

Unchanged September logical fingerprint:
`7d22fab5f8dbffea1c9254124e9c2731006648391519e55543f6058c77c7112b`.
Unchanged September Parquet SHA256:
`d3bd5b75665c646e109e22514839da6771b49070f4ed2998b5e879cdb16fc8fc`.

## Bounded acquisition and recoverable publication

`scripts/current_foundation.py` exposes literal-JSON `plan`, explicit-workspace
`fetch`, and independent `validate` modes. Planning performs no source reads or
writes. Fetch is the only network boundary. Plans declare exact symbols, sessions,
ranges and source hashes; staging cannot target the repository or immutable
master/Deepvue workspaces. Existing workspaces cannot automatically retry/resume.
Attempt reservations are durably recorded before HTTP. Redirects, pagination,
identity/basis disagreements, invalid keys/OHLCV and cap breaches refuse the page.
Completed pages and sanitized receipts survive a later failure. Keys, headers,
full URLs/query strings, raw errors and arbitrary provider fields are not saved.

Observed retrieval totals, with no retries:

| Source | Attempts / cap | Returned rows / cap |
|---|---:|---:|
| Massive adjusted aggregates | 101 / 125 | 3,672 / 25,000 |
| Massive current ticker details | 75 / 110 | 75 / 110 |
| FRED VIXCLS CSV | 1 / 2 | 698 / 1,000 |

All fetches completed and were independently revalidated offline. Current ticker
requests have no historical date parameter: their planning context is September
4, but their values are decision-time evidence available at retrieval, never
September 4 market-cap attestations.

The FRED source is [Cboe Market Statistics via FRED VIXCLS](https://fred.stlouisfed.org/series/VIXCLS),
a daily-close non-security series. Source attribution/copyright information is
retained in its versioned metadata. All 698 observations remain in immutable
staging, including seven missing values and 20 non-null observations outside the
XNYS calendar. The published session projection contains 671 observations and
performs no forward fill. A missing September 4 close retains the existing
Regime volatility UNKNOWN behavior, not an invented proxy or whole-snapshot veto.

Bar publication first verified an append-only full candidate against the existing
63,279 rows. It retained a full database and partition backup, committed the
increment with a pending publication record, published exact candidate partitions,
verified every field, and marked completion. Interrupted committed publication
recovers only from the same candidate hashes. Full-artifact interruption/recovery/
no-op simulation preceded the real write. Prior values and timestamps are intact.

The exposure store accepts an optional caller-owned connection, allowing one
exclusive maintenance lock to span its existing recoverable protocol. The complete
September exposure simulation passed interruption/recovery/no-op before production.
No crosswalk was applied, and prior exposure publications remain unchanged.

The feature candidate used a copy of the database and the existing pure pipeline.
All candidate daily values were independently recalculated and compared. The two
validated tables replaced only the corresponding production feature tables inside
a transaction, following a full-copy rollback rehearsal. Original feature outputs
remain in the complete retained backup. Existing formulas and thresholds did not
change; obsolete derived values were not carried into the new current rows.

## Three-clock extension

Optional `EvaluationV1` metadata extends V1/V2 snapshots and API metadata compatibly:

- `market_as_of_session` (T): September 4, 2026;
- `evaluation_timestamp` (E): actual evaluation, with timezone/UTC offset;
- `action_session` (A): September 8, 2026;
- explicit population scope and per-input role, observation/effective date,
  availability timestamp and artifact hash.

Actual operational receipts were produced September 7 UTC, still September 6 in
New York. The next XNYS action remains September 8; September 7 is a holiday.

An explicit current materialization plan checks that T is the latest completed
session at E. Market observations cannot follow T; source availability cannot
follow E. Decision-time reference/control evidence can be effective after T when
known by E and valid for A. The September master therefore need not be backdated.
Legacy plans keep their original close-time gates. The extension does not alter
historical universe selection or engine formulas.

Absent evaluation metadata is omitted from serialization, preserving legacy
snapshot content/fingerprints. Present metadata participates in the fingerprint
and must agree with top-level market/action dates and generation time. API metadata
preserves it, and the shared Workstation context displays market, evaluation and
action clocks plus scope. A focused test verifies that clocks do not change any
canonical symbol or Regime output.

## Remaining population/replay contract blocker

The immutable universe evaluator produced a staged first-action candidate with
75 research members, 49 strict trade members and 25 market-mapping members. It uses
no prior-retention membership or invented fields. The first truthful known and
effective XNYS session is September 8. The source controls were observed after the
September 4 close. The candidate is explicitly **not published**.

`DatedProvenanceV1` rejects a known/source date after its effective date.
`select_snapshot(..., September 4)` therefore returns no research population.
The existing materializer requires such a population for September 4 and each of
its 672 prior/current replay sessions. Publishing September's master or calling a
population "initial covered" does not supply those historical denominators.
Backdating the current market-cap/identity evidence would rewrite market-derived
ranks and breadth, which the handoff explicitly prohibits.

There is a related existing replay constraint: five otherwise eligible stocks
have 914 missing prefix/internal calendar slots in aggregate. Existing per-symbol
bar indices cannot satisfy the shared-calendar Decision/Risk index contract for
those histories. They were not dropped, reindexed, forward-filled or given invented
pre-listing bars. Details remain in the private readiness proof.

This is a historical-population/replay representation blocker, not a calendar wait,
missing Massive entitlement, request-cap failure, or FRED-lag veto. A canonical
materializer manifest/snapshot was not sealed around incomplete schedule evidence.
No stale, synthetic, partial or historical artifact was presented as the requested
real snapshot.

**Next bounded decision:** provide verifiable historical research membership or
review a versioned current-state bootstrap/replay contract that explicitly handles
unknown past membership and per-symbol calendar alignment. Preserve all numerical
rules and avoid imputing past ranks or breadth. Simply waiting for September 8
does not create the missing historical evidence.

## Preservation and evidence

Before work, 358 files were inventoried. The intentional pre-existing file changes
are the production DuckDB and 100 updated bar partitions. The other 257 hashes,
including immutable September staging, July master bytes, previous receipts,
environment and user settings, remain unchanged. New QQQE, September publication,
calendar/spot/reference/provenance artifacts are separately inventoried. All full
backups remain retained; no merge or cleanup of backups occurred.

Final checkpointed production SHA256:
`ae5890020e2701be93dc7b24916405c9106d1c8ff309dd475d9a38addf509a9a`.
Current provenance logical fingerprint:
`772410aade01af1cae35dec27dcbb16ae182e1518018757db11c70f96a2748f8`.
Calendar logical fingerprint:
`bc16946781af23125ead762bd76f2d6d159172064ce56cd589956e7557577e4e`.
Exposure fingerprint:
`3a4a3844738754a0371dbe3cfc41c100109963682d886162b01ac100207e22c9`.
Staged action-population fingerprint:
`c43ae163b2a4403da7b98e0262c857f027bc7770946bf5713b88889621c1a196`.

Plans, market rows, exact paths, backups, source receipts, candidate databases and
preservation inventories stay private and outside Git. PROJECT_STATE records
final observed verification totals. Browser checks use the synthetic fixture only;
there is no real snapshot path or production-route smoke result to report.
