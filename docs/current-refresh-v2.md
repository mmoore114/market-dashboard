# Current-cohort Groups and daily refresh

Continuation of reviewed PR #17 at `9d83fdc8e515d0d3d8a25e12a736a78265572741`.
The owner explicitly authorized required bounded acquisition, reversible local
publication, rebuild, verified activation and local scheduling. The PR stays draft.

## Clock contract

`CurrentGroupProvenanceV2` / `current-group-analysis-v2` labels Groups
`CURRENT_COHORT_AT_E`. It retains market evidence T, membership source date,
effective/known session, actual known-at timestamp, evaluation E, action A and
valid-through. Current membership may analyze older completed-session stock data
only in this explicit context and only if known by E and valid for A.

The previous milestone's September-8-bars requirement was an overly strict
historical interpretation for this current-state use case. Historical selection
still rejects current-cohort membership. Five-/20-session group rank changes and
top-quintile history remain unavailable; no historical group ranks are rewritten.
Stock RS uses the existing current-cohort bootstrap and Leadership V1 formulas.
The reviewed Structure/Setup V2 formulas and 60/40 lifetimes are unchanged.

The pinned `exchange-calendars==4.13.2` XNYS calendar determines completed T,
next A, official open, holidays, DST and early closes. A pre-open evaluation on
A's UTC date is accepted only with its explicit future exchange open. A new
snapshot expires at A's open, independently of any previous snapshot deadline.
A UTC midnight never invents a completed market session. During the open session,
refresh reports the next after-close attempt; this workflow is not an intraday feed.

## Real snapshot receipt

Separate artifact: `verified-current-cohort/snapshot.json` in the private
`aperture-daily-refresh` workspace. `current.json` is its atomically activated copy.
Logical fingerprint:
`59a5dca7832288b8b3534fdddb47b97608805409d1c8a31adaad08d111660b83`.

- Bytes: 7,352,531; replay 602.29 seconds; peak RSS 493,876 KiB.
- Price evidence T: September 4, 2026 close.
- Evaluation E: September 8, 2026, 00:31:12.937673 UTC (September 7 New York).
- Generation timestamp: September 8, 00:36:43.214671 UTC.
- Action A: September 8; new context valid until its open, 13:30 UTC.
- Hierarchy source: September 7; themes source: September 5.
- Membership known-at: September 7, 23:53:11.514821 UTC; effective/known session
  September 8 and valid-through September 8, preserved from the publication.
- 75 research members, 49 trade members; 63 NONE / 12 WATCH / 0 TRADE / 0 ACT.
- All 75 research and 49 trade symbols have all four hierarchy fields.
  Themes cover 58/75 research symbols (114 memberships), 40/49 trade (84).
- 312 Groups: 11 sectors, 25 groups, 75 industry paths, 170 sub-industry paths,
  31 themes. All four source conflicts remain in full per-symbol parent paths.
- 104 groups have some valid RS evidence; only one meets existing leadership-rank
  eligibility. Unsupported metrics remain null with existing coverage/member gates.

The single required FRED VIXCLS availability request returned data only through
September 3. No September 4 observation was fabricated or carried forward into its
place. Volatility close at T is null, and the existing Regime/Decision contracts
retain UNKNOWN/veto evidence. Missing VIX does not turn known completed stock
prices into nonexistent observations; FRESH describes bounded decision-context
availability, not complete evidence. Earnings remains incomplete. No Massive bar
request was needed because all required completed-session bars were already local.

## One supported command

`.venv/bin/python scripts/aperture.py refresh` uses private configuration from
`${XDG_CONFIG_HOME:-$HOME/.config}/aperture/refresh.json`; `--config` selects an
explicit alternative. `launch` performs the same catch-up and starts the API/UI;
`status` reports fingerprint, completed market session, age and usability.

Configuration contains repository/workspace paths, exact seed bootstrap/snapshot,
verified Groups publication workspace, local credentials-file path and Node path.
It never embeds credential values. An optional prepared candidate is accepted only
after typed integrity, source-hash, T/A, V2, real/populated and freshness validation.
The seed artifacts are immutable anchors, not freshness overrides.

