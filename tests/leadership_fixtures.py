"""Synthetic leadership fixtures; no production datasets."""
from datetime import date
import socket

import httpx
import pandas as pd
import pytest

from market_dashboard.aperture.leadership_contracts import *

CALENDAR = tuple(pd.bdate_range('2024-01-02', periods=300).date)
SOURCE = StrengthSourceV1(data_vendor='synthetic',dataset_id='leadership-test-v1',price_basis='split_adjusted',
    dividend_treatment='excluded',volume_convention='split_adjusted',calendar_id='synthetic-session-calendar-v1')


def provenance(index=0, end=299, name='test', version='v1'):
    return DatedProvenanceV1(snapshot_id=name,version=version,source_as_of_date=CALENDAR[index],
        known_session=CALENDAR[index],effective_session=CALENDAR[index],valid_through=CALENDAR[end])


def universe(symbols=('A','B'), index=0, **kwargs):
    return ResearchUniverseV1(provenance=provenance(index,**kwargs),policy_version='research-test-v1',symbols=tuple(symbols))


def member(symbol, group='G'):
    return GroupMemberV1(group_id=group,source_symbol=symbol,market_data_symbol=symbol,identity_reason='COMPATIBLE')


def membership(symbols=('A','B'), group='G', kind=GroupType.THEME, index=0, **kwargs):
    return GroupMembershipV1(provenance=provenance(index,**kwargs),group_type=kind,group_ids=(group,),
        members=tuple(member(s,group) for s in symbols),identity_version='synthetic-exact-v1')


def raw(symbol='A', values=None, index=252, residual=0., context=None):
    values = values or {h:float(h) for h in HORIZONS}
    return StrengthInputV1(symbol=symbol,session_date=CALENDAR[index],source=SOURCE,
        returns=tuple(RawReturnV1(horizon=h,value=values.get(h)) for h in HORIZONS),
        residual=ResidualV1(beta_252_qqq=1.,overlap_count=252,benchmark_R63=.1,residual_R63_qqq=residual),
        distance_from_closing_high_63=0.,distance_from_closing_high_252=0.,context=context or StrengthContextV1())


def bars(symbols=('A','B','QQQ'), count=300):
    return pd.DataFrame([{'ticker':s,'date':d,'close':100.+i*(j+1)+((i%3)*.25)}
        for j,s in enumerate(symbols) for i,d in enumerate(CALENDAR[:count])])


@pytest.fixture(autouse=True)
def forbid_leadership_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Leadership calculation attempted network access')
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(socket,'create_connection',forbidden)
    monkeypatch.setattr(httpx.Client,'request',forbidden)
    monkeypatch.setattr(httpx.AsyncClient,'request',forbidden)
