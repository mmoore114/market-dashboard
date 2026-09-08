# Stack pre-integration review — AP-PREINTEGRATION-001

Review baseline: PR #20 `6b7a0716a19e78a1c8735c7e1c5b47d7011065c4`.
The active task authorizes focused fixes, pushes and draft updates, not merging,
deployment, acquisition, production refresh or scheduler restart.

## Findings and corrections

**Confirmed edge-case defect:** INDUSTRY V2 previously constructed RegimeInputV1,
whose global subindustry-overlap validator could block valid industry evidence.
Repeated child labels under different parents for different symbols were already
allowed. A single security in two subindustry paths was rejected before V2 voting.

`market-regime-input-v2` now inherits all shared alignment checks and changes only
the authoritative membership-overlap rule to INDUSTRY. Secondary ambiguity remains
in complete group/member evidence and detail membership context. Duplicate group
identities, misdated groups, source/calendar/universe/version disagreement and
invalid symbol evidence still fail validation. Conflicting industry assignments
remain invalid. Unresolved identities use their distinct source identities; null
market-symbol values are never collapsed into one fictitious security.

The public and prepared bar adapters accept an explicit input contract; new V2
materialization selects V2 before construction, with no intermediate V1 rejection.
V1 continues to reject overlapping subindustries and refuses V2 input. Existing
V2 outputs that carry V1 inputs remain decodable under their original registry and
fingerprint. The prior registry/type addresses are frozen and the new input type
is appended. Decision/Regime calculation fingerprints and thresholds are unchanged:
this explicitly versioned input contract broadens secondary-context admissibility,
not the industry voting formulas or confirmation rules.

The retained captured evidence has **zero overlapping security identities** in
INDUSTRY or SUB_INDUSTRY. Its conflicting parent labels refer to different symbols.
The original hierarchy CSV also has zero conflicting per-symbol paths across
11,368 captured symbols. Actual retained evidence constructs and evaluates through the new V2 contract;
regime remains UNKNOWN. Thus this is a supported future/input edge case, not an
observed captured-data failure. The initial diagnostic grouped null market IDs
together; the corrected identity-aware count excludes that diagnostic artifact.

**Confirmed performance defect:** setup filtering built full reviews and scanned
all shared membership for every candidate. Setup-only review/selection is now
shared by filters and full detail; a selected group builds one request-local
membership set. Full review runs only for paginated rows or requested detail.
No persistent cache, snapshot mutation, decision reevaluation or evidence loss is
introduced. Selection, direction, stable sorting, null ordering and pagination are
unchanged. The full decision engine still independently evaluates every setup.

## Historical performance evidence

One process at a time, 1,300 MiB soft / 1,500 MiB hard memory limits, no acquisition,
setup replay, snapshot rebuild or activation. Both reads validated the original
`4d8ca015e9deadc1ca7f26b53596134072720ae9714c2be89e778df8ca6798c6`
fingerprint and unchanged September 8 13:30 UTC expiry. Measurements include bounded
projection and JSON serialization, exclude cold loading/network transport, and use
three calls per case on 2,743 records with default 25-row pages.

| Filter | Before median | After median | Matches | Response bytes |
| --- | ---: | ---: | ---: | ---: |
| LONG TREND_PULLBACK | 13.983 s | 0.179 s | 825 | 39,351 |
| Biotechnology INDUSTRY + LONG TREND_PULLBACK | 2.017 s | 0.120 s | 89 | 40,365 |
| SHORT TREND_PULLBACK | 0.0047 s | 0.0044 s | 0 | 347 |

All result hashes (excluding metadata) and response sizes matched exactly. Cold
read/validation: 50.70 s before, 51.16 s after. Peak RSS: 1,066,644 KiB before,
1,067,092 KiB after (about 1.02 GiB). The latter also includes actual V2 regime input
construction/evaluation. Private scripts/results remain outside Git.

