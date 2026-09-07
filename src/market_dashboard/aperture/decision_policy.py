"""Immutable opt-in AP-DECISION-RISK-001 hypothesis; no config-file loading."""
from dataclasses import asdict, dataclass

from market_dashboard.aperture.leadership import fingerprint
from market_dashboard.aperture.rules import ApertureRules

APERTURE_RULES_FINGERPRINT = '920a29facf60a0c5375d094fa669dc2ed402504f3e80ef256feb2ed1724b03e0'


@dataclass(frozen=True)
class DecisionThresholdsV1:
    established_composite: float = 60.
    rotation_composite: float = 40.
    rotation_strength: float = 80.
    rotation_delta: float = 15.
    group_rank_fraction: float = .80
    short_promotion_enabled: bool = False
    pilot_divisor: int = 3


POLICY = DecisionThresholdsV1()
RULES_FINGERPRINT = fingerprint({
    'engine':'decision-risk-v1', 'formula':'decision-risk-formulas-v1',
    'thresholds_version':'decision-risk-thresholds-v1', 'thresholds':asdict(POLICY),
    'aperture_rules':APERTURE_RULES_FINGERPRINT,
    'extension':'sign*(close-sma50)/wilder_atr14; configured bands; inclusive 0..4.8',
    'events':'T-close; T BMO/during past; T AMC/unknown distance0; inclusive 0..5; explicit fresh complete coverage T..T+5',
    'freshness':'caller-attested fresh_for_session=T; both timestamps<=completed_at; absent attestation unknown; no invented TTL',
    'replacement':'explicit source/id links; replaced records excluded; missing replacement unknown; no proximity inference',
    'strength':'three-valued branches; established OR rotation; true branch suffices independently',
    'group':'one explicit subindustry; valid rank<=ceil(.8*eligible_count); themes nonvoting',
    'ladder':'all gates evaluated; long watch then trade then act; short decline watch only',
    'sizing':'equity*.0025*regime; floor(risk/distance); floor(shares/3); capital min; explicit caller stop only',
    'timing':'completed T inputs; exact next exchange action session; no I/O',
})


def validate_rules(rules: ApertureRules):
    if rules.logical_fingerprint != APERTURE_RULES_FINGERPRINT:
        raise ValueError('Decision V1 requires the unchanged aperture-rules-v1 configuration')
    return rules
