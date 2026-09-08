# Codex Next Task

Status: SESSION CLOSED — review before integration; no automatic work tonight.

Read the [end-of-session checkpoint](PROJECT_STATE.md#session-closed--2026-09-08-0739-utc)
first. UX implementation `8239a633a0aa62d34dd293b6fc66d3bf4df1695e` is pushed
on `codex/workstation-ux-001`; the shutdown checkpoint is documentation only.
Draft PR #19 is stacked on PR #18's `57c8aaaf1875d63a0e65b802229b33c8a215f7aa`;
both remain unmerged. Production is pinned to
`7de9858f055e7e79d26c6ac8a42896956497b43c`, not the UX implementation.

Tomorrow's task: review PRs #18/#19 and before/after UX screenshots, inspect the
retained global EP-error veto's intended scope, and check refresh status and
available disk before deciding on integration. Preserve missing VIX/earnings as
missing; do not extend the snapshot's original September 8 13:30 UTC deadline.

The timer was enabled/active and is now temporarily stopped, still enabled with
unchanged configuration. API/frontend and task-owned previews are stopped; no
refresh/build remains running. Do not restart scheduling automatically tonight.
When deliberately resuming after inspection: `systemctl --user start aperture-refresh.timer`.
Check actual state after a new login because enablement was preserved.

No new implementation, test suite, acquisition, replay, snapshot rebuild, merge
or deployment is authorized by this shutdown checkpoint. Preserve settings,
private datasets, snapshots, backups, replay shards and screenshots. The project
state records their locations and the existing receipts; do not repeat the full
1,383-file audit. See also the [UX completion receipt](workstation-ux-001-receipt.md).
