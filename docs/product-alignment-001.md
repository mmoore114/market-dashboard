# Product and decision alignment — AP-PRODUCT-ALIGNMENT-001

The owner selected **INDUSTRY** on September 8, 2026, after reviewing the
captured hierarchy alternatives. This is the exact Deepvue `Industry` column,
not its broader `Group` column and not its `Sub-Industry` column. Keep all
**75 distinct full parent paths**, including the 73 distinct leaf labels.
`GROUP` remains broader navigation; `SUB_INDUSTRY` and themes remain context.
The workflow is market environment → themes/groups → leaders → current setups
→ candidates → sizing. Deepvue remains the chart companion.

## Source and authority trace

The [original product contract](aperture_product_contract.md) calls for industry
leadership and a not-lagging group condition but never binds that wording to a
Deepvue field. The [Word source](sources/final-word-spec/word-final-spec.txt)
separates group strength from Structure/Setup. Neither source settles the column.
The [captured manifest](deepvue_capture_manifest_2026-09-07.json) establishes four
separate columns and conflicting parents. The owner's explicit INDUSTRY choice
resolves that ambiguity. The original Grok V1 source was not found in the bounded
local/document search; PR #19's desktop/mobile screenshots were inspected and its
compact layout retained as the available layout evidence.

| Layer | Retained V1 | Industry alignment |
| --- | --- | --- |
| Construction/ranking | `leadership.aggregate_groups` aggregates each explicit level separately, ranks eligible peers within that level | Same algorithm and source membership; no renamed ranks, merged paths or transplanted denominators |
| Leadership context | `engine_context` carries independent Structure/Setup context; RS medians determine group ranks | Unchanged; group rank does not become a Setup condition |
| Regime internals | `regime.internals_sleeve` consumes SUB_INDUSTRY | `market-regime-v2` consumes INDUSTRY; eligible/excluded industry paths are explicit |
| WATCH | Universe, Structure, strength; no subindustry gate | Unchanged |
| TRADE | WATCH plus confirmed regime and SUB_INDUSTRY not-lagging | `decision-risk-v2` requires INDUSTRY not-lagging; subindustry/theme context cannot promote or veto |
| ACT | TRADE plus setup, extension, earnings, size | Same downstream conditions, including the retained global setup-error veto |
| API/UI | Brief, Tape, Groups default to subindustry; V1 snapshot outputs contain subindustry decisions | V2 research Brief/Groups/Tape/detail lead with industry. Historical stored decisions explicitly keep their original policy; V1 transport remains available |
| Shared evidence | Bounded normalized graph and member pages | Preserved, with appended V2 types and frozen prior registry addresses |

Full parent paths distinguish both observed industry conflicts: Ground
Transportation and Real Estate Management & Development. The two subindustry
conflicts also remain accessible. No path is chosen by leaf-label guessing.

## Population, coverage and thresholds

A group needs at least five valid RS-composite members and 60% coverage of its
published security membership to receive a leadership rank. Members outside the
calculated research population remain in the coverage denominator. Non-security
source rows remain excluded as before. Slow and rotation ranks have independent
eligibility populations. Ties use average ranks; rank 1 leads.

Historical September 4 price evidence with the retained current-cohort membership:

| Level | Full paths | Eligible leadership ranks | Illustrative ceil(0.8 × eligible count) |
| --- | ---: | ---: | ---: |
| SECTOR | 11 | 3 | 3 |
| GROUP | 25 | 6 | 5 |
| INDUSTRY | 75 | 24 | 20 |
| SUB_INDUSTRY | 170 | 59 | 48 |
| THEME | 31 | 27 | 22 |

V2 preserves the *relative not-lagging rule*: rank ≤ ceil(0.8 × N), where N is the
selected INDUSTRY level's own eligible count. It does not reuse the old cutoff 48.
The new gate verifies that N matches the eligible industry population, requires
exactly one industry path for the symbol and fails closed for missing coverage,
invalid rank or ambiguous membership. Rank 20 passes out of 24; 20.5 does not.
This is an explicit versioned interpretation, not new empirical calibration.

