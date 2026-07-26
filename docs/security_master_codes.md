# Security master code policy

Massive ticker-reference records use provider security-type codes and ISO 10383
Market Identifier Codes (MICs). The raw values are retained in every dated
snapshot. Normalization is controlled by `config/settings.yaml`; an unmapped
type or exchange is always classified as `Review Needed` and excluded from the
candidate universe.

The initial allowed exchange mapping is:

| MIC | Normalized exchange |
| --- | --- |
| `XNYS` | NYSE |
| `XNAS` | Nasdaq |
| `ARCX` | NYSE Arca |
| `XASE` | NYSE American |
| `BATS` | Cboe BZX (mapped, but not currently allowed) |

The initial allowed security types are `CS` (Common Stock), `ETF` (Exchange
Traded Fund), and `ETS` (Single-security ETF). Known unsupported codes are
mapped explicitly to excluded categories.

## Codes observed on 2026-07-26

| Raw type | Massive description | Normalized category | Candidate policy |
| --- | --- | --- | --- |
| `CS` | Common Stock | Common Stock | Allowed |
| `ETF` | Exchange Traded Fund | ETF | Allowed |
| `ETS` | Single-security ETF | ETF | Allowed |
| `ETV` | Exchange Traded Vehicle | Exchange Traded Vehicle | Excluded |
| `ETN` | Exchange Traded Note | Exchange Traded Note | Excluded |
| `PFD` | Preferred Stock | Preferred Share | Excluded |
| `WARRANT` | Warrant | Warrant | Excluded |
| `RIGHT` | Rights | Right | Excluded |
| `UNIT` | Unit | Unit | Excluded |
| `ADRC` | American Depository Receipt Common | Depositary Receipt | Excluded |
| `FUND` | Fund | Fund | Excluded |
| `SP` | Structured Product | Structured Product | Excluded |

Observed exchange MICs were `XNYS`, `XNAS`, `ARCX`, `XASE`, and `BATS`.
`BATS` is explicitly normalized to Cboe BZX but remains structurally excluded
because it is not in `allowed_exchange_mics`.

Run `python scripts/validate_security_master.py` after each snapshot to
enumerate all observed raw codes and any unknown mappings before changing the
policy.

Acquisition vehicles cannot be reliably distinguished from ordinary common
stock using the ticker type alone. The initial structural filter therefore
uses configured, auditable name patterns and reports the exclusion reason
`acquisition_vehicle`. This is deliberately conservative and must be reviewed
before a historical-bar backfill.
