# Deepvue audit — authenticated classification inspection

Updated 2026-09-07.

The September 5 observations below remain dated evidence. The separately captured
September 7 hierarchy and completed private inventory are recorded at the end.

The user authorized inspecting Deepvue for Aperture's industry, sub-industry,
group and theme organization. Authentication was confirmed in the cloud browser.
The inspection was read-only except for selecting an existing column set on an
unsaved all-stock screen and downloading CSV exports. Saved screens, watchlists,
account settings, and dashboards were not overwritten.

## September 5 verified export

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

## September 5 dashboard classifications and themes

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

## September 5 Aperture import decision

`scripts/import_deepvue_taxonomy.py` validates a dated export by default and only
persists on explicit `--publish`. The normalized snapshot retains provenance,
missing classifications, per-symbol ranks, and row fingerprints. A separate
group snapshot publishes a rank only when all ranked constituents agree.
In that September 5 import, sector and parent industry remain null; they are
never reverse-engineered from a label. The September 7 source described below
has not been published or incorporated into that import. Verified theme membership is imported as its
own dated, many-to-many snapshot with a separately preserved theme catalog.

No API, GICS license/equivalence, historical taxonomy, or revision history was
verified. Deepvue remains an adjacent chart-review and
bootstrap reference; Aperture must not depend on authenticated Deepvue at runtime.

Do not commit raw proprietary exports or account information to Git.


## September 7 hierarchy and verified local inventory

`AP-DEEPVUE-INVENTORY-001` verified the privately supplied package against the
[capture manifest](deepvue_capture_manifest_2026-09-07.json). All three CSV hashes,
byte sizes, headers and row counts match; no package file is missing. See the
[inventory completion record](deepvue_inventory_2026-09-07.md) for portable path
resolution, duplicate reconciliation and verification boundaries.

The September 7 export contains 11,368 unique symbols and explicit Sector, Group,
Industry and Sub-Industry columns. Sector/Group/Industry cover 5,461 symbols, with
11/25/73 distinct labels respectively; Sub-Industry covers 5,458 symbols across
164 labels. The remaining 5,907 parent classifications and 5,910 sub-industry
classifications are missing, not inferred. This resolves the earlier absence of
parent fields as a source-availability gap, not as a runtime publication.

Four child labels have multiple observed parents, exactly as recorded in the
manifest: Retail REITs and Health Care REITs at Sub-Industry -> Industry;
Real Estate Management & Development and Ground Transportation at Industry ->
Group. Original per-symbol assignments remain intact. No canonical parent was
selected, and no taxonomy conflict was repaired.

The stock export and themes remain September 5 captures. Themes contain 1,794
nonempty memberships, 1,323 unique symbols, and an explicit empty Bitcoin marker:
31 themes total, 30 populated. Neither source was refreshed to September 7.
Capture dates describe observed availability; they do not establish historical
membership, a market evidence clock, or a new snapshot evaluation/action date.

The handoff records that the September 7 authenticated UI capture created a new
column set, `Untitled Column Set (2)`, whose four hierarchy selections autosaved.
Existing saved column sets and screens were not overwritten. This local inventory
made no Deepvue requests or UI changes. No import publication, source-data
mutation, snapshot rebuild, or engine change occurred. Historical taxonomy,
revision IDs, GICS equivalence/licensing, universal classification coverage and
resolution of the four parent conflicts remain unavailable or unverified.
