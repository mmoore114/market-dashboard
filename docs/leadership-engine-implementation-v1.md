# Strength/Leadership and Group Ranking V1

AP-LEADERSHIP-001 is an opt-in pure calculation layer. It does not fetch data,
read configuration files, write snapshots, or declare a stock actionable.
`LeadershipOutputV1.research_status` is `experimental_uncalibrated`: the approved
weights and thresholds are initial research hypotheses, not calibrated trading
rules. Structure Engine V1, Setup Engine V1, legacy Leadership Score and the
20/60/120-session SPY-relative features retain their existing behavior.

## API and frozen contracts

- `aperture/leadership_contracts.py`: frozen, extra-field-forbidding, finite-or-null
  Pydantic schemas for source, dated universe, raw/ranked returns, residuals,
  optional context, exact membership, symbol evidence, group evidence/history,
  and complete daily output. JSON round trips retain nulls and enum values.
- `features/leadership_features.py`: existing `ticker/date/close` bar-frame
  adapter, exchange-session returns, closing-high distances and QQQ residuals.
- `aperture/leadership.py`: cross-sectional ranking, group aggregates, independent
  leadership/rotation ranks, dated snapshot selection and consecutive history.
- `aperture/leadership_adapters.py`: existing research-universe decisions,
  `UniverseMemberships`, normalized Deepvue frames, exact identity conversion,
  Structure Engine, Setup Engine and optional legacy context.

The public entry point is:

```python
from market_dashboard.aperture.leadership import calculate_leadership

outputs = calculate_leadership(
    supplied_bars,                    # in-memory frame; no reader is invoked
    calendar=exchange_sessions,        # ordered tuple of actual session dates
    output_sessions=requested_dates,  # strictly increasing calendar subset
    source=attested_source,
    universes=dated_research_snapshots,
    memberships=dated_group_snapshots,
    contexts=contexts_by_symbol_date,  # optional {(symbol, session): context}
)
```

The caller supplies source vendor, dataset identity, split-adjusted price basis,
dividend treatment, volume convention and calendar identity. `adjusted=true`
alone is not an adequate adjustment contract. Metadata columns on bars, when
present, must agree with the attested source. Prices must be positive and finite;
invalid/missing closes become missing observations with explicit return reasons.
Duplicate symbol/session bars, intraday or ambiguous dates and bars outside the
supplied calendar are rejected. Input frames are copied, never mutated.

No calendar or current universe is inferred. The synthetic tests use a synthetic
weekday calendar; that fixture is not a production holiday calendar. An exchange
calendar must include every session needed for the requested lookbacks. No
historical group output is reconstructed using today's membership.

## Point-in-time membership and identity

`DatedProvenanceV1` carries snapshot ID, version, source date, known session,
effective session and validity end. Source/known dates cannot follow the
effective session; validity cannot end before it. Each universe schedule, and
each group-type schedule, must be strictly increasing by effective session with
unique snapshot IDs. Unknown and future-effective snapshots beyond the last
requested output are rejected. A revision becomes active only on its effective
session. The most recent effective snapshot must still be valid; expired
snapshots do not fall back to an older version. Historical outputs retain their
original provenance. A group type with no effective supplied snapshot produces
no groups; a missing research-universe snapshot is an error.

Each ranked symbol is a member of the explicitly dated **equity research**
universe. The existing decision adapter uses `equity_research.eligible`, not
trade eligibility or the legacy broad backfill cohort, and rejects duplicate,
stale, wrong-date or wrong-policy decisions. The direct `research_memberships`
adapter requires caller-attested dated provenance for existing membership objects.
Missing price history does not remove a research member from daily evidence.

Reference symbols are exact-case identities. Deepvue adapters require the
existing complete dated `CompatibilityBoundary`; they never uppercase, casefold,
resolve an alias or apply a crosswalk. `TPC` and `BCPC` convert exactly; `TpC`
and `BCpC` remain preserved source members without market-data conversion.
The caller must pair the boundary with the point-in-time source it attests;
this pure layer cannot discover or independently verify a master snapshot on disk.

