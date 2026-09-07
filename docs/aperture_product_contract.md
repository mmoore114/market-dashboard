# Aperture Product Contract

> **Historical foundation contract.** It preserves an earlier product design and
> must not be used as current instruction. Use
> [APERTURE_CURRENT_AUTHORITY.md](APERTURE_CURRENT_AUTHORITY.md) for current product
> truth and [PROJECT_STATE.md](PROJECT_STATE.md) for implementation status. The
> S1/S2/S3/S4, setup-candidate, scoring, and sequencing sections below are historical
> hypotheses. Existing code/history remains unchanged.

Status: foundation contract for implementation and testing  
Origin: Aperture V1 prototype, Deepvue account audit, and the existing market-dashboard research engine

## Product definition

Aperture is a transparent, data-first swing-trading research terminal that reduces a broad U.S. market into a small, explainable Watch, Trade, and Act list. It is designed for daily-chart momentum and growth trades lasting days to several weeks.

It supports discretionary decisions. It does not place trades.

## Product principles

1. Explainability before optimization.
2. Risk before reward.
3. Structure, extension, setup, and action state are separate concepts.
4. Point-in-time calculations and out-of-sample validation are mandatory.
5. Every promoted name must expose the exact reasons it passed and the exact vetoes that could block it.
6. The interface should be dense but scannable, with detail available on demand.
7. The system must be teachable: a learner should be able to understand the funnel, the risk unit, and the next action without knowing the implementation.

## Intended funnel

Research universe
-> instrument and exposure classification
-> tradable equity universe
-> market regime
-> sector, industry, and theme leadership
-> relative and absolute strength
-> structural stage
-> extension
-> setup
-> Watch
-> Trade
-> Act
-> position management
-> outcome and benchmark tracking

Each transition must produce reason codes and retain the prior layer's component values.

## Universe separation

Do not force every instrument into one universe.

### Market-mapping universe

May contain liquid diversified ETFs and benchmark instruments needed for:

- SPY, QQQ, IWM, RSP, QQQE, and volatility context;
- sector and industry proxies;
- theme and rotation research;
- breadth and style sleeves.

### Equity research universe

Broad U.S. direct-equity universe used to calculate ranks, breadth, group medians, and historical comparisons. Point-in-time membership is required for backtests.

### Equity trade universe

Production target:

- U.S. common stocks and eligible ADRs;
- no OTC, preferreds, warrants, rights, units, acquisition vehicles, non-equity products, or single-security leveraged products;
- price at least $10;
- market capitalization at least $1 billion;
- 20-session average dollar volume at least $50 million;
- ADR20 at least 2.5%.

These are initial product defaults, not proven optimal thresholds.

### Hysteresis hypothesis

A symbol may enter on strict gates and remain temporarily on softer gates:

- market cap at least $850 million;
- price at least $9;
- ADV20 at least $42.5 million;
- ADR20 at least 2.15%.

Hysteresis must be tested and versioned before it controls production decisions.

## Market regime

The target regime model has five independently visible sleeves:

1. Index structure: SPY, QQQ, and IWM.
2. Breadth: participation above important moving averages and advancing/declining behavior.
3. Internals: concentration and distribution of leadership.
4. Volatility: implied or realized volatility context.
5. Style: growth and cap-weight leadership versus equal-weight participation.

Output:

- Green: normal new-risk allowance.
- Yellow: reduced new-risk allowance.
- Red: no new Act promotions; manage existing positions only.

The V1 risk multipliers were Green 1.0, Yellow 0.5, and Red 0.0. They remain hypotheses until evaluated.

## Strength

Keep the following separate:

- raw multi-window returns;
- percentile-based absolute strength;
- excess return versus a benchmark;
- beta-adjusted residual strength;
- sector and industry relative strength;
- persistence, such as repeated relative-strength days.

### Composite RS candidate

Initial V1 hypothesis:

- 50% three-month return percentile;
- 30% six-month return percentile;
- 20% twelve-month return percentile.

### Residual RS candidate

Three-month return minus beta to QQQ multiplied by QQQ's three-month return, then ranked across the point-in-time research universe.

The existing repository's SPY-relative 20, 60, and 120-session features remain useful components. Do not overwrite them when adding the candidate model.

## Structural stage

Canonical storage should keep structural stage separate from tactical price action.

Candidate values:

- S1: base or early inflection;
- S2: established uptrend;
- S3: deterioration or topping;
- S4: established decline.

A weekly structural stage provides context. A daily helper may provide timelier confirmation. Stage transitions require persistence to reduce single-session flicker.

Do not store S2E as a separate structural stage. Store:

- structure_stage = S2
- extension_state = Extended

The UI may render a combined S2E chip for convenience, but the underlying fields must remain separate.

