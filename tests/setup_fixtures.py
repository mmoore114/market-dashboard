"""Synthetic typed inputs only; no provider data or storage."""
from datetime import date, timedelta

from market_dashboard.aperture.setup_contracts import *
from market_dashboard.aperture.structure_contracts import StructureInputV1, StructureEvidenceV1, StructureState
from market_dashboard.aperture.structure import evaluate_structure

SOURCE = StructureSourceV1(data_vendor='synthetic',dataset_id='setup-fixture-v1',
    price_basis='split_adjusted',dividend_treatment='none',volume_convention='synthetic matching units')


def box(n=20, high=104., low=100., last=102.):
    closes=(last,)+tuple(low+.1 if i%2 else high-.1 for i in range(1,n-1))+(last,)
    return PriceWindowV1(highs=(high,)*n,lows=(low,)*n,closes=closes)


def coil():
    return PriceWindowV1(highs=(104.,)*10+(103.,)*5+(102.5,)*5,
        lows=(96.,)*10+(97.,)*5+(99.5,)*5,closes=(100.,)*20)


def row(index=250, state=StructureState.UPTREND, **changes):
    values=dict(symbol='XYZ',session_date=date(2026,1,1)+timedelta(days=index-250),session_index=index,
        source=SOURCE,corporate_action_qa=CorporateActionQA.CLEAR,corporate_action_evidence='synthetic no action',
        open=102.,high=104.,low=100.,close=102.,previous_close=102.,
        atr5=1.5,atr14=2.,atr20=2.,previous_atr14=2.,volume=100.,prior_volume20=(100.,)*20,
        mean_volume5=100.,mean_volume20=100.,s20=0.,
        averages=tuple(MovingAverageV1(kind=k,value=100.,previous=100.,prior_distances=(1.,)*6)
            for k in (ReferenceKind.EMA10,ReferenceKind.SMA20,ReferenceKind.SMA50)),
        window20=box(),window30=box(30))
    values.update(changes)
    values['averages']=tuple(MovingAverageV1.model_validate(ma) for ma in values['averages'])
    if 'structure' not in changes and state is not None:
        sf=StructureInputV1(symbol=values['symbol'],session_date=values['session_date'],source=values['source'],
            prior_sessions=index,close=values['close'],previous_close=values['previous_close'],
            atr14=values['atr14'],previous_atr14=values['previous_atr14'],
            **{ma.kind.lower():ma.value for ma in values['averages']},sma20_10_ago=100.,sma50_20_ago=100.,
            above20_15=10,above50_15=10,below20_15=5,below50_15=5)
        evidence=evaluate_structure([sf])[0]
        values['structure']=StructureEvidenceV1.model_validate(evidence.model_dump() | {'state':state,'error':None})
    return SetupInputV1(**values)


def resequence(rows):
    result=[]
    for offset,r in enumerate(rows):
        data=r.model_dump(exclude={'structure','schema_version','feature_version','session_date','session_index'})
        state=r.structure.state if r.structure else None
        result.append(row(index=250+offset,state=state,**data))
    return result

# Imported explicitly by each setup test module; all its tests run offline.
import socket
import httpx
import pytest


@pytest.fixture(autouse=True)
def forbid_setup_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Setup tests prohibit all network requests')
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(socket,'create_connection',forbidden)
    monkeypatch.setattr(httpx.Client,'request',forbidden)
    monkeypatch.setattr(httpx.AsyncClient,'request',forbidden)
