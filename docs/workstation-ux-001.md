# AP-WORKSTATION-UX-001

Status: implemented; see [completion receipt](workstation-ux-001-receipt.md). Stacked on PR #18 at `57c8aaa`; production remains pinned to `7de9858`.

Complete AP-WORKSTATION-UX-001: make Aperture useful for daily research and correct misleading decision explanations.

The owner has completed a visual walkthrough. The current interface exposes too much raw diagnostic evidence, Groups is an unranked wall of hierarchy paths, Tape rows expand around historical setups, and symbol detail buries the trading conclusion beneath repeated failures.

This authorizes implementation, focused verification, commit/push and a draft PR. Do not merely return a plan.

1. Establish a safe baseline.

Read AGENTS.md, README, current authority, project state, and the universe-expansion/recovery documentation.

Known PR #18 head:
57c8aaaf1875d63a0e65b802229b33c8a215f7aa
Verified runtime:
7de9858f055e7e79d26c6ac8a42896956497b43c

Fetch and inspect actual state. Create an isolated feature branch/worktree based on the recovered implementation. Leave PR #18 unmerged; use it as the base for a clearly documented stacked draft PR if necessary.

Do not disturb the pinned daily-refresh runtime, timer, settings modification, checkpoints, captures, backups or active snapshot. Preserve the memory fixes and reference-based V2 API.

Record this assignment in the repository.

2. Diagnose decision explanations before changing their presentation.

Locate the retained snapshot with fingerprint:
4d8ca015e9deadc1ca7f26b53596134072720ae9714c2be89e778df8ca6798c6

Trace Agilent (A) and a small deterministic sample of WATCH names. The walkthrough showed:
- REGIME_UNKNOWN alongside REGIME_ACTION_SESSION_MISMATCH.
- EARNINGS_COVERAGE_MISSING alongside EARNINGS_CALENDAR_TOO_SHORT.
- A LONG TREND_PULLBACK marked TRIGGERED, evaluated=true, replay_required=false, but rejected with SETUP_ENGINE_ERRORS.
- Blank account/entry/stop inputs producing many repeated sizing failures.
- Successful established-strength qualification displayed alongside failures from the alternative rotation branch.

For each, trace the exact evidence and code path. Distinguish:
- Genuine strategy disqualification.
- Missing or unavailable source evidence.
- Invalid or misaligned data.
- User proposal not yet entered.
- An unmet alternative that does not block a passing OR condition.
- Historical/terminal setup evidence that does not describe the current setup.

Fix demonstrated implementation or explanation defects with focused regressions. Do not suppress legitimate engine errors, fabricate earnings/VIX, relax gates, change thresholds, or force TRADE/ACT counts upward.

Check whether the exchange calendar covers the required future earnings horizon. Extending verified calendar coverage is different from inventing future market observations.

Produce a concise blocker breakdown for the sampled names and, where inexpensive, aggregate counts from existing decision outputs. Clearly distinguish overlapping reasons from unique stock counts.

3. Implement one consistent, compact interface.

Keep the dark Aperture theme, restrained accent colors, readable typography and sidebar. No charts. Deepvue remains the chart companion.

Global shell:
- Replace the large technical banner with concise market-data date, evaluation/action context, and data-health status.
- Keep freshness separate from evidence completeness.
- Put fingerprints, bootstrap counters, raw codes and publication details behind “Data details.”
- Remove Book, Journal and unavailable Time Machine from primary working navigation; retain an appropriate secondary/planned location.
- No “Try again” for a capability that lacks historical data.

Brief:
- Explain market context and unavailable inputs in plain language.
- UNKNOWN must use neutral styling, not a green success symbol.
- Make funnel counts open the corresponding filtered Tape.
- Replace the oversized empty ACT panel with a compact explanation and access to WATCH candidates.
- Display leading groups with short names and existing supported metrics.
- Label rotation/delta precisely; do not present a cross-sectional difference as historical movement.

Groups — replace the current expandable catalog:
- Separate Sectors, Groups, Industries, Sub-industries and Themes. Default to Sub-industries.
- Show a compact sortable table: short name, existing leadership rank/RS, supported rotation metric, covered members/total members, and candidate counts where supported.
- Default to eligible groups ordered by the existing leadership rank; provide access to unranked/insufficient-coverage groups with clear reasons.
- Compare ranks only within their appropriate level and eligible population.
- Selecting a group opens a bounded member table with ticker, RS, Structure, active Setup and decision state, with access to stock detail.
- Preserve distinct parent-path identities and many-to-many themes. Use secondary parent context where needed to distinguish duplicate names.
- Show source age/reuse status concisely; expand provenance on demand.
- Do not invent group metrics or ranking formulas.