The caller-loaded `deepvue_identity_disposition_v1.json` is validated against a
fixed logical hash of its version, source date and exact 29-symbol disposition.
Its seven market series and 22 breadth indicators remain in membership/source
identity evidence but are excluded from security coverage denominators. No regex
classifies new symbols. Crosswalk fields are never consumed; all 23 proposals,
including NXH → BBBY and SEPQ → TUGN, remain unapplied.

`deepvue_membership` returns both the typed group snapshot and an audit tuple for
**every** supplied source row. Unclassified taxonomy rows remain in that audit
with an explicit `__UNCLASSIFIED_SOURCE_ROW__` group sentinel and are not assigned
to an invented group. Snapshot members retain exact source symbol, nullable
market-data symbol, conversion reason and non-security flag. Deepvue can supply
only SUB_INDUSTRY and THEME. Explicit catalogs preserve empty themes. A ticker
can belong independently to multiple themes; duplicate exact membership keys
are fatal. Sectors/industries require separately supplied explicit memberships.

## Individual formulas and missing data

For `n ∈ {5,21,63,126,252}`, `Rn = C[T]/C[T-n] - 1`. Returns are fractions,
not percentage points. Calendar positions determine endpoints; missing bars
never shift a horizon. The two endpoint closes are required; missing interior
bars do not shift or suppress an otherwise valid endpoint return.

Each horizon is independently ranked across the dated research population:
`100 * (average_rank - 1)/(valid_count - 1)`, ascending raw return, average ties.
A singleton emits 50; zero valid observations emit nulls. Every component stores
its denominator, universe snapshot ID and universe policy version.

- `RS_comp = .50*p63 + .30*p126 + .20*p252` requires all three percentiles.
- `RS_rotation = .40*p5 + .60*p21` requires both percentiles.
- `rotation_delta = RS_rotation - RS_comp` requires both aggregates.

Missing components remain null with `MISSING_Rn` evidence. There is no weight
renormalization, blending, categorical rotation label or entry permission.
Changing only short-term returns cannot change the slow composite.

Beta uses the last 252 daily-return session slots ending at T. Each stock and QQQ
daily return requires the immediately preceding calendar-session close; a gap
never becomes a multi-session daily return. Only exact overlapping finite pairs
are retained. At least 126 pairs are required. Sample covariance divided by
sample QQQ variance gives beta; `residual_R63_qqq = R63_stock - beta*R63_QQQ`.
Zero/nonfinite variance, insufficient overlap, missing stock/QQQ R63 and
nonfinite calculation results have separate reason codes. A valid beta remains
visible if the 63-session residual is unavailable. Valid residuals receive the
same cross-sectional percentile rule; their own denominator is stored. QQQ is
benchmark evidence regardless of whether it is a research-universe member.

Closing-high distances are evidence-only fractions `C[T]/max(last n closes)-1`
for n=63 and 252, including T. All n closing observations are required; unavailable
context remains null. Legacy return/SPY-excess fields retain their supplied
**percent** units. They are not recalculated or mixed with new fractional returns.
Optional structure state and active setup families/statuses do not gate strength.

`engine_context` validates symbol, session and source against existing engine
outputs. Setup errors, unevaluated active instances or corrected-replay requirements
produce missing setup context. Valid empty setup context is an empty tuple;
missing context is null. Terminal instances are excluded from active context; their unevaluated retention
does not suppress other valid active instances.
The adapter does not translate old S1–S4 fields into Structure Engine states.

## Group metrics and ranks

The denominator is every dated **security** member in the supplied group,
including members outside the research universe or without a compatible symbol.
These records reduce coverage instead of disappearing. `outside_universe_count`
reports them. Explicit non-security records have a separate excluded count and
remain in the output's membership evidence. Only research-universe strength
observations contribute valid strength values.

Each group reports:

