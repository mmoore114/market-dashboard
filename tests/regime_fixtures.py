"""Synthetic regime evidence; no provider or production data."""
from functools import lru_cache

from tests.leadership_fixtures import (
    CALENDAR, SOURCE, universe, raw, membership, GroupType, forbid_leadership_network,
)
from market_dashboard.aperture.leadership import rank_strength, aggregate_groups, RULES_FINGERPRINT as LEADERSHIP_RULES
from market_dashboard.aperture.leadership_contracts import LeadershipOutputV1
from market_dashboard.aperture.regime import calendar_hash
from market_dashboard.aperture.regime_contracts import *

IDENTITY = SpotVolatilityIdentityV1(source_symbol='VIX',data_vendor='synthetic',dataset_id='spot-v1',
    equivalence_evidence='Synthetic VIX spot volatility points')


def price_rows(total=100, valid20=None, valid50=None, above20=None, above50=None):
    valid20 = total if valid20 is None else valid20
    valid50 = total if valid50 is None else valid50
    above20 = total if above20 is None else above20
    above50 = total if above50 is None else above50
    return tuple(PriceFeaturesV1(symbol=f'S{i}',close=100.,
        sma20=None if i>=valid20 else 99. if i<above20 else 101.,
        sma50=None if i>=valid50 else 99. if i<above50 else 101.) for i in range(total))


def index_input(symbol='SPY', vote=Vote.CONSTRUCTIVE):
    args = {Vote.CONSTRUCTIVE:(110.,105.,100.,104.), Vote.DEFENSIVE:(90.,95.,100.,96.),
            Vote.MIXED:(100.,100.,100.,100.), Vote.UNKNOWN:(None,100.,100.,100.)}[vote]
    return IndexInputV1(symbol=symbol,close=args[0],sma20=args[1],sma50=args[2],sma20_5_ago=args[3])


def style_inputs(spy=.1,rsp=.1,qqq=.1,qqqe=.1):
    return tuple(StyleInputV1(symbol=s,R21=v) for s,v in zip(('SPY','RSP','QQQ','QQQE'),(spy,rsp,qqq,qqqe)))


@lru_cache(maxsize=32)
def leader(index=252,total=100):
    u=universe(tuple(f'S{i}' for i in range(total)))
    es=rank_strength(tuple(raw(s,index=index) for s in u.symbols),u,CALENDAR[index])
    es=tuple(e.model_copy(update={'RS_comp':80.,'RS_rotation':90.,'rotation_delta':10.}) for e in es)
    ms=tuple(membership(u.symbols[j:j+20],f'G{j//20}',GroupType.SUB_INDUSTRY) for j in range(0,total,20))
    merged=ms[0].model_copy(update={'group_ids':tuple(g for m in ms for g in m.group_ids),
        'members':tuple(v for m in ms for v in m.members)})
    gs=aggregate_groups(es,(merged,),CALENDAR[index])
    return LeadershipOutputV1(rules_fingerprint=LEADERSHIP_RULES,session_date=CALENDAR[index],source=SOURCE,
        universe=u,calendar_fingerprint=calendar_hash(CALENDAR,CALENDAR[index]),symbols=es,groups=gs)


def regime_input(index=252, total=100, **changes):
    args=dict(session_date=CALENDAR[index],source=SOURCE,calendar_fingerprint=calendar_hash(CALENDAR,CALENDAR[index]),
        universe=universe(tuple(f'S{i}' for i in range(total))),
        indexes=tuple(index_input(s) for s in ('SPY','QQQ','IWM')),breadth=price_rows(total),style=style_inputs(),
        volatility=VolatilityInputV1(identity=IDENTITY,close=18.,sma20=18.,close_5_ago=18.),leadership=leader(index,total))
    return RegimeInputV1(**{**args,**changes})