Regime V2 preserves existing sleeve thresholds, including at least five eligible
groups, but applies them to industries with available composite and delta medians.
The fraction denominator is that eligible industry's comp/delta population;
coverage describes it against all 75 industry paths. Symbol breadth/strength
populations remain separate. Five groups is an absolute evidence minimum, not a
percentile cutoff; it is not scaled from 170 to 75. Existing green/red fractions
remain experimental. No claim of improved predictive performance is made.

## Policy identity, migration and reproducibility

`industry_policy.py` hashes `decision-risk-v2` and `market-regime-v2` against their
V1 policy fingerprints plus the explicit industry policy. V2 Decision, Group and
Setup-action outputs have V2 identities; unchanged extension, strength, earnings
and sizing calculations retain their V1 component identities.

New version selections default to the coherent V2 Decision/Regime pair. Explicit
V1 remains supported; mixed pairs/fingerprints are refused. The materializer and
its independent decision validation dispatch by the selected version. Regime V2
must initialize fresh or consume V2 memory from earlier actual sessions; it
rejects V1 memory. Old evidence-graph type addresses and registry fingerprints are
retained. Loading an old snapshot does not recalculate it, extend its clocks, or
attach a V2 identity to its decisions. The UI's industry context is not a rewrite
of a stored V1 gate.

This task does not activate a new production snapshot or change the pinned runtime.
Future deployment must use a new snapshot with the selected policy identities.
Existing setup checkpoints stay intact. Any future checkpoint compatibility
attestation must distinguish unchanged Structure/Setup calculations from changed
Decision/Regime semantics; do not replay or erase shards merely to inspect them.

Reproduce the bounded, read-only comparison against a retained archive:

```bash
.venv/bin/python scripts/compare_industry_policy.py --snapshot /path/to/current.json --output /new/path/comparison.json
.venv/bin/python -m pytest tests/test_industry_policy.py tests/test_workstation_research.py
```

The comparison uses existing completed-session inputs and a freshly initialized
V2 regime; it does not reuse V1 confirmation history, acquire data, replay setups,
create a trading snapshot, or change the original expiry. Compare group-gate
changes separately from final ladder state, because other vetoes can still block.

## One current setup

`current-setup-display-v1` is an additive presentation contract:

1. Match the selected LONG/SHORT direction and evaluated market session.
2. Consider only FORMING, NEAR_TRIGGER or TRIGGERED instances that were evaluated,
   have no replay requirement, and have no local or unattributed error.
3. Prefer TRIGGERED, then NEAR_TRIGGER, then FORMING; break ties by immutable setup
   ID ascending. Input order, group rank and stock score never select a setup.
4. If none qualifies, distinguish a complete, error-free detection evaluation
   (`No current setup`) from missing/partial/errored evaluation (`Evaluation
   unavailable`). An EP error prevents claiming verified absence of all families.
5. A current evaluated pullback can be displayed despite an unrelated EP error.
   Display is not decision eligibility: the retained global decision veto still
   applies. All qualifying decision setup IDs remain independently evaluated.

Tape's family filter matches the displayed setup. Other active, terminal,
opposite-direction and unavailable instances remain in detail; terminal/opposite
history is paged in groups of 20 with birth and last status-change dates. Existing
engines retain terminal instances for 20 trading sessions (roughly one month);
older active births may be available. A complete 60-day daily archive is not
claimed or reconstructed. Full local evidence and bounded shared/member APIs remain.

## EP veto disposition

`features.setup_features` defaults unattested corporate-action QA to UNKNOWN.
`setup_detection.ep_detection` returns `corporate_action_quarantine` for EP when
QA is not CLEAR; the observed sample carries it for both LONG and SHORT EP.
The sample pullbacks remain evaluated without local errors. A common missing-bar
or invalid-OHLC failure, in contrast, can affect every family; an unattributed
error cannot safely be treated as local.

