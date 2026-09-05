# Data foundation — repository inspection and remaining audit

Reviewed 2026-09-05 at foundation commit `d1192f6`.
Scope: tracked code and checkpoint inspection; laptop datasets were not mounted.

| Area | Evidence available | Remaining work |
| --- | --- | --- |
| Security identity | Dated security master, versioned exposure policy, v2/v3 preservation and recoverable publication are implemented. | Verify local snapshots; define ticker changes, delistings, stable security identifiers and classification effective dates. |
| Raw flat files | Separate flat-file processing and inventory/stress-validation scripts exist. | Inventory actual files, session coverage, hashes and gaps; do not redownload by assumption. |
| Adjusted bars | REST ingestion and validators exist; checkpoint records 100 tickers and 63,279 rows. | Verify local coverage and full values, vendor adjustment semantics and corporate-action/volume conventions. No raw-to-adjusted corporate-action bridge has been established by this inspection. |
| Storage consistency | Publication uses explicit pending/complete/recovery states and DuckDB/Parquet reconciliation. | Inspect current publication state; do not describe two stores as one atomic transaction. |
| Universes | Market mapping, equity research and equity trade have separate contracts; production planning universe is broader. | Verify which builders actually consume the new contracts. Preserve legacy and v3 partitions. |
| Features | Legacy simple ATR and additive Wilder ATR have distinct names; missing values remain null. | Freeze engine feature timing, EMA10, medians versus means, window inclusion and missing-session behavior. |
| Calendar | Source formulas are session-based; checkpoint describes 90-session coverage. | Establish authoritative exchange calendar, holidays, partial sessions and as-of timestamps. Do not substitute calendar-day arithmetic. |
| Reproducibility | Policies, fingerprints and dated outputs are implemented in parts of the pipeline. | Define end-to-end revision identity, engine warmup/replay state, delisted coverage and historical memberships. Do not claim universal point-in-time completeness. |
| Industry/theme taxonomy | No completed Deepvue audit or owned taxonomy implementation was found in the inspected documentation. | Inspect Deepvue and reconcile its actual hierarchy to Massive identities. Do not assume labels imply licensed GICS codes. |
| Engine implementation | Milestone 1 provides typed contracts; S1/S2/S3/S4 and legacy classifiers remain. | Resolve the engine specification register before implementing new semantics. |

## Proposed taxonomy audit outputs — not yet an implemented schema

Keep provider facts, normalized hierarchy and curated memberships distinct.
Inspect whether a security has one structural classification and multiple theme
memberships. Record source label/code, source date, effective period where known,
mapping version and exceptions. Determine actual hierarchy levels from Deepvue;
do not conflate industry group, industry, sub-industry and thematic group.

Use Massive security identities for reconciliation. Ambiguous/unmatched symbols
must remain visible; never silently discard them. A present-day Deepvue export
is a current snapshot, not historical membership evidence.

No licensed constituent dataset, raw export, credential, local database, or
machine path belongs in Git. Commit schema, transformations, synthetic fixtures
and audit descriptions; keep source datasets in approved local storage.

## Local audit acceptance

Report actual paths privately, date windows, symbol/row counts, duplicate keys,
required-field nulls, missing sessions, publication state, policy identity and
DuckDB/Parquet agreement. Preserve the 100-ticker history and completed manifests.
Any proposed new download must identify exact scope and cost controls separately.
