# Aperture Workstation V1

AP-WORKSTATION-SLICE-001 adds a local, single-user React interface over the
completed Python engines. All thresholds remain `experimental_uncalibrated`.
ACT means discretionary review; the workstation cannot submit orders.

## Local development

Use Python 3.11+ and Node 22.12+ from the repository root:

```bash
.venv/bin/python -m pip install -e '.[dev]'
cd web
npm ci
cd ..
```

In one terminal, start the API on loopback:

```bash
APERTURE_MODE=FIXTURE .venv/bin/python -m uvicorn api.main:create_app \
  --factory --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd web
npm run dev
```

Open `http://127.0.0.1:5173`. Vite forwards `/api` to the local API. The default
mode is FIXTURE; credentials and an `.env` file are unnecessary. The API does not
load `.env`. The exact allowed frontend CORS origins are localhost and 127.0.0.1
on port 5173, without credentials. Production assets are built with `npm run build`;
remote hosting and authentication are outside this milestone.

Set `APERTURE_FIXTURE_SCENARIO=GREEN`, `YELLOW`, or `RED` on the API process to
select a synthetic regime scenario. Each scenario is a coherent separate
snapshot; individual rows never contradict its common regime. Every screen and
response identifies `SYNTHETIC FIXTURE`. Its calendar, security master, prices,
volumes, groups, earnings and symbols are fictional and deterministic. Fixture
freshness describes the fixture's dated scenario, not current market coverage.
Restart the API after changing mode, scenario or the snapshot file.

## Explicit local snapshot mode

```bash
APERTURE_MODE=LOCAL_SNAPSHOT \
APERTURE_SNAPSHOT_PATH=/path/to/review.local-snapshot.json \
.venv/bin/python -m uvicorn api.main:create_app --factory \
  --host 127.0.0.1 --port 8000
```

The path must identify a standalone JSON snapshot, at most 32 MiB, outside
Deepvue/staging and production raw/processed/database directories. It must carry
`mode=LOCAL_SNAPSHOT`. There is no database query, provider call, directory scan,
implicit data build, or fixture fallback. JSON is loaded once at startup;
freshness is rechecked on each request. Missing files, invalid contracts,
unsupported versions, fingerprint mismatches, future timestamps and expired or
unknown freshness block all research routes. Health remains available with typed
reasons, and the UI shell retains navigation. The caller explicitly supplies
`freshness.valid_until`; V1 does not invent a market-session TTL.

The later real materializer must construct this complete contract from verified,
point-in-time published inputs, provide a real exchange calendar and attested
freshness, preserve every version identity, and use `seal_snapshot`. This
milestone deliberately does not implement that materializer. Relabeling a fixture
does not make it real market evidence.

## Snapshot and transport contracts

`src/market_dashboard/workstation/models.py` owns frozen, extra-field-forbidding
Pydantic contracts. `WorkstationSnapshotV1` retains the source and calendar,
security-master/exposure/universe/feature/engine/rules identities, full regime
evidence, group evidence, funnel counts and one complete Decision/Risk output
per exact symbol/direction. That output retains all canonical inputs, components,
setup instances, gates, reasons and sizing context. Volume is separately nullable
with an explicit reason. Missing values remain null throughout the API.

The SHA-256 logical fingerprint covers JSON logical content except the top-level
generation timestamp and the fingerprint field itself. All nested evidence
timestamps remain covered. Validation rejects duplicate symbol/direction keys,
inconsistent dates/source/regime/universe/groups/funnel and any content-digest
mismatch. Action session is the exact next supplied exchange session. A digest
detects corruption; it is not authentication or a claim of provider accuracy.

`projections.py` selects and formats read models without changing engine states.
Brief leading groups are the first five known sub-industry leadership ranks;
weakening context is the five lowest negative median rotation deltas. These are
display selections, not new group or decision classifications.

All routes use `/api/v1` and `Cache-Control: no-store`:

| Route | Behavior |
|---|---|
| `GET /health` | Availability, mode, freshness, dates, version and reasons; remains readable on failure |
| `GET /brief` | Five sleeves, regime, funnel, groups, ACT queue and explicit unavailable portfolio heat |
| `GET /tape` | Bounded pagination, allowlisted sorting and component filters |
| `GET /symbols/{symbol}` | Exact case-sensitive identity and every direction's full evidence |
| `POST /sizer` | Delegates proposals to canonical `size_idea` with snapshot regime/earnings/ATR context |
| `GET /rules` | Effective configured thresholds, immutable policy constants and fingerprints |
| `GET /openapi.json` | Versioned generated transport schema |

Tape supports `action`, `structure`, `setup`, `min_rs_comp`, `min_rs_rotation`,
exact sub-industry `group`, and `veto`. Sort fields are `symbol`, `price`,
`RS_comp`, `RS_rotation`, `rotation_delta`, `extension_atr`, `decision`, and
`group_rank`; order is `asc` or `desc`. Nulls sort last in both directions.
Equal values use ascending exact symbol then direction. Decision sorting is
lexical. Page size is 1–100 (default 25), page is 1–100000 (default 1); pages
beyond available results are empty with unchanged total/page metadata.
Invalid filters and sorts return 422. An absent valid symbol returns 404.
Errors use `workstation-error-v1` with code, message and optional field details;
raw request values, file contents, absolute paths and stack traces are not echoed.

Sizer accepts exact symbol, LONG/SHORT, equity, buying power, entry and stop.
Nullable numbers reach canonical refusal handling. It does not select a stop
from setup invalidation or duplicate share math in JavaScript. Both theoretical
and capital-constrained full/pilot amounts remain visible on refused results,
clearly labeled unavailable. SHORT illustrations do not enable SHORT promotion.

## Interaction and verification

Persistent navigation exposes Brief, Tape, Sizer and Rules. Groups, Book and
Journal are disabled planned destinations. Session storage contains only table
filters/density and selected drawer symbol. Snapshot payloads and financial form
values stay in memory. The detail uses a modal dialog with Escape/focus return;
chart handoff is copy-symbol/manual Deepvue review, with no invented URL.
HTTP requests time out after 15 seconds and views expose retry/error states.
The shell refreshes health every 30 seconds and blocks content on expiry.

```bash
.venv/bin/python -m pytest tests/test_workstation.py
.venv/bin/python -m pytest
.venv/bin/python -m api.export_openapi --check
.venv/bin/ruff check api src/market_dashboard/workstation tests/test_workstation.py
.venv/bin/ruff format --check api src/market_dashboard/workstation tests/test_workstation.py
cd web
npm test
npm run typecheck
npm run build
npm run lint
npx playwright install chromium
npm run test:browser
cd ..
git diff --check
```

The checked-in OpenAPI document is deterministic. `npm test` verifies generated
TypeScript against it before component tests. Regenerate intentional transport
changes with `.venv/bin/python -m api.export_openapi`, then `npm run generate:api`
from `web/`. The committed frontend examples are fully synthetic API responses,
generated with `.venv/bin/python -m api.export_ui_fixture` and formatted by
`npm run format`.

Browser tests start both local fixture processes, exercise real HTTP routes at
1366px and 390px, verify filter persistence, Escape/focus return and sizing, and
capture screenshots under `docs/workstation-evidence/`. These images contain only
fictional fixture content. See PROJECT_STATE for observed validation totals.

No existing engine, immutable rule configuration or legacy output semantics are
changed. Real snapshot materialization, ingestion, publication, portfolio heat,
positions, Book, Journal, backtesting, hosting and execution remain deferred.
