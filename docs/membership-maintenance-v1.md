# Current membership maintenance and operational status

Owner-authorized continuation of draft PR #17 from `3f00d497`. This policy permits
current-cohort reuse between verified Deepvue captures without daily approval.
It does not automate authenticated Deepvue access or add a provider.

## Policy and source clocks

`membership-reuse-policy-v1` is a separate private operator authorization. New
`CurrentGroupProvenanceV3` / `current-group-analysis-v3` evidence binds the policy
hash, original schedule hash, authorization time and age limits. It retains the
original source/effective/known/valid-through fields verbatim, even when the
current action falls after the original schedule's one-session validity.

| Source | Maximum age | Warn before expiry | Current source | Exclusive expiry |
| --- | --- | --- | --- | --- |
| Hierarchy | 14 calendar days | 3 days | 2026-09-07 | 2026-09-21 00:00 UTC |
| Themes | 7 calendar days | 2 days | 2026-09-05 | 2026-09-12 00:00 UTC |

Hierarchy receives a two-week maintenance interval; the more changeable theme
labels receive one week. Warnings allow time for manual capture and verification.
These are conservative operational defaults, selected without returns analysis,
parameter search or any claim about predictive performance. They are configurable
through explicit policy publication, not through a timer's automatic renewal.

Age is measured in UTC calendar days from the actual capture date. Date-only
captures conservatively start aging at the beginning of that date. Expiry is
exclusive at capture date plus maximum age, 00:00 UTC. The warning begins exactly
`warn_before_days` before expiry. Both actual evaluation and the target action
open must precede expiry. This source-age limit is independent of the exchange
calendar's completed price session and does not invent a new market observation.

Restarting, rebuilding, repeated publication or a new authorization timestamp
never resets capture age. An unchanged publication is a no-op. Changed limits
require explicit operator publication and retain the previous authorization.
New verified captures are registered with actual time and supersede older ones
prospectively, independently for hierarchy and themes. An unchanged theme capture
can remain pinned to its original receipt when a newer hierarchy is registered.
Conflicting contents for the same role/capture date are refused for review.

Historical selection still uses the original schedules and refuses expired or
current-cohort membership. Reuse cannot generate historical ranks, rank changes,
rotation changes or top-quintile history. Unknown assignments, all four parent
conflicts and complete per-symbol paths are unchanged. Security identity,
tradability, population, earnings, adjusted-history corrections and all other
controls retain their own existing rules. There are no Structure/Setup changes.

## Explicit local publication

The private refresh configuration still selects the source workspace. Publish or
reapply the defaults once with:

```bash
.venv/bin/python -m market_dashboard.workstation.refresh.membership \
  --config "$HOME/.config/aperture/refresh.json"
```

After importing and verifying a new capture through the existing publication
contract, register its publication workspace with `--source-workspace PATH`.
The command verifies receipt and schedule hashes before registering it. It never
logs in to Deepvue, requests provider data, or edits the original publication.

To explicitly change a limit, supply both flags for that role, for example
`--hierarchy-max-age-days 14 --hierarchy-warn-before-days 3` or
`--themes-max-age-days 7 --themes-warn-before-days 2`. Omitting a role preserves
its previously published limit. Limits must be 2–366 days with a positive warning
strictly shorter than the maximum; changing them is an operator decision.

The policy pointer defaults to `membership-policy.json` in the private refresh
workspace; `membership_policy` in configuration may select an explicit path.
Publication uses the refresh lock, verified content-hash archives of both previous
and new authorization, fsync and atomic replacement. New snapshot manifests bind
the immutable policy archive, so later capture registration does not invalidate
old evidence paths. The original capture files, September-8-only schedules and
publication receipts remain immutable.

## Refresh and status behavior

Refresh preflights the selected captures and their action-time age limits before
provider acquisition. Within the policy interval, the original one-session
schedule alone no longer blocks September 9 or another eligible action. At expiry
it reports the source role, capture date, exclusive expiry and target action in a
`SOURCE_REFRESH_REQUIRED` reason. No timer or rebuild silently renews the policy.
New captures or explicit policy changes invalidate the refresh input identity.

```bash
.venv/bin/python scripts/aperture.py launch
.venv/bin/python scripts/aperture.py refresh
.venv/bin/python scripts/aperture.py status
```

`status` is read-only and performs no provider requests. It reports:

- independently verified active snapshot path, fingerprint, market/evaluation/
  action clocks, generation time, expiry, age and present usability;
- last attempt start/finish, outcome, failure reason, missing inputs and the
  snapshot's actual VIX availability;
- each capture's original date, current age, reuse/warning/expiry state, maximum
  age, policy hash and exact source-refresh requirement;
- the next eligible acquisition/build attempt separately from the user-systemd
  timer's next dispatch, plus scheduler availability/enabled/active state;
- whether the existing refresh lock is held, and an interrupted attempt if a
  recorded RUNNING state has no live lock.