- total members, valid RS_comp count, coverage, median and linear p75;
- valid RS_rotation count/coverage, median rotation and median delta with count;
- fraction of valid composites >=80; residual-percentile median and valid count;
- valid structure denominator, UPTREND fraction and UPTREND-or-EMERGING fraction;
- setup-context denominator and distinct TRIGGERED member counts per family;
- missing structure/setup/residual context reasons when coverage is incomplete.

Medians use midpoint interpolation. Fractions use their stated valid denominator;
missing structure is not treated as NEUTRAL. Multiple same-family triggered
instances for one member count once. A family count is null if no setup context
is available, and zero if context is available but no member has that trigger.
Counts with partial context are explicitly bounded by `setup_context_count`.

Within each type/session, eligible groups rank descending by median RS_comp with
average ordinal ties. Eligibility requires >=5 valid composites **and** >=.60
coverage. Metrics remain visible for ineligible groups, with null rank and
separate gate reasons. Rotation rank independently applies the same gates to
valid RS_rotation and ranks its median. `rotation_rank_advantage` is leadership
rank minus rotation rank and is null unless both ranks exist.

History uses exchange-session indices, not elapsed calendar days. Five-/twenty-
session changes are prior minus current rank, independently for both ranks.
The complete intervening sequence of supplied group outputs is required; gaps
are not filled. Rank endpoints must be eligible. Intermediate ineligibility does
not erase a supplied historical observation. Top-quintile membership means
ordinal rank <=ceil(.20*eligible_group_count), including average tie ranks.
Streaks independently reset on ineligibility, falling outside that boundary,
missing group output or an absent exchange-session output. Membership revisions
do not rewrite or erase earlier outputs and do not alone reset a streak.

## Versions, representative evidence and verification

Formula version is `leadership-formulas-v1`; threshold version is
`leadership-thresholds-v1`. The immutable policy names weights, coverage/count
bounds, beta window/minimum, breadth threshold and top-quintile fraction.
`rules_fingerprint` hashes canonical sorted JSON for that policy and the explicit
ranking, quantile, beta, closing-high and history definitions. The V1 rule hash is
`30178a5ec7822b97a2341f74b5965f1db3997c72a181f02eb421ded492923485`. A separate calendar
fingerprint hashes only the supplied calendar prefix through T, so extending the
future calendar cannot alter earlier evidence. Outputs contain no retrieval
clock or nondeterministic identifier.

Representative synthetic ranking fixture:

| Symbol | p5 | p21 | p63 | p126 | p252 | RS_comp | RS_rotation | delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 100 | 50 | 0 | 50 | 100 | 35 | 70 | 35 |
| B | 50 | 100 | 50 | 100 | 0 | 55 | 80 | 25 |
| C | 0 | 0 | 100 | 0 | 50 | 60 | 0 | -60 |

The independent group fixture has two five-member, fully covered groups:
NEW median composite 10 / rotation 90 ranks 2 / 1 (advantage +1), while OLD
median composite 90 / rotation 10 ranks 1 / 2 (advantage -1). A four-valid-member
group retains its median even at 100% coverage but cannot rank. Six valid members
out of ten meet the 60% gate; six out of eleven do not.

Focused verification command:

```bash
.venv/bin/python -m pytest tests/test_leadership_features.py tests/test_leadership_ranking.py tests/test_leadership_groups.py tests/test_leadership_adapters.py -q
```

The synthetic tests cover formulas, exact boundaries, gaps, effective revisions,
null denominators, ties, independent rotation, beta alignment, context separation,
identity/disposition behavior, frozen JSON round trips and input preservation.
All new tests block socket/httpx network access. The pipeline test also forbids
`builtins.open`, `io.open` and `os.open`. The full suite preserves legacy rankings
and all Structure/Setup tests. See PROJECT_STATE for observed final counts and
protected-file verification.

No production materialization, calibration, exposure build, crosswalk application,
UI, market regime, extension permission, trade/risk policy or ingestion is added.
The separate September master timestamp-precision publication blocker is deferred.