The refresh pipeline reuses `current_sources.fetch_staged` / `validate_staged`,
`publish_bars`, `EquityFeaturePipeline`, `build_action_population`, bootstrap and
normal V2 materialization. It never expands the fixed covered population. Required
bars/benchmarks are requested only for missing completed sessions, with an overlap
bar to detect revised adjusted history. An overlap change refuses automatic mixing
and reports corrected-history replay required. Current reference controls are
requested for a new action context; changed instrument types refuse stale exposure
classification. Prior trade membership is passed to existing universe safeguards.

Successful provider jobs are reused; each exact job has at most two attempts per
invocation and three total per UTC day. Delayed VIX responses can be checked again
after 15 minutes within that budget. Bars/control failures preserve the previous
snapshot. VIX publication delays remain explicit optional Regime evidence; no
fallback source or invented publication time is used. A successful acquisition
cache is evidence availability, not permission to extend membership validity.

New input generations and derived data are private. Bar publication operates on a
separate database copy with verified backups and the existing recoverable publisher;
original production data is unchanged. Candidate/output hashes and readback are
verified. An exclusive OS lock prevents overlap. Activation uses fsync plus atomic
replace and retains a verified copy of the previous active artifact. The API detects
an activated file change and reloads the typed snapshot. A failed refresh leaves
last success intact and reports its age, usability, missing inputs and next attempt.

## Local schedule and host limits

Installed user units: `aperture-refresh.service` and `aperture-refresh.timer`.
The timer has `OnCalendar=*:0/15`, `OnStartupSec=2min`, `Persistent=true` and 30-second
accuracy. Its dispatcher uses actual XNYS close plus 45 minutes; this buffer is an
operational starting point, not a promise of provider publication completeness.
Provider delay checks occur at bounded intervals; premarket launch uses the same
locked command. Early-close days use their actual close, not a fixed 16:00 clock.
The service has a 30-minute timeout; partial run artifacts remain recoverable.

Installation and startup catch-up were observed successful. At verification the
next timer dispatch was September 8 at 01:00 UTC; the recorded supporting-input
attempt is 01:42:41 UTC, eligible at the 01:45 dispatcher tick. The next scheduled
after-close target is September 8 at 20:45 UTC, subject to membership/control validity.
Use `status`, `systemctl --user list-timers aperture-refresh.timer`, and the private
`refresh-status.json` for current values rather than treating this receipt as a
permanent schedule.

User systemd is running on this machine. The service cannot execute when ChromeOS
suspends/stops the Linux environment, and the timer cannot guarantee waking the
Chromebook. Persistent startup/resume catch-up processes the actual latest completed
session once Linux is available. Reliable unattended execution requires an always-on
host; no hosting purchase or deployment was made.

## Verification and remaining requirements

- 25 focused current-group/calendar/lock/retry/bootstrap tests passed.
- 359 relevant snapshot/API/Decision/Regime/Leadership/foundation/V2 tests passed;
  four optional real-master-artifact tests skipped. No full suite was repeated.
- 13 frontend component tests; typecheck, build, lint and schema/type sync passed.
- Two real desktop/mobile browser tests passed for Brief, Tape, Groups, Sizer,
  Rules and symbol-detail API. Populated Groups displayed current-cohort clocks,
  member lists and unavailable historical rotation. Both temporary services stopped.
- Actual activation succeeded; repeated refresh returned ALREADY_CURRENT with the
  same fingerprint. A controlled failed refresh preserved a usable real snapshot
  byte-for-byte. Local input preparation verified 66,951 bars and 75 research members.
- The first real build found an additional historical-only Regime validator; it was
  corrected and tested with a small complete replay before the successful real build.
  Parquet verification normalizes timestamp precision and equivalent null representations
  for comparison only, without imputing or changing data.

The Workstation is usable now within its stated deadline. September 4 VIX remains
unpublished in the checked source; corresponding volatility evidence stays UNKNOWN.
For action sessions after September 8, the current Groups publication's explicit
valid-through interval needs a refreshed capture or reviewed validity attestation.
The command deliberately reports that requirement before paid acquisition, rather
than silently rolling membership validity forward. Changed adjusted history or
instrument classification similarly requires its existing corrected-publication
boundary. These are explicit source/control limits, not missing launch commands.

Settings, raw captures, original source data, old snapshots, engine comparison
artifacts and retained backups remain unchanged. New snapshots, logs, receipts,
configuration and scheduler paths remain private and outside Git.