A separate in-process FastAPI/TestClient check included route validation and full
metadata. Normal current-time requests first returned 503 for the expired snapshot.
Only the isolated test clock then used the snapshot's original evaluation instant;
no timestamp/expiry changed, no listener opened and nothing was published as fresh.
Delivered and optimized handlers ran sequentially over the same decoded snapshot.

| Actual endpoint filter | Before median | After median | Complete response bytes |
| --- | ---: | ---: | ---: |
| LONG TREND_PULLBACK | 13.593 s | 0.192 s | 101,597 |
| Biotechnology + LONG TREND_PULLBACK | 1.955 s | 0.129 s | 102,611 |

Each median covers three requests. Complete response SHA-256 hashes, including
metadata, matched before/after. Peak RSS including FastAPI/TestClient was
1,115,612 KiB (about 1.06 GiB). These endpoint sizes supersede the smaller projection
measurements above, whose metadata did not include the full local evaluation.

## Policy and workflow boundaries

- INDUSTRY controls coverage, membership, eligible rank denominator and regime
  group internals. GROUP, SUB_INDUSTRY and themes retain their actual labels.
- Declared group minimum five and coverage 60% match Leadership aggregation;
  declared internals minimum five matches the consumed regime threshold. A focused
  invariant test prevents these separately versioned declarations drifting.
- New materialization and independent decision validation select Decision/Regime
  V2. API detail preserves the selected policy. Sizer uses the exact stored
  symbol/direction regime and earnings gates with unchanged sizing rules; it does
  not substitute V1 decisions or re-run setup selection.
- The global EP veto is unchanged. Proposed separate work would confine
  detector-only errors to family/direction, retaining shared/unattributed failures
  globally and instance evaluation/replay failures locally. That policy change is
  neither required for integration nor included here.
- Latest labeled fixture screenshots were re-inspected locally: 11 complete Tape
  rows and 10 Groups rows at 1366×768; desktop/mobile first detail viewport shows
  current setup, primary earnings blocker and next action. UI layout is unchanged.

## Focused verification

Research/materialization regressions passed (62 tests apart from the separately
reported industry tests). Regime adapter/sleeve/transition regressions passed
(1,277 tests). The final industry/materializer/API/Sizer and normalized snapshot
run passed 42 tests. The new API test uses explicitly labeled synthetic outputs;
no private snapshot clock is changed. A fixture generated with the exact delivered
PR #20 code decoded under the new code with its original registry
`608ed447…edb150a` and fingerprint `338eed3a…634f54c` unchanged.

Existing PR #20 evidence (3,000 full-suite passes/four skips and desktop/mobile
browser checks) is reused for unchanged code. No full suite or browser run was
repeated merely to refresh that evidence. Final frontend typecheck/production
build, 11 component tests, lint/format, OpenAPI/type synchronization, snapshot
schema checks, scoped Python lint and Git whitespace checks passed.

## Integration sequence for owner approval

1. Recheck remote heads and keep the enabled timer stopped. Main at review is
   `3a1499e2d22a7321c55dc4e03b4dba382d590aad`; verified ancestry is main → #18
   `57c8aaaf1875d63a0e65b802229b33c8a215f7aa` → #19
   `000a356041fdc3ffab8f4ab9c7ac053d6ecd846c` → #20. The final tested #20 head is
   recorded in the PR delivery message. Any later code delta needs relevant checks.
2. Merge #18 with a merge commit and retain branches. Retarget #19 to main,
   verify its diff is only its reviewed changes, then merge with a merge commit.
   Retarget #20 to main, verify the remaining diff, then merge with a merge commit.
   Do not squash/rebase away the shared ancestry. Confirm final main's tree equals
   the tested #20 tree; otherwise review/test the integration delta before deployment.