Tape:
- Use consistent compact rows, sticky headers and existing pagination.
- Show short sub-industry labels.
- Show relevant active setups for the row’s direction; put terminal/history and opposite-direction details behind expansion.
- Summarize the primary actionable blocker rather than listing every reason.
- Make symbols and group names useful navigation targets.
- Keep filters, sort and scroll position when opening/closing stock detail.
- Distinguish trade-universe eligibility from the TRADE action state.

Stock detail:
- First viewport: ticker/company, price date, decision state, Structure, strength, active setup summary and primary blockers.
- Put “Copy symbol / Deepvue” and “Size this idea” near the top.
- Preserve the existing Sizer handoff and verify symbol/direction transfer.
- Use concise sections or tabs for Overview, Setups, Decision evidence and Data details.
- Separate active setups from terminal history.
- Show useful trigger/invalidation geometry when actually available, clearly distinguishing lifecycle invalidation from a proposed trade stop.
- Deduplicate repeated reasons while keeping complete evidence accessible.
- Avoid nested scrolling traps and large empty metric cells.

Sizer:
- Add symbol search using the existing bounded data/API.
- Display the applied risk percentage and dollar budget clearly.
- Label account equity and buying power distinctly.
- Preserve entry/stop as explicit user proposals.
- Before a proposal exists, show “Enter trade details”; do not display a wall of INVALID failures.
- Distinguish theoretical sizing from policy-qualified sizing without changing eligibility rules.
- Do not manufacture a valid size when required controls are unavailable.

Rules:
- Present readable definitions, labeled thresholds and units.
- Format $1 billion, $50 million and percentages normally.
- Replace raw Python enum dictionaries, unnamed tuples and internal parameter labels with accurate explanations.
- Preserve exact formulas, versions and fingerprints in expandable technical sections.
- Keep values derived from canonical rules; do not create a second frontend rules engine.

4. Preserve performance and truthful snapshot handling.

Use V2 detail references and bounded API projections. Do not fetch or reconstruct the entire evidence graph in the browser, or return to expanding shared Leadership/Regime models.

Prefer existing projections; add bounded endpoints only where the workflow needs them. Display-only work must not trigger full engine replay.

If the retained snapshot has expired, inspect it offline and use clearly labeled representative fixtures for interactive development. Do not bypass production freshness checks or change its timestamps.

Use a genuinely current verified snapshot for final live checks if available. Report any limitation honestly. Do not disturb the scheduled after-close refresh to obtain screenshots.

5. Verify the actual user workflow.

Add focused tests for demonstrated explanation defects and new interactions. Run relevant frontend/type/build/schema checks; do not repeat the full Python suite.

Capture before-and-after browser screenshots and inspect them yourself at desktop/laptop and mobile sizes. Browser tests must exercise:
- Brief funnel → filtered Tape.
- Ranked group → member → stock detail.
- Active setup and blocker interpretation.
- Stock detail → prefilled Sizer.
- Missing evidence and unranked group states.
- Returning to the prior filtered list.

At a 1366×768 viewport and normal zoom:
- Tape should show at least 10 ordinary rows without terminal setup lists inflating them.
- Groups should show at least 10 comparable rows with ranking evidence visible.
- Stock detail should expose its conclusion and primary blockers without scrolling.
- Raw hashes, Python representations and repeated diagnostic paragraphs should not occupy primary views.

Check API payload sizes and memory on representative heavy symbols/groups. Preserve prior full-population memory safeguards.

6. Save and deliver.

Update README, project state and a concise UX completion receipt. Commit, push and open a draft PR with the correct base; do not merge or switch the production runtime automatically.

Return:
- Branch, commit, draft PR and base.
- Decision/explanation findings and exact fixes.
- Before/after screenshots with accessible paths.
- Workflow and performance verification.
- Any genuinely missing data or remaining blocker.
- Confirmation that the existing timer/runtime and protected artifacts remain intact.

Make routine design decisions autonomously within this scope. The goal is a readable research workflow:
market context → leading groups → stocks → setup and blockers → sizing.