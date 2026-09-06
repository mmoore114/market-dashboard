# Exact-case security identity audit

This records the initial audit. For the implemented reader classifications,
resolved migrations and current publication gates, read the
[identity-boundary contract and migration map](security-identity-boundary.md).

The provider ticker is an identity-bearing string, versioned as
`provider-ticker-exact-case-v1`. A snapshot/ticker key uses exact case. The master
builder no longer strips or uppercases ticker values and rejects invalid strings
instead. Every exact duplicate is fatal, including otherwise identical rows.
Casefold groups exist only in diagnostic reports. They are not stored search
keys, persistence keys, overrides or automatic joins.

## Audit coverage and disposition

Repository Python source, scripts and tests were searched for uppercase,
lowercase, casefold, duplicate reduction, joins and collations. Findings:

| Surface | Finding and disposition |
| --- | --- |
| `data/security_master.py` | Removed ticker uppercasing and last-row duplicate selection. Exact strings reach the existing 18-field schema. Exchange/type/currency code uppercasing and name/locale/market lowercasing are classification normalization, not ticker identity, and remain unchanged. The legacy public `persist` path now refuses mixed-case publication before any write because its callers can immediately run incompatible exposure classification. |
| `data/security_master_refresh.py` | Removed uppercase-only rejection. All exact duplicates reject. Reports mixed-case types and non-unique casefold groups. Source CSV symbols are read verbatim; matching is exact. Alias review annotations cannot change match status. Fingerprints retain exact ticker strings. |
| `data/security_master_publication.py` | Requires the exact-case identity receipt version and recomputes the reader compatibility gate before connecting to production. Mixed-case snapshots cannot publish; there is no revision/confirmation override for this gate. |
| `data/massive_reference_client.py`, staged fetch | Reference response tickers are not normalized. Query boolean lowercasing does not affect identity. Raw staged pages and fetch provenance remain immutable. |
| `data/exposure_policy.py` | Uppercases maintained ticker registries, review resolution keys/underlyings, override tickers/underlyings, known equities, classified output tickers and underlying validation. Name-extracted candidates are uppercased. These can alias distinct securities. Unchanged, publication blocker. |
| `data/swing_universe.py` | SQL master/exposure joins and pandas ticker merges are exact, but consume already uppercased exposure/bar identities. Indirect blocker until their upstream compatibility is established. |
| `data/daily_ingestion.py`, `data/massive_client.py` | Uppercase requested tickers and stored daily keys. Subsequent duplicate reduction can collapse identities. Unchanged, publication blocker. |
| `data/flat_daily_processing.py` | Uppercases processed ticker keys before duplicate reduction. Raw flat-file retrieval itself does not need a ticker case conversion. Unchanged, publication blocker. |
| `features/equity_features.py` | Uppercases ticker before grouping/features and benchmark joins. Unchanged, publication blocker. |
| `aperture/universes.py`, `aperture/rules.py` | Universe ticker validator uppercases; policy ticker validation requires uppercase. Locale and exchange normalization is separate. Unchanged, publication blocker. |
| `data/deepvue_taxonomy.py`, `data/deepvue_themes.py` | Legacy taxonomy cleaner strips/uppercases source symbols; theme importer imports the same cleaner. The new reconciliation bypasses it for symbols (classification missing-value parsing is reused separately). Legacy source publication remains a compatibility blocker. |
| `scripts/validate_daily_storage.py`, `scripts/report_flat_file_stress_test.py` | Uppercase filename-derived or selected ticker. Unchanged, publication blocker. |
| `scripts/validate_security_master.py` | Exact grouping/unique counts, but lacks collision reporting. New staged validator supplies those reports. |
| `scripts/validate_exposure_classification.py` | Exact SQL joins are safe only when upstream exposure identities are preserved. Indirect blocker. |
| `scripts/ingest_security_master.py` | Calls the legacy master store, then exposure publication. CLI unchanged; shared store now fails before writing a mixed-case master. This compatibility guard is intentional and required to prevent unsafe immediate exposure publication. |
| DuckDB / Parquet | `ticker VARCHAR`, unique `(snapshot_date,ticker)`, no `NOCASE` collation; Parquet string values retain case. Temporary database tests prove TPC/TpC and BCPC/BCpC coexist and compare field-for-field. No schema migration or production write occurred. |
| Tests | Old exact-duplicate collapse expectation was replaced with fatal-duplicate behavior. Added explicit mixed-case, collision, fingerprint, reconciliation, storage capability, publication gate and zero-network tests. Existing exposure semantics remain tested unchanged. |

## Publication boundary

Validation success is distinct from publication eligibility. All 13,155 exact
provider tickers can validate, while the snapshot remains blocked from publication.
Both public master publication paths enforce the gate before production writes.
The low-level store methods are used only for temporary schema capability tests;
they are not a supported publication bypass. The gate must remain until a separate
review establishes end-to-end reader compatibility, including policy registries,
bar keys, features, joins and source importers. Existing exposure policy versions
and July's snapshot are not migrated or reinterpreted.

The two diagnostic casefold groups are `bcpc: [BCPC, BCpC]` and
`tpc: [TPC, TpC]`. An uppercase source `TPC` matches only exact `TPC`, even when
`TpC` also exists. A non-exact alias with multiple candidates stays UNMATCHED with
an AMBIGUOUS_UNRESOLVED annotation. No mapping is inferred from normalization.

All 404 mixed-case rows remain master rows with their actual types: 354 PFD,
30 SP and 20 RIGHT. Candidate eligibility remains a separate classification field;
these rows are not removed because a trade universe may exclude those types.

## Offline revalidation

The existing 14-page fetch was reused without regeneration. All 30 previously
hashed staging artifacts were checked before and after revalidation and were
unchanged. HTTP sends and socket connects were explicitly blocked; call counts
were zero. The new validation receipt records the identity version and current
validator implementation hashes separately from original fetch provenance.

Observed result: 13,155 exact tickers, zero exact duplicates, two case-insensitive
collision groups. Exact Deepvue reconciliation: 11,325 matched security candidates,
16 unmatched and 29 excluded non-security source records. All 23 crosswalks remain
unapplied, with NXH to BBBY and SEPQ to TUGN quarantined. July remains unchanged.

## Superseding compatibility boundary

The blanket reader block above records the initial audit. The implemented
[identity-boundary contract and migration map](security-identity-boundary.md)
now distinguish exact reference consumers from uppercase market-data consumers.
Unsafe reference joins/classification adapters were migrated to a versioned
projection; legitimate uppercase domain invariants remain. The v2 refinement now
gives exact uppercase identities precedence, while
retaining collision reports and rejecting every non-exact reverse lookup. The
two groups are not themselves publication-compatibility blockers. No crosswalk
or alias was applied; publication remains separately unauthorized.