3. Create an immutable release checkout at the approved final tested head (or the
   merge SHA after tree equality verification). Install/build from lockfiles and
   verify imports/schema and local startup. Change both runtime configuration pin
   and service WorkingDirectory/ExecStart together, then daemon-reload. Preserve
   prior config/units. The current pin and rollback code target are exactly
   `7de9858f055e7e79d26c6ac8a42896956497b43c`; rollback restores its original units,
   config and saved V1 envelope/payload atomically. The old snapshot remains expired,
   so rollback restores reproducibility, not fresh eligibility. Never point old
   code at a newly published input-V2 snapshot it cannot decode.
4. **Before any real refresh, expand storage.** At review only about 1.44 GiB is
   free. Require at least 4 GiB usable free space on the actual staging/checkpoint/
   spill filesystem as a conservative operating floor, then confirm projected
   acquisition, database/Parquet copies, replay shards, normalization spill, candidate
   and readback fit with reserve. This is a planning guard, not a measured upper
   bound or an existing enforced application limit. Current retained shards alone
   occupy about 439 MiB, a prior spill 165 MiB and the active compressed snapshot
   25 MiB. Retain all old artifacts; expanding/moving storage requires a verified
   copy and explicit authorization, not deletion. Keep API/build/browser workloads
   separate and preserve recovery's 1,400/1,600 MiB supervised build limits with
   sufficient host headroom; do not run a refresh in the editor scope.
5. Retain old policy snapshots and original clocks; only a new validated candidate
   gets V2 policy/input identities. Regime V1 confirmation memory cannot seed V2.
   Initialize V2 from verified completed sessions or reuse compatible prior V2
   memory only with matching source/calendar/identity and actual continuity.
   UNKNOWN/missing sessions cannot be invented as confirmations. Current-cohort
   membership must not be backdated to manufacture historical industry rotation.
6. **Checkpoint reuse is conditional, not promised.** Current shards bind full
   versions, broad engine source hashes, as-of/calendar, source, corporate actions
   and exact history bytes/schema. The existing narrow compatibility receipt only
   admits two downstream decision modules; it does not authorize this branch's
   added contracts or version changes. Therefore these 2,743 shards are retained
   but are not automatically reusable by the new defaults. For identical price-
   engine inputs, a separately reviewed migration must prove Structure/Setup
   dependency equivalence and retain a typed hash-bound lineage receipt; never edit
   shard bases or claim changed inputs unchanged. New completed bars, corrected
   history, changed source/calendar/actions or price-engine identities require new
   replay work unless a separately validated incremental mechanism applies.
   Budget storage/time for a fresh replay when compatibility cannot be proven.
7. After separate refresh authorization, inspect source identity/history readiness,
   membership reuse expiry, lock status and the completed-session/action window.
   Run one supervised locked refresh; validate the candidate and selected V2 input/
   policy identities before atomic activation. An ALREADY_CURRENT result can
   retain a usable old-policy snapshot; it is not evidence of policy migration.
   Wait for the next eligible supervised build rather than modifying old clocks
   or falsifying refresh state. Verify VIX observation and regime
   confirmation status and explicit earnings coverage. Missing VIX remains UNKNOWN;
   missing earnings never means clearance. Neither source gap is waived for ACT.
8. Only after the supervised outcome and runtime/status checks are accepted, restart
   `aperture-refresh.timer`, inspect next dispatch and last attempt, and verify the
   pin. If the build fails, preserve the prior envelope and keep the timer stopped.
   An enabled timer can restart with the user manager/login; always recheck it.

No integration, pin change, real refresh or scheduler restart was performed by
this review. Merge approval and deployment/refresh authorization are separate;
low storage blocks refresh, not review of the code stack.


Final runtime inspection: production checkout still `7de9858`; refresh timer and
service inactive, timer enabled, ports 8000/5173/5174/5175 closed. Free disk was
1,525,542,912 bytes (about 1.42 GiB), available memory about 1,820 MiB. Protected
settings, runtime configuration/units and the snapshot envelope matched their
retained hashes; all 2,743 checkpoint files remain. The task checkout retains only
the pre-existing untracked `web/node_modules` symlink outside committed changes.
