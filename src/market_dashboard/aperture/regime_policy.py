"""Fixed opt-in hypothesis; existing aperture_rules_v1.yaml remains immutable."""
from dataclasses import asdict, dataclass
from market_dashboard.aperture.leadership import fingerprint


@dataclass(frozen=True)
class RegimeThresholdsV1:
    minimum_members: int = 100
    minimum_coverage: float = .60
    minimum_groups: int = 5
    index_votes: int = 2
    breadth_green20: float = .55
    breadth_green50: float = .50
    breadth_red20: float = .35
    breadth_red50: float = .40
    strong_threshold: float = 80.
    group_leading_threshold: float = 60.
    internals_green: tuple = (.20,.50,.35,.50)
    internals_red: tuple = (.10,.35,.20,.35)
    vix_green: float = 20.
    vix_red: float = 25.
    vix_green_ratio: float = 1.05
    vix_red_ratio: float = 1.15
    style_gap: float = -.03
    aggregate_votes: int = 3
    candidate_sessions: int = 2
    override_breadth20: float = .30
    override_vix: float = 30.


THRESHOLDS = RegimeThresholdsV1()
RULES_FINGERPRINT = fingerprint({
    'engine':'market-regime-v1','features':'market-regime-features-v1',
    'thresholds_version':'market-regime-thresholds-v1','thresholds':asdict(THRESHOLDS),
    'index':'C>MA20>MA50 and MA20>MA20[-5]; defensive C<MA50 and MA20<MA20[-5]',
    'breadth':'independent valid close/MA denominators; strict above; both count/coverage gates',
    'internals':'separate symbol denominators; common eligible subindustry comp/delta median denominator',
    'volatility':'red first; close>=25 or close>=1.15*MA20; green close<20 and close<=1.05*MA20',
    'style':'R21=C/C[-21]-1; green EW>0 and gaps>=-.03; red EW<=0 and gaps<-.03',
    'timing':'completed T; earliest supplied exchange T+1; unknown and gaps reset continuity',
    'hysteresis':'initialize yellow; 2 consecutive directional candidates; opposite via yellow resets streak',
    'override':'two observed defensive indexes and valid breadth20<.30 OR spot close>=30',
})
