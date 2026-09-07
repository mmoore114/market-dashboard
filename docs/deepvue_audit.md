# Deepvue audit — authenticated classification inspection

Updated 2026-09-05.

The user authorized inspecting Deepvue for Aperture's industry, sub-industry,
group and theme organization. Authentication was confirmed in the cloud browser.
The inspection was read-only except for selecting an existing column set on an
unsaved all-stock screen and downloading CSV exports. Saved screens, watchlists,
account settings, and dashboards were not overwritten.

## Verified export

- The unsaved all-stock screen contained 11,370 rows and exported all 11,370
  unique symbols with no duplicate or blank symbol.
- Export fields were Symbol, Next Earnings Date, Relative Measured Volatility
  (15 days), Avg Dollar Volume (20 day), ADR Percent (20 days), Last, Industry
  Rank (3 month), Sub-Industry, Absolute Strength (1 and 3 month), and Weinstein
  Stage.
- Deepvue offered Copy Symbols, Export CSV, and Export Excel.
- Treat `-`, blank, `N/A`, and `NaN` as missing classifications, not categories.
  Meaningful Sub-Industry coverage was 5,462 symbols (48.04%) across 164 labels.
  Rank coverage was 5,465 symbols (48.07%), with observed values 1 through 73.
- Every meaningfully classified row had a rank. Three unclassified rows carried
  a rank and must remain unclassified pending review.
- Two labels were internally rank-inconsistent in this snapshot: Retail REITs
  and Health Care REITs. Aperture must preserve symbol-level source ranks but
  publish no group rank when constituent values disagree.

## Verified dashboard classifications and themes

The Industry Ranks widget showed eleven sector-level names: Energy, Health Care,
Materials, Financials, Information Technology, Communication Services,
Utilities, Consumer Staples, Real Estate, Consumer Discretionary, and
Industrials. It displayed 1M/3M/6M/12M ranks and stock counts. The screener export
did not include sector or parent-industry columns, so no parent hierarchy may be
inferred from the sub-industry name alone.

Theme Tracker displayed 31 non-exclusive themes: Genomics, Semiconductors, Oil &
Gas, Cybersecurity, Telecom, Quantum, Steel, AI, Biotechnology, Bitcoin Miners,
Silver Miners, Gold Miners, Materials, Banks, Industrials, Transports, HealthCare,
Real Estate, Aerospace, Growth Stocks, Retail, Airlines, Utilities, Robotics,
Software, Solar, Home Construction, Bitcoin, Medical, Social Media, and China
Internet. The widget exposed Today/1W/1M/3M/YTD performance. Constituent export
was not offered, but authenticated read-only traversal of every theme's stock
list verified the complete many-to-many membership shown on 2026-09-05. Counts
ranged from 0 to 410; the largest lists were HealthCare (410), Biotechnology
(237), Software (105), and Banks (101). Bitcoin explicitly displayed zero stocks.
Every captured populated-theme count was reconciled to the count displayed by
Deepvue. The source capture remains local and uncommitted.

## Aperture import decision

`scripts/import_deepvue_taxonomy.py` validates a dated export by default and only
persists on explicit `--publish`. The normalized snapshot retains provenance,
missing classifications, per-symbol ranks, and row fingerprints. A separate
group snapshot publishes a rank only when all ranked constituents agree.
Sector and parent industry remain null until sourced; they are never
reverse-engineered from a label. Verified theme membership is imported as its
own dated, many-to-many snapshot with a separately preserved theme catalog.

No API, GICS license/equivalence, historical taxonomy, or revision history was
verified. Deepvue remains an adjacent chart-review and
bootstrap reference; Aperture must not depend on authenticated Deepvue at runtime.

Do not commit raw proprietary exports or account information to Git.
