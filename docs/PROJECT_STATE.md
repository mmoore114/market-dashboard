# Aperture Project State

Updated: 2026-09-07

Current product authority: `docs/APERTURE_CURRENT_AUTHORITY.md`

Working prototype baseline: `401e1b0afd6ad2a4678af4f1040014b5c9b568e9`

## Current outcome

Aperture has a working local React/TypeScript Workstation backed by FastAPI and a
real normalized `LOCAL_SNAPSHOT`. The snapshot was built as a truthful
`CURRENT_STATE_BOOTSTRAP` using market evidence through September 4, an evaluation
on September 6 New York time, and September 8 as the first action/population
session.

Validated snapshot facts:

- 75 equity-research members;
- 49 strict equity-trade members;
- 25 market-mapping members;
- funnel: 66 `NONE`, 9 `WATCH`, 0 `TRADE`, 0 `ACT`;
- size: 1,865,976 bytes;
- logical fingerprint:
  `d10b6c0b62d403755aa7be08e8c378fb7b694c3c1254cbfcc2ff282b899b8012`;
- Python, frontend, schema/type, build/lint, and desktop/mobile browser verification
  passed at the recorded baseline;
- snapshot and retained backups remain local and uncommitted.

The Workstation services were stopped cleanly after verification. The prototype
can be relaunched from the retained local snapshot.

## Implemented layers

- Massive-backed security and adjusted daily-bar foundation;
- DuckDB/Parquet storage with provider-preserving fractional volume;
- versioned exposure and universe policies;
- pinned XNYS exchange calendar and source provenance;
- deterministic Structure and Setup V1 engines;
- Leadership/RS and group-ranking engine;
- five-sleeve Market Regime engine;
- Decision/Risk, actionability, and sizing engine;
- normalized snapshot V2 and offline materializer;
- typed FastAPI service;
- React Workstation surfaces: Brief, Tape, symbol detail, Groups, Sizer, Rules;
- current-state bootstrap and Time Machine refusal before historical membership is
  available.

## Known product gaps

- The current snapshot does not contain published group membership, so Groups
  presents explicit missing evidence.
- Deepvue sub-industry and theme captures are verified bootstrap sources but remain
  local and are not runtime dependencies.
- Earnings/catalyst coverage is incomplete.
- The initial population is bounded, not the full U.S. equity research universe.
- Book, Journal, benchmark learning, and routine daily refresh remain future work.
- The current UI needs user-driven workflow and visual refinement.
- Aperture intentionally does not include charts; Deepvue handles chart review.

## Engine alignment status

The runtime V1 engines remain reproducible and unchanged. They do not yet reflect
all settled target decisions in `APERTURE_CURRENT_AUTHORITY.md`.

Most important target divergence:

- runtime Structure V1 uses EMA10/SMA20/SMA50 stack predicates;
- the settled target Structure model uses the final Word specification's
  SMA20/SMA50 ATR-normalized design, with EMA10 and SMA200 as context only;
- runtime shock rules can enter mature states immediately, while the target uses
  transitional shock states;
- target setup lifetimes allow RANGE up to 60 sessions and CONTRACTION initially
  up to 40 sessions while geometry remains valid.

Accepted Git V1 safety behavior—including frozen T-1 references, stable identity,
event ordering, no-look-ahead, corporate-action quarantine, missing-data evidence,
failure precedence, terminal non-reactivation, and corrected replay—remains part of
the target design.

No engine code or existing snapshot was changed by the documentation-authority
cleanup. A later explicitly authorized milestone must implement new versions and
rebuild the snapshot.

## Repository and data safety

- GitHub is the code source of truth.
- Work on feature branches and use draft pull requests.
- Do not merge without explicit authorization.
- Preserve `.vscode/settings.json` and unrelated user changes.
- Never commit credentials, provider exports, databases, Parquet data, snapshots,
  receipts, backups, or machine-specific paths.
- Historical V1 code, outputs, tests, and milestone evidence remain preserved.

## History

The complete cumulative project-state record through the first real bootstrap is
preserved at `docs/history/PROJECT_STATE-through-current-bootstrap-v1.md`.
Historical task receipts and implementation documents remain available under
`docs/`; consult them only when routed by a current task or when auditing provenance.

## Next work

No engine change is authorized merely by this status file. See
`docs/CODEX_NEXT_TASK.md` for the current assignment state and the proposed bounded
next milestone.
