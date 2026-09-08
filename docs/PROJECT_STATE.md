# Aperture Project State

Updated: 2026-09-08

Current product authority: `docs/APERTURE_CURRENT_AUTHORITY.md`

Working prototype baseline: `401e1b0afd6ad2a4678af4f1040014b5c9b568e9`

## Session closed — 2026-09-08 07:39 UTC

The owner requested safe shutdown. Refresh timer was **enabled and active**;
it is now **enabled but temporarily stopped**, with configuration unchanged.
The last refresh finished successfully at 07:34:34 UTC (`ALREADY_CURRENT`). No
refresh/build was running at shutdown. Workstation API/frontend and task-owned
previews are stopped; ports 8000, 5173, 5174 and 5175 are closed. Unrelated
processes were left alone. Do not automatically restart the timer tonight.

Saved UX implementation: branch `codex/workstation-ux-001`, commit
`8239a633a0aa62d34dd293b6fc66d3bf4df1695e`, pushed. This checkpoint is a
documentation-only descendant; use `git rev-parse HEAD` for its exact commit
and the private `end-of-session.json` receipt for the final pushed identity.
Draft [PR #19](https://github.com/mmoore114/market-dashboard/pull/19) is based on
`codex/universe-expansion-v1` at `57c8aaaf1875d63a0e65b802229b33c8a215f7aa`.
Draft [PR #18](https://github.com/mmoore114/market-dashboard/pull/18) has that
head and is based on `main` at `3a1499e2d22a7321c55dc4e03b4dba382d590aad`.
Both remain unmerged. Actual production is still pinned to
`7de9858f055e7e79d26c6ac8a42896956497b43c`; UX is **not deployed**.

Private locations below are relative to the operator's `$HOME`:

- UX checkout: `aperture-workstation-ux-code`; pinned runtime:
  `aperture-universe-release-7de9858`.
- Active snapshot envelope: `aperture-universe-expansion-2026-09-08/refresh/current.json`;
  payload is the adjacent content-addressed gzip named by that envelope.
  Retained build envelope:
  `aperture-universe-expansion-2026-09-08/refresh/runs/bounded-20260908T052316Z/snapshot.json`.
- Snapshot fingerprint:
  `4d8ca015e9deadc1ca7f26b53596134072720ae9714c2be89e778df8ca6798c6`.
  Original expiry **2026-09-08 13:30 UTC / 08:30 CDT** remains unchanged;
  it must not be treated as current tomorrow or have its deadline extended.
- Replay shards: `aperture-universe-expansion-2026-09-08/refresh/replay-checkpoints`.
  Recovery receipt: `aperture-universe-expansion-2026-09-08/recovery-final.json`.
  Existing activation/membership-policy backups remain under `refresh`.
- Screenshots: `aperture-workstation-ux-2026-09-08/before-complete` and
  `aperture-workstation-ux-2026-09-08/after-accepted` (laptop and mobile).
  Existing completion/integrity receipts and the shutdown receipt remain in
  `aperture-workstation-ux-2026-09-08`; no private artifacts are committed.

Essential artifact presence and existing receipts were checked; no replay,
rebuild, acquisition, deployment, test suite or full artifact rehash was run.
The owner's existing `.vscode/settings.json` modification remains byte-for-byte
unchanged and uncommitted in the main checkout. Reported free disk at shutdown:
**1,539,067,904 bytes (about 1.43 GiB)**. Check storage before further large work.

VIX/regime confirmation and earnings coverage remain missing. Decision V1's
retained global EP-error veto is disclosed by UX review, not silently removed;
inspect its intended family/direction scope before proposing a versioned change.

Tomorrow: review PRs #18/#19 and UX screenshots, inspect the veto's intended
scope, and check refresh status before deciding on integration. Neither merge
nor deployment is authorized by this checkpoint. After reviewing status and
storage, resume scheduling deliberately with:

```bash
systemctl --user start aperture-refresh.timer
```

Stopping an enabled timer is temporary; user-manager restart/login may activate
it again. Check actual timer state on resume. No enablement/configuration change
was made to suppress that normal behavior.

## Daily research UX — implemented on a stacked draft

AP-WORKSTATION-UX-001 is implemented on `codex/workstation-ux-001`, based on
PR #18 head `57c8aaaf1875d63a0e65b802229b33c8a215f7aa`. The compact research
workflow uses bounded V2 projections and preserves the shared evidence graph.
The separate `decision-review-v1` explanation contract attributes errors without
rewriting stored decisions or changing thresholds. Future preparation extends the
verified calendar for the earnings horizon; no data acquisition or replay occurred.

The final live workflow was checked against the unchanged expanded fingerprint
while it was fresh. Production remains pinned to `7de9858`; the existing timer and
walkthrough services were preserved. PR #18 and the UX draft remain unmerged; no
runtime switch is authorized by this task. See the [UX receipt](workstation-ux-001-receipt.md)
for sampled blockers, compatibility limits, focused checks and measured performance.

## Expanded coverage milestone

`AP-UNIVERSE-EXPANSION-001` follows the normal merge of reviewed PR #17 at
`3a1499e2d22a7321c55dc4e03b4dba382d590aad`. The verified candidate union has 11,374
identities. Current source reconciliation identifies 3,045 research-eligible and
812 strict-trade candidates. Of the research names, 2,743 have ready history;
130 short listed histories and 172 histories with missing sessions remain visible
in coverage. Ten exact identities remain unresolved; six additional current
identities resolve to unsupported exchanges. No alias or canonical parent is invented.

The published population contains 3,077 covered instruments and required benchmarks.
Its current calculation population is 2,743 research, 776 trade and 333 mapping
members. Full hierarchy capture rows cover all research/trade members; themes cover
1,101 research and 442 trade names. All four parent conflicts remain. These are
current-cohort calculations, not historical membership or backtested rotation.

The recovered full-population snapshot passed complete validation and real desktop/
mobile browser checks. The supervised build/readback peaked at 1.47 GiB RSS; the
independent API endpoint probe peaked at 1.09 GiB. The enabled timer is pinned to
the verified detached recovery release `7de9858`; draft PR #18 remains unmerged.
VIX remains explicitly UNKNOWN, and the September 8 action deadline is unchanged.

See [the coverage contract](universe-expansion-v1.md) and
[completion receipt](universe-expansion-v1-receipt.md) for actual deployment,
snapshot clocks/fingerprint, measured scale, tests and remaining limitations.
The earlier prototype facts below remain historical evidence.

## Original prototype outcome

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

- The current snapshot contains 312 current-cohort Groups; historical membership
  and historical group rotation remain unavailable before their actual effective dates.
- Deepvue sub-industry and theme captures are verified bootstrap sources but remain
  local and are not runtime dependencies.
- Earnings/catalyst coverage is incomplete.
- Published coverage is explicit; eligible names with missing or short histories remain outside newly admitted ready coverage. It is not a claim of complete U.S. equity coverage.
- Book, Journal and benchmark learning remain future work.
- The current UI needs user-driven workflow and visual refinement.
- Aperture intentionally does not include charts; Deepvue handles chart review.

## Engine alignment status

`AP-ENGINE-ALIGNMENT-001` is implemented and verified on the V2 branch. Runtime V1
remains reproducible through explicit selection. New selections default to V2, an
explicit coherent `structure-engine-v2` / `setup-engine-v2` pair; no production
source data or existing snapshot was relabeled.

- Structure V2 uses the verified final Word SMA20/SMA50 model, median-ATR slopes,
  ten-session persistence, confirmation/retention hysteresis, and transitional-only
  D50 shock overrides. EMA10/SMA200 are context only.
- Setup V2 uses Word closing-dispersion contraction, robust 20-session range,
  mature-trend-only pullbacks, and 40/60-session pre-trigger limits.
- Prior-session geometry, stable version-scoped birth identities, failure-first
  ordering, terminal non-reactivation, corporate-action quarantine, and corrected
  replay are retained.
- Materialization, normalized evidence, decision/regime context, symbol detail,
  and Rules explicitly carry the selected engine identities.

A separate `ENGINE_VERSION_COMPARISON` snapshot was built from the verified retained
inputs. It has 75 valid current Structure records and funnel 63 NONE / 12 WATCH /
0 TRADE / 0 ACT, versus the preserved V1 funnel 66 / 9 / 0 / 0. Structure changes:
28 of 75; active setup sets change for 63 symbols. The eight-symbol, 126-session
sample has 362 differing states out of 1,008 observations and 69 V2 transitions
versus 56 V1 transitions. This is not a claim of reduced churn or predictive lift.

Comparison snapshot bytes: 2,146,854. Logical fingerprint:
`e7e2b78be213dbf51919012bbc4ddbf34ee4e58ce495be8d50c45246aa386a73`.
The original evidence/evaluation/action clocks are unchanged. The comparison
retains expiry at 2026-09-08 00:00 UTC and must be refused as stale afterward.

Verification: 2,910 Python tests passed, four optional real-artifact tests skipped;
13 frontend component tests and two desktop/mobile comparison browser tests
passed. TypeScript, production build, scoped lint/format, schema/type sync and
whitespace checks passed. Both services stopped, and all 1,383 protected baseline
files—including settings, source data, original snapshots and backups—remained
byte-identical. No provider requests or production publications occurred.

See [the implementation contract](engine-alignment-v2.md) for material source
ambiguities and selected interpretations, and
[the completion receipt](engine-alignment-v2-receipt.md) for final evidence and
limitations. Book, Journal, routine refresh, full-universe coverage, group
membership, earnings completeness and broader calibration remain outside scope.

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

## V2 defaults and Groups activation

Reviewed PRs #15 and #16 were merged with merge commits and branches retained.
`AP-V2-GROUPS-ACTIVATION-001` makes new version selections use the reviewed V2 pair.
Original V1 and comparison snapshots still decode with unchanged fingerprints.

A separate local database and Parquet publication now contains September 7
hierarchy and September 5 themes, plus typed membership schedules effective
September 8 only. The production source database was not changed. Research
coverage is 75/75 for all four hierarchy fields and 58/75 for themes (114
memberships); trade coverage is 49/49 for hierarchy and 40/49 for themes (84
memberships). Unassigned themes remain unknown. Four conflicting child labels
remain separate per-symbol paths, with no stocks removed to repair a hierarchy.

Groups supports all five levels, path identities, dated provenance, complete
member lists, and existing leadership/RS evidence and eligibility reasons. No new
ranking formula was introduced. Available catalogs have 11 sectors, 25 groups,
75 industry paths, 170 sub-industry paths and 31 themes. Source labels remain
73 industries and 164 sub-industries; path counts differ because parents conflict.

The original snapshots still have empty Groups and unchanged fingerprints. The
owner-authorized continuation corrected current-state timing using
`CurrentGroupProvenanceV2`: completed September 4 prices can be analyzed using
September 7 hierarchy / September 5 themes known at evaluation and valid for the
September 8 action. Historical selection and rotation changes remain strict.

At the preceding milestone, a separate real snapshot was activated, fingerprint
`59a5dca7832288b8b3534fdddb47b97608805409d1c8a31adaad08d111660b83`.
Evaluation: September 8, 00:31:12.937673 UTC; action September 8; validity through
its 13:30 UTC open. Size 7,352,531 bytes; 312 Groups, 75 research / 49 trade,
funnel 63 NONE / 12 WATCH / 0 TRADE / 0 ACT. Some RS evidence is available for 104
groups; one passes existing leadership-rank gates. The checked FRED source lacks
September 4 VIX, which stays null/UNKNOWN. No price freshness was fabricated.

One launch/refresh/status command, exclusive locking, bounded cached provider
acquisition, private recoverable publication, immutable candidates, verified atomic
activation and reload are implemented. The installed user-systemd timer dispatches
every 15 minutes and at startup, using pinned exchange close plus a 45-minute buffer.
It catches up when Linux resumes; it cannot run while Linux is stopped/suspended.

Verification: 25 focused tests; 359 integration tests with four optional artifact
skips; 13 frontend components; two real desktop/mobile Workstation smoke tests.
Type/build/lint/schema checks passed. Repeated refresh returned ALREADY_CURRENT;
a controlled failed refresh preserved the usable real snapshot. Temporary browser
services stopped; the refresh timer remains enabled as requested.

## Next work

The prior Workstation milestone was delivered in PR #17, merged at
`3a1499e2d22a7321c55dc4e03b4dba382d590aad` before universe expansion.
Beyond the September 8 action, the separately published operator reuse policy
authorizes current-cohort membership within original-source age limits; the
retained publication itself is not extended. See [the detailed receipt](current-refresh-v2.md)
and `docs/CODEX_NEXT_TASK.md` for source limits and local operation.

## Membership maintenance and operational status

PR #17 now includes a private, versioned carry-forward authorization: hierarchy
14 calendar days, themes 7, warning 3/2 days before exclusive expiry. New typed
current-cohort evidence binds the policy and original schedules while retaining
the original source/effective/known/valid-through fields. No historical rotation
is generated. New verified captures supersede prospectively; repeated runs and
republication do not reset source age. Independent controls still block normally.

Status independently verifies the retained snapshot and reports clocks, expiry,
usability, attempt outcome/failure, VIX and other missing inputs, capture ages,
policy expiry, held lock, next eligible attempt and separate timer dispatch. Groups
shows source age and explicit operator reuse without redesign or charts.

Verification: 45 focused tests, 253 relevant integration tests, 14 frontend tests
and two real desktop/mobile smoke tests passed. September 8 close → September 9
action was simulated using synthetic data in a disposable test workspace; it is
not a real September 8 after-close completion. See
[the current completion receipt](membership-maintenance-v1.md) for the real policy,
refresh outcome, scheduler status and exact periodic maintenance requirements.

The maintenance continuation completed a real September 8 pre-open refresh using
September 4 prices, producing fingerprint
`ebc6f1d7fad7ce255b6657f66330fe1ada619852e8eba27ef7a89ab0e0939161`.
Its evaluation is 01:43:41.143924 UTC and expiry remains its own September 8
13:30 UTC action open. All 312 groups bind the separate reuse policy. The immediate
repeat was ALREADY_CURRENT, VIX remained UNKNOWN, and the enabled timer was
resumed. This does not claim real September 8 after-close completion.
