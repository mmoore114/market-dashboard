# Workstation snapshot V2 — AP-WORKSTATION-SNAPSHOT-002

The subsequent [offline local materializer](local-materializer-v1.md) implements
the explicit published-source boundary described below. Its actual local audit
is blocked; the normalized snapshot contract and existing engines are unchanged.

The first workstation repeated the complete Leadership and Regime populations
inside every Decision/Risk row. Its 12-record GREEN fixture occupied approximately
8,739,961 compact JSON bytes. Raising the loader limit would not solve that growth.
V2 normalizes the evidence before serialization, retaining every canonical field,
reason, null, setup and rule identity. No trading engine or UI calculation changes.

## Normalized contract

`WorkstationSnapshotV2` has schema identity `workstation-snapshot-v2`. It contains:

- identity, mode, aware generation time, as-of/action sessions and freshness;
- `shared`: source, universe, Leadership, Regime, rules and group references,
  the complete calendar, all workstation versions and the codec registry hash;
- `context_id`: a digest of shared content IDs and their metadata;
- `record_index`: sorted exact symbol/direction, name, nullable volume/reason,
  shared context ID and a reference to that key's normalized Decision/Risk output;
- `evidence`: a sorted table of unique immutable typed evidence nodes;
- canonical funnel counts and the snapshot logical fingerprint.

Each evidence node has a full SHA-256 `id` and a typed `value`. The value has a
numeric `model_type` and a fixed-length `fields` tuple. A field that originally
held a nested canonical model instead holds an integer address into the evidence
table. Scalars, nulls and ordered scalar arrays retain their exact values.
The integer is only a storage address: node hashes bind the full child content
IDs, and the shared context hash also binds content IDs rather than positions.
The table sorts by full content ID, making addresses deterministic for a given
logical snapshot. Equal models occupy one node even when separately instantiated.

The closed registry contains the 83 model types reachable through the declared
`DecisionRiskOutputV1` schema. It is derived from installed repository contracts,
never from a module/class name supplied by a local file. The registry hash binds
both canonical JSON Schema and field order. A schema change requires an explicit
catalog/migration decision; it cannot silently reinterpret an existing tuple.
[The generated schema and column catalog](workstation-snapshot-v2.schema.json)
map every numeric type and tuple column to its canonical source field and type.

This is lossless relational normalization, without gzip or removal of audit
fields. For example, a record's DecisionInput points to the one Leadership
object; RegimeInput points to that same object. Leadership points to indexed
symbol-strength and group rows. Group gates reference those same group rows.
Research-universe membership is stored once. Structure, Setup, all five raw/ranked
strength horizons, earnings inputs and evaluated evidence, every decision gate,
and sizing inputs/results remain available through typed references. Repeated
reasons, setup geometry and versioned components are also interned when equal.

## Materialization and validation

`snapshot_v2.materialize_v2` is pure. Supply canonical `SymbolRecordV1` engine
outputs and explicit source, universe, Leadership, Regime, groups, rules,
calendar, versions and snapshot metadata. Records can be an iterable, so a
producer need not retain thousands of expanded engine outputs. Input objects
remain unchanged. Supplied funnel counts are verified; omitted counts are counted
from the evaluated canonical states.

The converter interns the complete declared field set, resolves it through the
original canonical model validators, then validates snapshot-level relationships.
It rejects wrong hashes/types/tuple lengths, extra fields, missing references,
duplicate nodes/keys, unreachable nodes, cycles, and contradictory shared copies.
It checks exact symbol/direction/session/source/calendar/universe/rules identity,
Structure/Setup prices and timing, setup IDs/geometry, raw strength provenance,
symbol group membership, regime-gate agreement, event inputs and sizing context.
Two directions of a symbol cannot carry different direction-independent evidence.
No arbitrary first/last repeated copy is selected.

Only declared unordered populations are sorted: universe symbols, Leadership
symbols/groups, group members, Regime input indexes/breadth/style, Structure
breadth evidence and theme references. Snapshot keys and the evidence table are
also sorted. Price windows, setup lifecycle arrays, gate/reason order and event
records retain their original order. Generation-time changes, input row order,
dictionary insertion order and JSON whitespace do not change the logical digest.
All normalized content except the top-level generation time and digest field
is covered. In-memory decoded views are private, immutable derived caches and
are not serialized into snapshots.

Serialize with `snapshot.model_dump_json()`. The unchanged 32 MiB standalone
loader validates V2 only. V1 retains its original schema/meaning in Python for
explicit parity/migration tests; neither fixture nor local runtime accepts it.
V1 local files receive `SNAPSHOT_VERSION_UNSUPPORTED`. Rebuild from explicit
canonical outputs using `materialize_v2`; changing a version label is not a
migration. The loader performs no automatic scan, database query, provider call
or implicit materialization.

## API and UI compatibility

