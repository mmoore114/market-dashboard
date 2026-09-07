# Current-state bootstrap V1

AP-CURRENT-BOOTSTRAP-001 separates a current decision scan from historical
membership evidence. Market observations end September 4, 2026 (T). The recorded
evaluation is September 6 at 9:53:42.451047 p.m. New York time (E), or September 7
01:53:42.451047 UTC. The first population/action session is September 8 (A).

The exact staged population has 101 covered symbols, 75 research members,
49 strict trade members and 25 mapping members. This is a bounded initial covered
population, not the full U.S. market. Membership rules and every instrument's
exclusion/eligibility reasons remain intact. Research membership is published only
from September 8; `select_snapshot` still returns no membership before then.

## Calculation provenance and compatibility

`current-state-bootstrap-v1` is an explicit optional provenance extension. It
carries `CURRENT_STATE_BOOTSTRAP`, `UNKNOWN_BEFORE_BOOTSTRAP`, `CURRENT_COHORT_AT_E`,
T/E/A, scope, population counts, actual first observations and gap counts.
The same metadata is bound into the plan, source manifest, universe, rank evidence,
normalized snapshot and its logical fingerprint, and is propagated into API views.

Only the bootstrap calculation adapter accepts a current cohort for retrospective
warmup. Its provenance retains the true September 8 effective/known session;
no earlier membership rows or synthetic dated universe are constructed. Current
cross-sectional ranks and breadth use all 75 research members, preserve each
component's valid denominator and UNKNOWN reasons, and are labeled as known at E.
Retrospective warmup outputs are not published. A normalized bootstrap snapshot
must identify exactly its declared current T; it cannot be sealed as an earlier
historical snapshot. Time Machine explicitly refuses pre-bootstrap requests and
does not offer these calculations as backtest evidence.

The canonical evidence registry intentionally changes because the dated provenance
schema now includes the versioned bootstrap extension. Its generated registry
fingerprint and tuple catalog are synchronized with the standalone V2 schema.
An old registry is never silently interpreted using new tuple columns: old files
must be rebuilt from their explicit inputs. There was no earlier real snapshot to
migrate. Legacy non-bootstrap numerical behavior and membership gates remain intact.

## Sparse histories

Five current research members have 914 absent leading XNYS slots in total. All
914 precede the respective first observation; the actual research population has
zero internal missing observations through T. Those leading slots are
`NOT_YET_OBSERVED`, never manufactured warmup observations.

Each symbol's engines start at its first actual observation. Their relative
indices are translated to XNYS dates using that explicit first-observation offset
at the Decision/Risk and snapshot validation boundaries. Setup ages and session
distances retain their existing mathematics. No observed date or value changes.

For an internal gap, the adapter supplies an explicitly null session slot to the
pure engines, with no OHLCV imputation and no persisted synthetic bar. Calendar
time does not compress. Existing missing-input and corrected-replay rules govern
recursive features, state and setup availability. The absent session does not
count as a valid streak. UNKNOWN evidence for one symbol does not remove it from
the population or suppress unrelated valid symbols. A focused sparse test checks
leading gaps, internal gaps, preserved dates/values, all-member denominators, and
exact independent Structure, Setup and Decision/Risk parity.

## Source and publication boundary

No acquisition/refetch is part of this milestone. The offline boundary rechecks
foundation hashes, publication completion, the exact population fingerprint and
DuckDB/Parquet agreement. The bootstrap manifest preserves UNKNOWN historical
provider receipt clocks; it binds the reviewed existing authority and actual
current artifacts rather than inventing old ingestion receipts. Reference facts
are decision controls retrieved by E, not historical September 4 market-cap facts.

Schedule publication writes the exact candidate JSON bytes to a new standalone
processed artifact. Its immutable intent and candidate copy precede publication;
a separate complete receipt is required by the bootstrap reader. Interrupted
staging or file publication recovers only with identical intent and candidate
bytes. Existing unowned/revised targets are refused. An identical complete
publication is a no-op. Real-candidate simulations precede publication, and a full
verified database backup plus candidate copy are retained. The production database
and every completed foundation artifact remain byte-identical.

The current decision context expires at September 8 00:00 UTC, before the action
session. This is an operational current-scan boundary, not a fabricated provider
freshness attestation or a change to a research threshold. The snapshot carries
`CURRENT_DECISION_CONTEXT` freshness evidence; individual missing inputs retain
UNKNOWN. In particular, no September 4 VIXCLS close is fabricated or forward-filled.
The existing Volatility sleeve handles the missing observation canonically.

## Workstation surfaces

The shared context shows LOCAL_SNAPSHOT, calculation mode, T, E formatted in New
York, A, bounded scope, current-cohort rank basis, population/gap counts and source
fingerprint. Rules exposes the existing rule fingerprints. Brief retains canonical
funnel and sleeve evidence; Tape/detail and Sizer use the exact normalized records.

Groups has a read-only API/view with explicit missing membership evidence when no
published group source exists. No raw Deepvue capture or crosswalk is consumed.
Time Machine returns `UNKNOWN_BEFORE_BOOTSTRAP` for dates before September 8;
other dates still require a separately available historical snapshot.

For browser verification, set `APERTURE_REAL_SNAPSHOT` to the exact standalone
snapshot file and run `npm run test:browser` in `web`. This selects the real
bootstrap desktop/mobile smoke suite and starts only loopback services. Without
that explicit setting, browser tests retain their synthetic fixture mode. Neither
mode invokes providers or materializes data on demand.

## Verification receipt

Final observed snapshot, test and preservation results are recorded in
PROJECT_STATE and CODEX_NEXT_TASK. Private plans, build receipts, source records,
backup inventories and browser/API receipts stay outside Git.
