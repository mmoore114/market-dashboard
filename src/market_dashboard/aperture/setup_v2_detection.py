"""Word Setup V2 predicates. No policy votes; missing observations stay explicit."""

import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from types import MappingProxyType

from market_dashboard.aperture.setup_contracts import (
    DetectionV1,
    GeometryV1,
)
from market_dashboard.aperture.setup_contracts import (
    Direction as D,
)
from market_dashboard.aperture.setup_contracts import (
    Family as F,
)
from market_dashboard.aperture.setup_contracts import (
    ReferenceKind as K,
)
from market_dashboard.aperture.setup_detection import (
    average,
    common_error,
    ep_detection,
    metrics,
    rules,
)
from market_dashboard.aperture.structure_contracts import StructureState as S
from market_dashboard.aperture.structure_v2 import SOURCE_SHA256


@dataclass(frozen=True)
class SetupThresholdsV2:
    closing_ratio: float = 0.75
    tr_compression: float = 0.80
    dry_volume: float = 0.80
    range_depth: float = 6.0
    range_pct: float = 0.25
    efficiency: float = 0.50
    drift: float = 0.50
    near: float = 0.50
    trigger: float = 0.10
    failure: float = 0.25
    contraction_failure: float = 0.50
    geometry_shift: float = 1.0
    contraction_ceased: int = 2
    terminal_retention: int = 20
    shared_pivot: float = 0.15
    pullback_away: float = 1.0
    pullback_forming: float = 1.50
    pullback_near: float = 0.75
    pullback_trigger_low: float = -0.50
    pullback_trigger_high: float = 0.25
    pullback_failure: float = 0.75
    pullback_failure_days: int = 2


