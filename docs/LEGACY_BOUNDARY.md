# Aperture Legacy Boundary

Status: **ACTIVE COMPATIBILITY BOUNDARY**

Effective: 2026-09-07

The repository began as a Python/Streamlit Market Dashboard and evolved into the
Aperture React/FastAPI decision workstation. Historical code is retained where it
supports reproducibility, compatibility, or research comparison. Retention does
not make it current product authority.

## Preserved legacy concepts

The following are legacy or research-only unless a current versioned Aperture
contract explicitly consumes them:

- Opportunity Score;
- the original Leadership Score and its categorical states;
- `trend_stage` and labels such as Extended, Confirmed Leader, Emerging Leader,
  Pullback in Uptrend, Fading, and Bearish Trend;
- `price_action_state`, directional-bias, and entry-quality classifications;
- EMA9-based legacy features;
- the original simple rolling `atr_14` definition;
- the original Streamlit dashboard and development plan;
- older S1/S2/S3/S4 or S2E product vocabulary;
- candidate chart-pattern lists predating the four-family Setup taxonomy.

Representative preserved modules include:

- `src/market_dashboard/rankings/opportunity_score.py`
- `src/market_dashboard/rankings/leadership_score.py`
- `src/market_dashboard/classification/price_action_state.py`
- legacy feature columns and their regression tests
- `app/` Streamlit diagnostic surfaces

## Allowed uses

- reproduce historical outputs;
- protect backward-compatible data contracts;
- compare a new Aperture model with earlier research;
- support diagnostic/admin workflows;
- retain tests that prove old definitions were not silently rewritten.

## Prohibited uses

Legacy fields must not:

- vote in current Structure or Setup classification;
- promote or veto `WATCH`, `TRADE`, or `ACT`;
- be presented as the current Aperture state grammar;
- be copied into new code merely because they already exist;
- override Wilder ATR or another explicitly versioned current feature;
- cause Streamlit to be treated as the primary interface;
- reintroduce embedded charting into Aperture;
- be treated as current merely because an old README, session report, or archived
  specification describes them in detail.

The existing decision adapter already states that legacy state/score fields never
vote when converting older universe snapshots. Preserve and test that boundary.

## Documentation labels

Historical documents should begin with an unmistakable notice when practical:

> Historical/reference document. It does not override
> `docs/APERTURE_CURRENT_AUTHORITY.md`.

Completed milestone receipts should remain immutable evidence. They may describe
the system as it existed at completion, including versions that are no longer the
target design.

## Migration discipline

When replacing a legacy definition:

1. add a new named feature, engine, schema, or threshold version;
2. keep the prior version reproducible;
3. update materializers and consumers explicitly;
4. rebuild affected snapshots rather than relabeling them;
5. verify the old field no longer votes in the current path;
6. document the comparison and selected reason.

Deleting legacy code is a separate cleanup decision and requires proof that no
historical artifact, test, migration, or consumer depends on it.