Missing/malformed status metadata is reported without hiding a valid retained
snapshot. Unknown legacy attempt timestamps remain null rather than invented.
When metadata lacks a next attempt, status labels its calendar-derived fallback;
a currently eligible pre-open catch-up is reported as eligible now. Reading status
does not create a lock, rewrite metadata or refresh evidence. Scheduler access is
bounded and reports unavailable when the user bus cannot be inspected.

Groups shows the operational capture age, reuse state, warning/expiry and explicit
operator-reuse wording separately from frozen snapshot clocks. A newer capture
that differs from the displayed snapshot is labeled as requiring a rebuild. It
is never silently substituted into previously computed group evidence.

The existing enabled user timer dispatches every 15 minutes and at startup,
using actual pinned XNYS close plus 45 minutes, including early closes. Linux must
be running. ChromeOS sleep/Linux shutdown cannot guarantee unattended execution;
persistent catch-up resumes when Linux is available. No always-on host was added.

## Completion receipt

The real policy was published at `2026-09-08T01:41:22.934302Z`, SHA-256
`1055b5bec7d0a69c3a8d4564a574fdf443b5ee89a4c4340d7b5fb4eb78ae0f5a`,
with a verified identical archive. Hierarchy age was 1 day and themes 3 days;
both were reusable. Original capture, publication and snapshot hashes were retained.

Verification: 45 focused tests and 253 relevant snapshot/API/adapter tests passed;
14 frontend tests and two real desktop/mobile browser tests passed. The future
simulation uses synthetic stock history, inputs and clocks in a disposable test
workspace: September 8 close, actual XNYS next action September 9, two synthetic
group catalogs with separately dated captures, complete replay/serialization and
activation. It proves the next-session contract, not availability of real September
8 bars or completion of the September 8 after-close run. Independent control
failures still refuse publication and preserve the prior usable snapshot.

Real concurrent status was observed with RUNNING, the lock held, and the prior
snapshot still available. The existing real snapshot remained September 4 price
evidence / September 8 action during browser verification. The completed real refresh and scheduler observation follow.

The first upcoming membership maintenance is the September 10 theme warning.
Before an evaluation targeting September 14, themes need a newer verified capture
whose seven-day limit covers that action open (September 8 or later capture date).
Hierarchy has its independent September 18 warning and September 21 expiry.
Those are periodic source maintenance requirements, not daily approvals. Provider
publication delays and incomplete earnings remain independent evidence limitations.

### Real refresh outcome and final status

One actual pre-open refresh completed September 8 at 01:53:38.279803 UTC. It
re-evaluated the latest completed September 4 price session for September 8 action;
it was **not** the September 8 after-close run targeting September 9.

- New private artifact: `runs/20260908T014316047894Z/snapshot.json` in the refresh
  workspace, atomically activated as `current.json`.
- Fingerprint: `ebc6f1d7fad7ce255b6657f66330fe1ada619852e8eba27ef7a89ab0e0939161`.
- Evaluation: 01:43:41.143924 UTC; generation: 01:49:00.271471 UTC; its own expiry
  is September 8 13:30 UTC. All 312 groups use CurrentGroupProvenanceV3.
- 75 research records, unchanged funnel 63 NONE / 12 WATCH / 0 TRADE / 0 ACT.
- One actual FRED check again supplied VIX only through September 3. September 4
  volatility remains null/UNKNOWN. No new Massive bars or references were needed
  for this same completed-session/action context.
- The immediate real repeat returned ALREADY_CURRENT, with the identical snapshot
  fingerprint and no provider acquisition or rebuild. Last attempt finished
  01:55:25.762891 UTC without a failure; status reported no refresh running.
- The timer was temporarily paused during implementation and resumed after
  verification. It is enabled/active, with its next dispatch observed at 02:00 UTC.
  Next eligible support attempt: 02:43:41.143924 UTC, eligible at the 02:45 tick.
  September 8 after-close eligibility remains 20:45 UTC, targeting September 9
  subject to actual bar availability and independent controls.
- Desktop/mobile smoke passed again against this newly activated snapshot, with
  source-age/reuse status visible. Both API/frontend services stopped afterward.

All 1,383 protected baseline files remained byte-identical. Of the 43 additional
private files inventoried at task start, only the authorized active snapshot
pointer, activation intent and refresh status changed. The prior active bytes have
a verified content-hash backup; original snapshots, source captures, receipts and
September-8-only schedules remain intact. New policy archives, input generations
and snapshots remain outside Git. Settings remain unchanged and uncommitted.

Typecheck, production build, frontend lint/format, scoped Ruff, OpenAPI/snapshot
schema/type synchronization and whitespace checks passed. No full suite was run.
There is no remaining implementation blocker to trying September 9 action within
the reuse interval; real September 8 after-close input availability cannot be
verified before that session completes.
