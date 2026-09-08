# AP-WORKSTATION-UX-001 completion receipt

Implemented on `codex/workstation-ux-001`, stacked on draft PR #18 branch
`codex/universe-expansion-v1`, base commit
`57c8aaaf1875d63a0e65b802229b33c8a215f7aa`. Neither PR is merged or deployed.
Production remains pinned to `7de9858f055e7e79d26c6ac8a42896956497b43c`.

## Explanation findings and compatibility

Retained fingerprint:
`4d8ca015e9deadc1ca7f26b53596134072720ae9714c2be89e778df8ca6798c6`.
The deterministic sample is the first five alphabetically sorted WATCH symbols:
A, ABCL, ABNB, ADM, AEM. Raw before/after V2 responses and the aggregate audit are
private evidence; no market dataset or screenshot is committed.

| Finding | Exact path and correction |
| --- | --- |
| UNKNOWN plus action-session mismatch | `decision_risk.regime_gate` compares an absent eligibility date with the action date. The new review describes missing confirmation; real contradictory dates/source mismatches remain invalid-data blockers. |
| Missing earnings plus short calendar | `decision_components.earnings_gate` has neither source coverage nor a fifth future session. These are separate problems, both retained. Future `refresh.inputs.prepare` uses the verified XNYS calendar through action + 21 calendar days, without extending observations. The regression includes Labor Day and verifies T+5 = September 14 from September 4. |
| Triggered pullback rejected by setup errors | `setup_v2` aggregates detection errors into `SetupOutput.errors`; Decision V1 applies that tuple globally. The sample error is `corporate_action_quarantine` from EP detection. Review attributes errors by exact family/direction, keeps unattributed errors blocking, and explicitly discloses the retained global veto. |
| Failed rotation predicates alongside passing strength | The canonical OR result already passes. Review reports the successful branch; complete original predicates remain available. |
| Blank proposal emits repeated invalid sizing | Review shows one “Enter trade details” prompt. Sizer submits explicit proposals to the unchanged canonical calculator and distinguishes theoretical amounts from policy-qualified size. |
| Terminal/opposite setups inflate current rows | Tape and Overview summarize same-direction active setups, prioritized TRIGGERED then NEAR_TRIGGER. Setups exposes terminal and opposite-direction history separately, with original evidence intact. |

`decision-review-v1` is a versioned **read-only explanation projection**, not a new
Decision engine or a migration of immutable output. No TRADE/ACT promotion, gate,
threshold, fingerprint, output reference or persisted decision changed. Correcting
the canonical global Setup veto itself would require a separately versioned decision
change and compatible rematerialization; this task discloses it rather than rewriting
history. The future calendar fix cannot repair the retained snapshot's calendar.

| WATCH symbol | Passing strength | Additional local interpretation |
| --- | --- | --- |
| A | Established | Evaluated TRIGGERED LONG pullback; no matching detector error; retained unrelated EP veto. Sub-industry qualifies. |
| ABCL | Established | Triggered pullback plus forming contraction; retained unrelated EP veto. Sub-industry rank unavailable. |
| ABNB | Established | Evaluated triggered pullback; retained unrelated EP veto. Sub-industry qualifies. |
| ADM | Rotation | No active same-direction setup; sub-industry rank unavailable. Failed established branch is not a veto. |
| AEM | Established | Evaluated triggered pullback; retained unrelated EP veto. Sub-industry rank unavailable. |

All five also lack confirmed regime and earnings coverage, have the short retained
calendar and no complete user proposal. A's frozen EMA10 reference is available;
the UI labels it a frozen reference and separates lifecycle invalidation from a
proposed trade stop. It does not invent an executable entry.

Existing decision outputs contain **2,743 unique stocks: 254 WATCH, 2,489 NONE,
0 TRADE, 0 ACT**. Overlapping per-stock reason counts include: missing regime,
missing earnings, short calendar and global Setup errors each 2,743; outside trade
universe 1,967; strength ineligible 1,707; Structure ineligible 1,474; extension
below reference 1,326 and above cap 72. Terminal evidence appears in 2,682 stocks;
opposite-direction reasons in 2,637. These counts overlap and must not be summed.

## Research workflow and performance