All existing `/api/v1` transport schemas remain unchanged, including the complete
symbol-detail evidence envelope. The API resolves typed references into its
existing read models; it does not store expanded payloads back in the snapshot.
OpenAPI and generated TypeScript are unchanged and their drift checks still pass.
Brief/Tape/Rules and every copied detail field are compared with the V1 source
in regression tests. Detail responses still include the complete legacy audit
envelope for the requested symbol; compacting that transport is separate work.

Sizer now requires an exact symbol/direction record. A missing direction returns
typed 422 `SIZER_DIRECTION_UNAVAILABLE`, with no fallback to another direction.
`sizing_input` constructs canonical `SizingInputV1` from the validated record and
its referenced shared context; `POST /sizer` still delegates to `size_idea`.
Valid SHORT records have their own tested adapter path. No share math moves to
TypeScript.

Fixture development uses V2. Navigation, styling, accessibility, visible
synthetic labels, missing-data states and session-only preferences are preserved.
Regenerated desktop/mobile browser evidence remains in `workstation-evidence/`.
Browser tests additionally verify 5/21-session columns and explicitly scroll the
390px Tape to reach its rightmost reason column.

## Measured scale evidence

Observed local diagnostic run (Python 3.13; times are not pass/fail thresholds):

| Measurement | Result |
|---|---:|
| Existing GREEN fixture records | 12 |
| Compact V2 GREEN JSON | 480,251 bytes |
| Reduction from 8,739,961-byte V1 baseline | 94.51% |
| Scale symbol/direction records | 2,000 distinct LONG symbols |
| Uncompressed V2 scale JSON | 18,834,442 bytes (17.96 MiB) |
| Bytes per scale record, including all shared evidence | 9,417.221 |
| Hard scale ceiling | 24 MiB |
| Unchanged operational loader ceiling | 32 MiB |
| Synthetic canonical-pattern construction and normalization | 86.41 seconds |
| Strict SnapshotStore load and validation | 13.18 seconds |
| Re-materialization from decoded canonical outputs | 24.68 seconds |

The roughly 13-second one-time local load is acceptable for this bounded offline
workstation startup; later publication/materialization work can profile it further.
The size ceiling is a hard test. Timings are diagnostic and deliberately have no
flaky hard assertion.

The scale fixture has 1,226 NONE, 5 WATCH, 268 TRADE and 501 ACT records. It uses
the existing twelve synthetic Structure/Setup/event patterns in six sub-industries
and an overlapping theme, with tied strength cohorts, varying setup counts,
explicit earnings BLOCKED/UNKNOWN/CLEAR and missing price/volume/strength values.
Each distinct numeric pattern/strength/group combination is evaluated by the
canonical Decision/Risk engine; identical input classes are rekeyed by exact-symbol
symmetry to keep the test practical. First, middle and last outputs are independently
re-evaluated by the canonical engine and compared in full. This is a reproducible
synthetic integrity fixture, not calibrated market-distribution evidence.

The test writes its large artifact and metrics only into pytest's temporary
directory. It validates through SnapshotStore, checks Brief totals, Tape
pagination/filter counts, exact detail and Sizer at first/middle/last keys, then
re-materializes reversed records and asserts byte-identical output. Provider,
socket and DuckDB access are forbidden; construction/API checks additionally
forbid file-open operations. The full scale artifact is not committed.

Scale logical fingerprint:
`866c148e05a11d5553fcc9d5a7571c83018cce0f0e8c11f4dc0e085bac712e40`.

## Commands and boundary

The [existing local startup commands](workstation-slice-v1.md) are unchanged.
Additional validation commands from the repository root:

```bash
.venv/bin/python -m pytest tests/test_workstation.py tests/test_workstation_v2.py tests/test_workstation_scale.py -q -s
.venv/bin/python -m pytest
.venv/bin/python -m api.export_snapshot_schema --check
.venv/bin/python -m api.export_openapi --check
.venv/bin/ruff check api src/market_dashboard/workstation tests/test_workstation*.py tests/workstation_scale_fixtures.py
.venv/bin/ruff format --check api src/market_dashboard/workstation tests/test_workstation*.py tests/workstation_scale_fixtures.py
cd web
npm test
npm run typecheck
npm run build
npm run lint
npm run test:browser
cd ..
git diff --check
```

Regenerate the standalone schema with `python -m api.export_snapshot_schema` and
synthetic UI responses with `python -m api.export_ui_fixture` using the project
interpreter, then run frontend formatting. Do not regenerate OpenAPI/TypeScript
unless its actual public transport contract changes.

This correction precedes real local materialization. DuckDB/Parquet processing,
provider/event retrieval, production/staged writes, portfolio heat/positions,
Groups/Book/Journal, hosting, authentication, brokerage and execution remain
deferred. The September security-master timestamp-precision publication blocker
is unrelated and remains unchanged.