## Extension

Add explicit, non-destructive metrics:

- percent distance from EMA9, SMA20, SMA50, and SMA200;
- ATR multiple from SMA20 and SMA50;
- Relative Measured Extension candidate;
- distance from recent highs.

The V1 primary metric was:

ATR extension from SMA50 = (close - SMA50) / Wilder ATR14

Initial display bands:

- 0 to 3: potential new-risk range;
- 3 to 5: healthy but increasingly stretched;
- 5 to 7: hold or trim review;
- above 7: extreme.

The V1 new-entry cap was approximately 4.8 ATR. Treat all bands as testable hypotheses.

The repository currently calculates ATR14 as a simple rolling mean. Add Wilder ATR as a separately named feature; do not silently change historical semantics.

## Setup layer

Initial named setup candidates:

- pullback to EMA9/10;
- pullback to SMA20/21;
- volatility contraction pattern;
- tight range or mini coil;
- breakout from a defined pivot or consolidation;
- reclaim of an important moving average or level;
- episodic pivot or earnings-gap thrust;
- character change;
- constructive strength on a weak market day.

Every setup must expose its component conditions. Avoid a pattern label whose definition cannot be reproduced from stored point-in-time inputs.

## Action ladder

Candidate V1 logic:

### Watch

- in the equity trade universe;
- constructive S2-family structure;
- minimum strength threshold.

### Trade

Watch plus:

- market regime is not Red;
- group leadership is not lagging.

### Act

Trade plus:

- a named setup is present;
- extension is within the approved entry band;
- no earnings or event veto;
- a valid stop and nonzero risk-based size can be calculated.

Act means do the discretionary review today. It is not an order instruction.

## Risk contract

Default teaching account:

- account equity: $25,000;
- risk per idea: 0.25%;
- maximum initial dollar risk: $62.50;
- pilot position: one-third of full risk size.

Candidate default stop:

Stop = entry - 1.6 * Wilder ATR14

Full shares:

floor(max dollar risk / (entry - stop))

Pilot shares:

floor(full shares / 3)

The stock detail must show:

- entry;
- stop;
- stop distance in dollars and percent;
- stop distance in ATR multiples;
- full and pilot shares;
- position cost;
- planned dollar risk;
- account percentage at risk;
- any refusal reason.

The sizer must refuse invalid stops, nonpositive share counts, or new risk inside the earnings lockout.

## Earnings veto

The V1 candidate was a hard veto on new Act risk when earnings are within five sessions. The exact event source, timestamp rules, and treatment of unconfirmed dates must be documented and tested.

## Primary interface

Routes or equivalent views:

- Brief: regime, funnel, leadership, Act list, and portfolio heat.
- Tape: dense sortable and filterable candidate table.
- Groups: sector, industry, and theme leadership.
- Book: positions, R multiples, next actions, and portfolio heat.
- Sizer: risk-based position calculator.
- Rules: live human-readable rules tied to versioned configuration.
- Journal/Benchmarks: trade decisions, realized outcomes, counterfactuals, and comparison with passive benchmarks.

Selecting a symbol should open a detail surface with:

- pass/fail checklist and reason codes;
- price and volume context;
- stage, extension, strength, setup, group, regime, and earnings fields;
- sizing preview;
- link or clear workflow for final chart review in Deepvue.

## Scoring policy

The existing Opportunity Score and Leadership Score remain research tools.

Do not let a 0-100 score directly produce an Act state until component definitions, stability, and predictive value have been evaluated. Prefer visible components and explicit gates. If a score remains, version it and show its component contributions.

## Benchmarking and learning

Track:

- trade return and R multiple;
- maximum favorable and adverse excursion;
- holding period;
- setup and state at entry;
- regime and group context;
- slippage assumptions;
- SPY and QQQ return over the same interval;
- passive-account benchmark;
- rejected or vetoed candidates when practical.

Backtests must use point-in-time universes and signal-on-close, fill-no-earlier-than-next-session assumptions.

## Explicitly out of scope for the foundation

- live broker routing;
- autonomous order placement;
- opaque reinforcement-learning agents;
- intraday execution optimization;
- options analytics inside this repository;
- copying or scraping proprietary Deepvue data as an application dependency.

## Decision status

Locked for the foundation:

- transparent funnel;
- risk-first sizing defaults;
- separation of structure, extension, setup, and action state;
- Python/DuckDB research engine;
- React/TypeScript primary interface;
- Deepvue as chart-review companion;
- point-in-time and benchmark requirements.

Requires empirical validation:

- all threshold values;
- score weights;
- stage persistence duration;
- regime sleeve construction;
- setup definitions;
- extension bands;
- exit and scale-in rules;
- earnings lockout length;
- portfolio heat limits.
