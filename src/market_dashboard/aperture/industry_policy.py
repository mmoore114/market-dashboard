"""Industry authority, versioned separately from retained sub-industry policy."""

from dataclasses import asdict, dataclass

from .decision_policy import RULES_FINGERPRINT as DECISION_V1
from .leadership import fingerprint
from .regime_policy import RULES_FINGERPRINT as REGIME_V1


@dataclass(frozen=True)
class IndustryPolicyV1:
    level: str = "INDUSTRY"
    group_rank_fraction: float = 0.80
    minimum_group_members: int = 5
    minimum_coverage: float = 0.60
    minimum_internals_groups: int = 5


POLICY = IndustryPolicyV1()
DECISION_RULES = fingerprint(
    {
        "engine": "decision-risk-v2",
        "base": DECISION_V1,
        "industry_policy": asdict(POLICY),
        "group": "one exact INDUSTRY parent path; own eligible rank population; ceil(.8*N); subindustry and themes context only",
        "setup_errors": "retained global veto; scope decision deferred",
    }
)
REGIME_RULES = fingerprint(
    {
        "engine": "market-regime-v2",
        "base": REGIME_V1,
        "industry_policy": asdict(POLICY),
        "internals": "INDUSTRY own membership and coverage; eligible comp/delta medians; at least five; no V1 memory reuse",
    }
)
