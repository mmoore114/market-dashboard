# Codex Next Task

**Task ID:** AP-FOUNDATION-RECONCILE-001

**Status:** READY

**Issued:** 2026-09-06

**Base commit:** `c5e696ddeb0be2a2fb8befa91ad2adc292ee49e9`

## Goal

Reconcile the eight hard blockers found by the AP-LOCAL-MATERIALIZER-001
read-only audit into verified offline evidence and a precise remaining-action
plan. Do not attempt another workstation snapshot build during this milestone.

This is foundation reconciliation, not market-data acquisition or publication.
Resolve only what the existing local evidence can establish honestly. A finding
that needs new provider data, operator attestation, or publication must remain
blocked with an exact bounded next action; never infer or manufacture readiness.

## Branch and handoff

1. Begin from the exact base commit above on a new branch named
   `codex/foundation-reconciliation-v1`.
2. Target a draft PR to `codex/local-materializer-v1`.
3. Read `AGENTS.md`, `docs/PROJECT_STATE.md`, this file,
   `docs/local-materializer-v1.md`, the snapshot V2 contract, and the existing
   data/publication contracts before editing.
4. Work through this bounded milestone autonomously. Stop only for a material
   contract contradiction, a destructive action, or authority beyond this task.
5. At completion, update `docs/PROJECT_STATE.md` and this file, run verification,
   commit, push, open the draft PR, and return only the commit SHA, test totals,
   draft PR link, remaining blockers, and exact next bounded action.

## Authority boundary

Authorized:

- source code, tests, configuration schemas, and documentation required for a
  deterministic offline reconciliation workflow;
- read-only inspection of the exact local artifacts and private audit evidence;
- new reports and candidate artifacts written only beneath the existing explicit
  workstation staging workspace;
- local hashes, field-level comparisons, calendar validation, coverage analysis,
  and isolated fixture simulations;
- one implementation commit, push, and draft PR as described above.

Not authorized:

- network or provider requests of any kind;
- production-data mutation, ingestion, repair, publication, or migration;
- another real snapshot build or production API startup;
- security-master or exposure publication, universe publication/rebuild,
  crosswalk application, or use of the unpublished September master;
- copying licensed rows, machine paths, private reports, credentials, databases,
  Parquet/CSV data, manifests with local provenance, or staging outputs into Git;
- changes to `.vscode/settings.json`, merges, or broker behavior.

## Required workflow

Add a narrow offline reconciliation command or extend the existing materializer
CLI with explicit `reconcile-plan`, `reconcile`, and `reconcile-validate` behavior
only if that fits the current architecture cleanly. Plan mode must make zero file,
database, or network reads and no writes. Reconciliation must open production
sources read-only, disable DuckDB external access, preserve before/after hashes,
and write only to an explicit nonproduction workspace. Validation must be offline
and bind the exact plan, input hashes, findings, and generated evidence.

Use the original audit receipt and its exact eight finding codes as the starting
population. Every original finding must end in exactly one state:

- `RESOLVED_BY_VERIFIED_EVIDENCE`;
- `REMAINS_BLOCKED_REQUIRES_LOCAL_REVIEW`;
- `REMAINS_BLOCKED_REQUIRES_PUBLICATION`;
- `REMAINS_BLOCKED_REQUIRES_BOUNDED_ACQUISITION`.

Do not silently add, combine, or drop findings. New findings may be reported
separately with stable codes and evidence.

## Reconciliation requirements

### Adjusted bars

- Compare the DuckDB and all 100 declared Parquet copies at key and field level.
- Report rows present only in either store and per-field mismatch counts, date and
  symbol bounds, duplicates, nulls, invalid OHLCV, and logical fingerprints.
- Trace publication receipts/configuration where available. Do not choose a
  canonical copy merely because it is newer, larger, or first in the plan.
- If authority cannot be proved locally, retain the blocker and propose the exact
  review or recoverable publication action required.

### Legacy universe and Aperture schedule

- Compare DuckDB and Parquet legacy-universe copies exactly and explain their
  differences without treating either as the Aperture research universe.
- Identify the authoritative versioned rules that define Aperture research and
  trade membership. Build a candidate dated schedule in staging only when every
  member, identity interval, policy version, effective session, and rules hash is
  derivable from approved local sources.
- A candidate is not a publication. Never label legacy exposure eligibility as a
  canonical Aperture research/trade schedule.

### Calendar

- Inventory installed, versioned exchange-calendar sources and existing calendar
  artifacts. A union of observed bar dates is not an exchange calendar.
- A candidate XNYS schedule may be generated in staging only from an authoritative
  versioned calendar implementation already available locally. Record package or
  source version, timezone, regular and early closes, session range, artifact hash,
  and reproducibility command.
- Validate T and T+1 against that exact schedule. If no authoritative source is
  available offline, retain the blocker and specify the minimal later action.

### Provenance and adjustment basis

- Recover only attestations supported by existing receipts, configurations, and
  immutable source metadata: provider/dataset, price adjustment, dividend
  treatment, matching volume basis, observation/fetch/publication times, coverage,
  calendar binding, and artifact hashes.
- Produce a reviewable candidate manifest plus a field-by-field evidence matrix.
  Unsupported fields remain UNKNOWN; Codex must not self-attest provider semantics.
- A candidate manifest is not a publication or operator approval.

### Identity and time alignment

- Calculate the intersection of adjusted-bar sessions, complete published exact
  security identity, complete exposure-policy-v3, and any valid candidate universe
  schedule.
- Do not project the 2026-07-26 master backward to candidate T=2026-07-24 and do
  not consume the unpublished 2026-09-05 artifact.
- Report every feasible T/T+1 pair, or prove that none exists with current local
  artifacts. Never choose a convenient date that violates identity intervals.

### Benchmarks and spot volatility

- Assess exact session coverage for SPY, QQQ, IWM, RSP, QQQE, and the versioned
  non-security VIX/approved-equivalent spot series after calendar and population
  reconciliation.
- Distinguish absent symbols, missing sessions, insufficient warmup, copy-selection
  effects, and missing spot identity/source.
- Produce a bounded acquisition specification for only the remaining gaps,
  including identifiers, date bounds, expected rows, endpoint classes, request and
  record caps, and validation gates. Do not execute it.

## Outputs and acceptance

Create private staged outputs containing:

- resolved plan and input/hash receipt;
- exact eight-finding disposition ledger;
- bar and universe copy-difference reports;
- calendar candidate/evidence or explicit absence report;
- provenance evidence matrix and candidate manifest;
- identity-valid T/T+1 intersection report;
- benchmark/spot/research coverage report;
- bounded next-action specification;
- preservation proof and deterministic logical fingerprints.

Commit only reusable code, schemas, synthetic fixtures, and documentation. Tests
must cover zero-I/O planning, zero-network reconciliation, no production writes,
finding conservation, conflicting copies, unsupported provenance, calendar early
closes, identity interval refusal, benchmark/spot gaps, deterministic receipts,
tamper detection, and protected-file preservation.

Run focused tests, the complete Python suite, applicable frontend/contract checks,
and `git diff --check`.

Success does not require clearing all eight blockers. It requires that every one
is backed by exact evidence and reduced to either a verified resolution or the
smallest honest next action. Do not build a real workstation snapshot in this
milestone.