`setup_v2` collects detection errors into `SetupOutput.errors`.
`decision_risk` then adds `SETUP_ENGINE_ERRORS` to every instance and the overall
setup gate. The [Decision V1 contract](decision-risk-implementation-v1.md) explicitly
says setup engine errors block qualification. Thus the global veto is not a proven
implementation deviation. V2 retains it; no errors are suppressed.

**Remaining policy decision:** authorize a separately versioned family/direction
scope for detector-only errors, while retaining shared-data and unattributed
failures globally and instance evaluation/replay failures locally, or retain the
global veto. An EP-only QA error must not be reinterpreted as verified global data
corruption, but changing its downstream action scope needs that explicit decision.

## Observed historical comparison

The retained expanded snapshot decoded under its original fingerprint
`4d8ca015e9deadc1ca7f26b53596134072720ae9714c2be89e778df8ca6798c6`.
The read-only process peaked at 1,106,416 KiB RSS (about 1.06 GiB); no setup replay
or market acquisition ran. Original expiry remains September 8, 13:30 UTC.
V2 initialized from the existing completed-session regime inputs, without V1
memory. Both regime outputs are UNKNOWN because VIX remains missing.

| Symbol | V1 group gate | V2 industry gate | Current setup display | Stored / compared decision |
| --- | --- | --- | --- | --- |
| A | NOT_LAGGING, rank 1/59 | NOT_LAGGING, rank 1/24; coverage 26/40 | Triggered trend pullback | WATCH / WATCH |
| ABCL | UNKNOWN | UNKNOWN; Biotechnology coverage 181/561 | Triggered trend pullback; forming contraction stays in detail | WATCH / WATCH |
| ABNB | NOT_LAGGING, rank 47/59 | UNKNOWN; Hotels, Restaurants & Leisure coverage 77/130 (59.23%) | Triggered trend pullback | WATCH / WATCH |
| ADM | UNKNOWN | UNKNOWN; Food Products coverage 38/83 | Evaluation unavailable, rather than falsely verified absence | WATCH / WATCH |
| AEM | UNKNOWN | UNKNOWN; Metals & Mining coverage 86/177 | Triggered trend pullback | WATCH / WATCH |

ABNB explains why the selected level needs its own coverage and population.
Its subindustry qualified, but the parent industry does not satisfy 60% coverage.
The other unchanged vetoes prevent an overall ladder change. A synthetic test
also exercises distinct six-subindustry/twelve-industry populations and tied
ranks at the new inclusive boundary; no performance claim follows from either.


## Validation and delivery boundary

The full Python suite passed 3,000 tests with four skips. After adding the final
materializer dispatch regression and correcting pre-publication V2 validation,
all 67 focused industry/research/materializer tests passed. Frontend typecheck,
production build, 11 component tests, lint/format and API/schema synchronization
passed. Four browser workflow tests passed with preserved V1 fixture policies,
and four passed again with the explicit INDUSTRY V2 fixture.

Desktop captures at 1366×768 show 11 complete Tape rows and 10 complete Groups
rows. Desktop and 390-pixel mobile captures were personally inspected, including
the first detail viewport's current setup, earnings blocker and next action.
PR #19 historical captures were reviewed before editing; final captures are
explicitly labeled synthetic fixtures, not newly acquired market observations.
Private screenshots, comparison output and test logs remain outside Git.

Existing snapshot identity, expiry, settings and runtime configuration remain
unchanged. The 2,743 replay checkpoints remain retained. No acquisition, setup
replay or production publication ran. Production stays pinned to `7de9858`, with
the scheduler stopped; temporary validation services are stopped after checks.
This work is for a draft stacked on PR #19 (itself stacked on #18), with no merge
or deployment. Missing VIX, incomplete earnings clearance and the expired saved
snapshot continue to limit readiness.