P = SetupThresholdsV2()
EXPIRY = MappingProxyType({F.CONTRACTION: 40, F.RANGE: 60, F.TREND_PULLBACK: 10})
OBSERVATION = MappingProxyType({F.EP: 5, F.CONTRACTION: 5, F.RANGE: 5})
FAILURE_WINDOW = MappingProxyType({F.EP: 5, F.CONTRACTION: 5, F.RANGE: 3})
RULES_FINGERPRINT = sha256(
    json.dumps(
        {
            "engine": "setup-engine-v2",
            "features": "setup-features-v2",
            "thresholds": "setup-thresholds-v2",
            "source": SOURCE_SHA256,
            "values": asdict(P),
            "expiry": dict(EXPIRY),
            "observation": dict(OBSERVATION),
            "failure_windows": dict(FAILURE_WINDOW),
            "semantics": "word-alignment-v2;range20;closing-dispersion;strict-trend-pullback;"
            "failure-first;prior-session-reference;trigger-session-ATR-frozen;age-strict-greater;"
            "cessation-two-sessions;monotonic-near;corrected-replay-required;version-scoped-identity;"
            "EP-v1-detection-and-quarantine;EP-event-boundary;pullback-prior-five",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
).hexdigest()


def volume_evidence(row):
    a, b = row.median_volume5, row.median_volume20
    if a is None or b is None or b <= 0 or a < 0:
        return None, ("VOLUME_UNAVAILABLE",), ()
    ratio = a / b
    return ratio, ("VOLUME_DRYUP",) if ratio <= P.dry_volume else (), ()


def contraction_detection(row, direction):
    error = common_error(row)
    if error is None and (row.window20 is None or row.tr5 is None or row.tr20 is None):
        error = "missing_contraction_inputs"
    if error is None and row.tr20 <= 0:
        error = "nonpositive_tr"
    if error:
        return DetectionV1(
            family=F.CONTRACTION, direction=direction, geometry=None, error=error
        )
    w = row.window20
    cr = {n: (max(w.closes[-n:]) - min(w.closes[-n:])) / row.close for n in (5, 10, 20)}
    r10 = cr[10] / cr[20] if cr[20] > 0 else None
    r5 = cr[5] / cr[10] if cr[10] > 0 else None
    lower, upper = sorted(w.lows[-10:])[1], sorted(w.highs[-10:])[-2]
    ratio, flags, contradictions = volume_evidence(row)
    if lower >= upper:
        return DetectionV1(
            family=F.CONTRACTION,
            direction=direction,
            geometry=None,
            error="degenerate_geometry",
        )
    return DetectionV1(
        family=F.CONTRACTION,
        direction=direction,
        geometry=GeometryV1(
            reference_as_of_session=row.session_date,
            reference_kind=K.PIVOT_HIGH if direction == D.LONG else K.PIVOT_LOW,
            reference_price=upper if direction == D.LONG else lower,
            reference_atr=row.atr14,
            lower=lower,
            upper=upper,
            window=10,
        ),
        rules=rules(
            CR20_POSITIVE=cr[20] > 0,
            CLOSING_10_20=r10 is not None and r10 <= P.closing_ratio,
            CLOSING_5_10=r5 is not None and r5 <= P.closing_ratio,
            TR_COMPRESSION=row.tr5 / row.tr20 <= P.tr_compression,
        ),
        measurements=metrics(
            CR20=cr[20],
            CR10=cr[10],
            CR5=cr[5],
            R10_20=r10,
            R5_10=r5,
            TRCompression=row.tr5 / row.tr20,
            VolumeDryRatio=ratio,
        ),
        flags=flags,
        contradictions=contradictions,
    )


def range_detection(row, direction):
    error = common_error(row)
    if error is None and (
        row.window20 is None or row.median_atr20 is None or row.word_s20 is None
    ):
        error = "missing_range_inputs"
    if error is None and row.median_atr20 <= 0:
        error = "nonpositive_range_atr"
    if error:
        return DetectionV1(
            family=F.RANGE, direction=direction, geometry=None, error=error
        )
    w = row.window20
    upper, lower = sorted(w.highs)[-2], sorted(w.lows)[1]
    if upper <= lower:
        return DetectionV1(
            family=F.RANGE,
            direction=direction,
            geometry=None,
            error="degenerate_geometry",
        )
    depth = upper - lower
    depth_atr, depth_pct = depth / row.median_atr20, depth / ((upper + lower) / 2)
    efficiency, drift = abs(w.closes[-1] - w.closes[0]) / depth, abs(row.word_s20)
    ratio, flags, contradictions = volume_evidence(row)
    return DetectionV1(
        family=F.RANGE,
        direction=direction,
        geometry=GeometryV1(
            reference_as_of_session=row.session_date,
            reference_kind=K.RANGE_HIGH if direction == D.LONG else K.RANGE_LOW,
            reference_price=upper if direction == D.LONG else lower,
            reference_atr=row.atr14,
            lower=lower,
            upper=upper,
            window=20,
        ),
        rules=rules(
            DEPTH_ATR=depth_atr <= P.range_depth,
            DEPTH_PCT=depth_pct <= P.range_pct,
            EFFICIENCY=efficiency <= P.efficiency,
            SMA20_DRIFT=drift <= P.drift,
        ),
        measurements=metrics(
            RangeDepthATR=depth_atr,
            RangeDepthPct=depth_pct,
            Efficiency20=efficiency,
            SMA20Drift=drift,
            VolumeDryRatio=ratio,
        ),
        flags=flags,
        contradictions=contradictions,
    )


def structure_allows(row, direction, kind=None):
    return row.structure is not None and row.structure.state == (
        S.UPTREND if direction == D.LONG else S.DECLINE
    )


def in_zone(row, direction, kind):
    ma = average(row, kind)
    if ma.value is None or row.close is None or not row.atr14 or row.atr14 <= 0:
        return False
    return (
        P.pullback_trigger_low
        <= direction.sign * (row.close - ma.value) / row.atr14
        <= P.pullback_forming
    )


def pullback_detection(row, direction, kind=None):
    error = common_error(row)
    if error is None and (row.structure is None or row.structure.state is None):
        error = "missing_structure"
    if error:
        return DetectionV1(
            family=F.TREND_PULLBACK, direction=direction, geometry=None, error=error
        )
    if kind is None:
        attempts = [
            pullback_detection(row, direction, k) for k in (K.EMA10, K.SMA20, K.SMA50)
        ]
        qualifying = [d for d in attempts if d.qualifies]
        if not qualifying:
            return attempts[0]
        selected = min(
            qualifying,
            key=lambda d: (
                abs(row.close - d.geometry.reference_price),
                str(d.geometry.reference_kind),
            ),
        )
        return selected.model_copy(
            update={
                "flags": selected.flags
                + tuple(
                    f"CANDIDATE_REFERENCE_{d.geometry.reference_kind}"
                    for d in qualifying
                )
            }
        )
    ma = average(row, kind)
    if ma.value is None or ma.prior_distances is None or ma.value <= 0:
        return DetectionV1(
            family=F.TREND_PULLBACK,
            direction=direction,
            geometry=None,
            error="missing_pullback_inputs",
        )
    distance = direction.sign * (row.close - ma.value) / row.atr14
    away = max(direction.sign * d for d in ma.prior_distances[-5:])
    ratio, flags, contradictions = volume_evidence(row)
    return DetectionV1(
        family=F.TREND_PULLBACK,
        direction=direction,
        geometry=GeometryV1(
            reference_as_of_session=row.session_date,
            reference_kind=kind,
            reference_price=ma.value,
            reference_atr=row.atr14,
            lower=ma.value,
            upper=ma.value,
            window=5,
        ),
        rules=rules(
            STRUCTURE=structure_allows(row, direction),
            AWAY=away >= P.pullback_away,
            NOW=in_zone(row, direction, kind),
        ),
        measurements=metrics(
            distance_atr=distance, away_atr=away, VolumeDryRatio=ratio
        ),
        flags=flags,
        contradictions=contradictions,
    )


def detect(row):
    return tuple(
        fn(row, direction)
        for fn in (
            ep_detection,
            contraction_detection,
            pullback_detection,
            range_detection,
        )
        for direction in D
    )