Brief → filtered Tape → overview/setup/blockers → prefilled Sizer and
ranked group → bounded members → stock detail → prior list were exercised in a
real browser. Missing evidence and unranked groups remain accessible. Laptop
1366×768 at normal zoom shows **11 complete Tape rows and 10 ranked Groups rows**;
Agilent's conclusion and primary blockers fit without scrolling. Mobile 390×844
uses bounded horizontal table scrolling and a single scrolling detail surface.
Before/after desktop and mobile captures were personally inspected, including
Tape, Groups, detail, Rules and missing-data states. Raw hashes and full diagnostic
checklists are collapsed. There are no charts.

Final live checks used the unchanged, genuinely fresh retained snapshot through
07:10 UTC on September 8. Its original expiry remains **13:30 UTC / 08:30 CDT**;
no timestamp or deadline was extended, no snapshot built and no acquisition/replay
performed. The standalone preview ran under short-lived user-systemd services
between timer dispatches; only these task-owned previews were stopped. The final label/direction review
was rechecked at 07:10 UTC.

Measured loopback responses, inclusive of metadata:

| Response | Bytes | Seconds |
| --- | ---: | ---: |
| Tape, 100 rows | 137,171 | 0.109 |
| Sub-industries, up to 100 rows | 96,306 | 0.018 |
| A V2 detail | 254,463 | 0.013 |
| BA V2 detail | 259,996 | 0.014 |
| NTRA V2 detail | 422,221 | 0.016 |
| Financials member page 1, 100 rows | 105,625 | 0.024 |
| Financials member page 11 | 79,418 | 0.017 |

Financials has 1,045 published members; outside calculated coverage remains explicit.
No browser evidence-graph reconstruction or expanded Leadership/Regime model is
needed. Research health's membership-policy read took 3.265 seconds under contention
(0.712 seconds in the earlier probe), a remaining latency consideration separate
from the bounded stock/group queries.

Final measured API process peak RSS: **1,110,724 KiB (1.059 GiB)**, resident after
queries 1,012,612 KiB. During browser use the service cgroup peaked at
1,153,957,888 bytes (1.075 GiB; includes accounting beyond process RSS).
The final probe recorded zero high/max/OOM/kill events. An earlier supervised
probe crossed MemoryHigh 21 times but had no max/OOM/kill events. Peak across
all process probes was 1,116,200 KiB. These are API load/serve measurements, not
a new snapshot-construction benchmark. Existing bounded construction, checkpoint
recovery and reference validation safeguards are unchanged.

## Verification and preserved state

- 21 focused Python tests passed: research explanations/API bounds, recovery,
  model validation and complete V2 local-field/shared-reference preservation.
- 11 component tests passed, including LONG and SHORT Sizer handoff and expired
  snapshot refusal. Live desktop/mobile workflows passed; synthetic desktop/mobile
  workflows also passed. No full Python suite was run.
- Typecheck/production build, OpenAPI check, generated TypeScript synchronization,
  ESLint/Prettier, targeted Ruff and whitespace checks passed.
- Production refresh configuration, timer/service units and the owner's settings
  modification retain their baseline hashes. All 1,383 files in the wider protected artifact baseline also match;
  the audit is retained privately. Original snapshots, checkpoints, captures, datasets and
  backups remain in place; new captures are in separate directories.
- All 2,743 retained shard payload hashes and version bindings passed a read-only
  audit, including the existing hash-proven replay-code compatibility receipt.
  Compressed and uncompressed snapshot SHA-256 values also match their envelope.
- Timer stays enabled and active; next normal after-close eligibility is September
  8 at **20:45 UTC / 15:45 CDT**. The 15-minute scheduler continues independently.
  Production API 8000 and Workstation 5173 remain running for the owner.

Private evidence directory: `aperture-workstation-ux-2026-09-08` beneath the operator's
home. It contains `before-complete`, `after-accepted`, intermediate screenshot directories, browser and
focused-test logs, `aggregate-before.json`, sampled responses,
`performance-final.json`, `api-browser-memory.txt` and `preservation-final.json`.
Missing VIX/earnings and the disclosed canonical Decision V1 veto are the remaining
research limitations. Deployment and a new canonical decision version are outside
this completed UX task.
