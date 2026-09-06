import builtins
from dataclasses import FrozenInstanceError
import io
import json
import os
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal
from pydantic import ValidationError
import pytest

from tests.regime_fixtures import *
from tests.leadership_fixtures import bars
from tests.test_structure_engine import row as structure_row
from market_dashboard.aperture.structure import evaluate_structure
from market_dashboard.aperture.structure_contracts import StructureSourceV1
from market_dashboard.aperture.regime import evaluate_regime, breadth_sleeve
from market_dashboard.aperture.regime_adapters import regime_input_from_bars, spot_identity, research_universe
from market_dashboard.aperture.regime_policy import THRESHOLDS, RULES_FINGERPRINT
from market_dashboard.features.regime_features import sma, simple_return

CONFIG=json.loads((Path(__file__).resolve().parents[1]/'config/deepvue_identity_disposition_v1.json').read_text())


def frames():
    return bars(('SPY','QQQ','IWM','RSP','QQQE','S0')), pd.DataFrame(
        {'series_id':['VIX']*300,'date':CALENDAR,'close':[18.]*300})


def adapt(equities=None,spot=None,**changes):
    b,v=frames()
    args=dict(session=CALENDAR[252],calendar=CALENDAR,source=SOURCE,universe=universe(('S0',)),volatility_identity=IDENTITY)
    return regime_input_from_bars(b if equities is None else equities,v if spot is None else spot,**{**args,**changes})


def test_exact_windows_and_endpoints():
    b,v=frames(); out=adapt(b,v)
    spy=next(i for i in out.indexes if i.symbol=='SPY')
    closes=dict(zip(CALENDAR,b.loc[b.ticker=='SPY','close']))
    assert spy.close==closes[CALENDAR[252]]
    assert spy.sma20==pytest.approx(sum(closes[d] for d in CALENDAR[233:253])/20)
    assert spy.sma50==pytest.approx(sum(closes[d] for d in CALENDAR[203:253])/50)
    assert spy.sma20_5_ago==pytest.approx(sum(closes[d] for d in CALENDAR[228:248])/20)
    assert next(i.R21 for i in out.style if i.symbol=='SPY')==closes[CALENDAR[252]]/closes[CALENDAR[231]]-1
    assert out.volatility.sma20==pytest.approx(18.)


def test_missing_interior_does_not_shift_return_but_blocks_sma():
    b,v=frames(); expected=adapt(b,v)
    b=b.loc[~((b.ticker=='SPY') & (b.date==CALENDAR[240]))]
    out=adapt(b,v)
    assert out.style==expected.style
    assert out.indexes[0].sma20 is None and out.indexes[0].sma50 is None
    assert out.indexes[0].close==expected.indexes[0].close
    b=b.loc[~((b.ticker=='SPY') & (b.date==CALENDAR[231]))]
    assert next(i.R21 for i in adapt(b,v).style if i.symbol=='SPY') is None


def test_future_mutation_and_calendar_extension_do_not_change_t():
    b,v=frames(); expected=adapt(b,v)
    b.loc[b.date>CALENDAR[252],'close']=1e99
    v.loc[v.date>CALENDAR[252],'close']=1e99
    assert adapt(b,v)==expected
    assert adapt(b,v,calendar=CALENDAR[:254])==expected
    assert evaluate_regime(adapt(b,v),calendar=CALENDAR)==evaluate_regime(expected,calendar=CALENDAR)


@pytest.mark.parametrize('which',['equity','spot'])
@pytest.mark.parametrize('defect',['duplicate','noncalendar','intraday','timezone','identity','source','basis'])
def test_reject_ambiguous_bar_inputs(which,defect):
    b,v=frames(); data=b if which=='equity' else v
    if defect=='duplicate': data=pd.concat([data,data.iloc[:1]],ignore_index=True)
    elif defect=='noncalendar': data.loc[0,'date']=pd.Timestamp('2024-01-06')
    elif defect=='intraday': data['date']=pd.to_datetime(data.date)+pd.Timedelta(hours=1)
    elif defect=='timezone': data['date']=pd.to_datetime(data.date,utc=True)
    elif defect=='identity': data.loc[0,'ticker' if which=='equity' else 'series_id']='Spy'
    elif defect=='source': data['dataset_id']='wrong'
    else: data['price_basis' if which=='equity' else 'basis']='unadjusted'
    with pytest.raises(ValueError):
        adapt(data,v) if which=='equity' else adapt(b,data)


@pytest.mark.parametrize('value',[None,0.,-1.,float('inf'),float('nan')])
def test_nonpositive_nonfinite_bar_values_are_missing(value):
    b,v=frames(); b.loc[(b.ticker=='SPY') & (b.date==CALENDAR[252]),'close']=value
    v.loc[v.date==CALENDAR[252],'close']=value
    out=adapt(b,v)
    assert out.indexes[0].close is None and out.volatility.close is None


@pytest.mark.parametrize('calendar',[(),CALENDAR[::-1],CALENDAR+(CALENDAR[-1],),CALENDAR[:252]])
def test_reject_calendar_inconsistency(calendar):
    with pytest.raises(ValueError): adapt(calendar=calendar)


def test_spot_identity_uses_exact_versioned_nonsecurity_disposition():
    identity=spot_identity(disposition_config=CONFIG,source_symbol='VIX',data_vendor='synthetic',dataset_id='spot-v1',
        equivalence_evidence='Synthetic VIX spot volatility points')
    assert identity==IDENTITY and identity.canonical_series=='$VIX'
    with pytest.raises(ValueError):
        spot_identity(disposition_config={**CONFIG,'version':'other'},source_symbol='VIX',data_vendor='x',dataset_id='x',equivalence_evidence='x')
    with pytest.raises(ValidationError):
        PriceFeaturesV1(symbol='$VIX',close=18,sma20=18,sma50=18)


@pytest.mark.parametrize('field,value',[('session_date',CALENDAR[253]),('calendar_fingerprint','0'*64),
    ('rules_fingerprint','0'*64),('source',SOURCE.model_copy(update={'dataset_id':'other'})),
    ('universe',universe(('S0',)))])
def test_leadership_context_exact_alignment(field,value):
    with pytest.raises(ValidationError): regime_input(leadership=leader().model_copy(update={field:value}))


@pytest.mark.parametrize('part',['symbols','groups','overlap','nested_source','nested_date','nested_universe','future_membership'])
def test_reject_duplicate_or_misaligned_nested_context(part):
    c=leader()
    if part in ('symbols','groups'):
        c=c.model_copy(update={part:getattr(c,part)+(getattr(c,part)[0],)})
    elif part=='overlap':
        c=c.model_copy(update={'groups':(c.groups[0].model_copy(update={'members':c.groups[1].members}),)+c.groups[1:]})
    elif part.startswith('nested'):
        e=c.symbols[0]
        if part=='nested_universe': e=e.model_copy(update={'universe':universe(('S0',),index=1).provenance})
        else:
            field='source' if part=='nested_source' else 'session_date'
            value=SOURCE.model_copy(update={'dataset_id':'other'}) if field=='source' else CALENDAR[251]
            e=e.model_copy(update={'inputs':e.inputs.model_copy(update={field:value})})
        c=c.model_copy(update={'symbols':(e,)+c.symbols[1:]})
    else:
        c=c.model_copy(update={'groups':(c.groups[0].model_copy(update={'membership':universe(index=253).provenance}),)+c.groups[1:]})
    with pytest.raises(ValidationError): regime_input(leadership=c)


def structure_evidence():
    source=StructureSourceV1(**SOURCE.model_dump(exclude={'schema_version','calendar_id'}))
    return evaluate_structure([structure_row(symbol='S0',session_date=CALENDAR[252],source=source)])[0]


def test_structure_breadth_separate_valid_denominator_and_error_missing():
    e=structure_evidence()
    context=StructureBreadthContextV1(session_date=CALENDAR[252],source=SOURCE,universe=universe(tuple(f'S{i}' for i in range(100))),
        evidence=(e.model_copy(update={'state':'UPTREND'}),))
    inp=regime_input(structure=context)
    out=breadth_sleeve(inp.breadth,context)
    assert out.constructive_structure.valid_count==1 and out.constructive_structure.fraction==1
    assert out.constructive_structure.coverage==.01 and out.state==State.GREEN
    e=e.model_copy(update={'error':'MISSING_INPUT'})
    out=breadth_sleeve(inp.breadth,context.model_copy(update={'evidence':(e,)}))
    assert out.constructive_structure.valid_count==0 and out.constructive_structure.fraction is None


@pytest.mark.parametrize('defect',['date','source','universe','rules','duplicate','symbol'])
def test_structure_alignment(defect):
    e=structure_evidence()
    context=StructureBreadthContextV1(session_date=CALENDAR[252],source=SOURCE,universe=regime_input().universe,evidence=(e,))
    if defect in ('date','source','symbol'):
        key={'date':'session_date','source':'source','symbol':'symbol'}[defect]
        value={'date':CALENDAR[251],'source':e.inputs.source.model_copy(update={'dataset_id':'bad'}),'symbol':'OUTSIDE'}[defect]
        e=e.model_copy(update={'inputs':e.inputs.model_copy(update={key:value})})
    elif defect=='rules': e=e.model_copy(update={'rules_fingerprint':'0'*64})
    elif defect=='universe': context=context.model_copy(update={'universe':universe(('S0',))})
    context=context.model_copy(update={'evidence':(e,e) if defect=='duplicate' else (e,)})
    with pytest.raises(ValidationError): regime_input(structure=context)


@pytest.mark.parametrize('change',[{'indexes':()}, {'style':()}, {'breadth':()},
    {'universe':universe(tuple(f'S{i}' for i in range(100)),index=253)}, {'surprise':1}])
def test_input_membership_and_extra_fields(change):
    with pytest.raises(ValidationError): regime_input(**change)


@pytest.mark.parametrize('value',[float('nan'),float('inf'),-float('inf')])
def test_frozen_finite_schemas(value):
    with pytest.raises(ValidationError): PriceFeaturesV1(symbol='SPY',close=value,sma20=None,sma50=None)
    with pytest.raises(ValidationError): VolatilityInputV1(identity=IDENTITY,close=value,sma20=20,close_5_ago=None)
    with pytest.raises(ValidationError): StyleInputV1(symbol='SPY',R21=value)


def test_frozen_policy_schema_fingerprint_and_roundtrip():
    out=evaluate_regime(regime_input(),calendar=CALENDAR)
    assert RegimeOutputV1.model_validate_json(out.model_dump_json())==out
    with pytest.raises(ValidationError): out.state=State.RED
    with pytest.raises(ValidationError): out.inputs.volatility.close=100
    with pytest.raises(FrozenInstanceError): THRESHOLDS.vix_red=99
    assert out.rules_fingerprint==RULES_FINGERPRINT and len(RULES_FINGERPRINT)==64
    with pytest.raises(ValidationError): FractionV1(numerator=1,valid_count=0,population_count=100,fraction=None,coverage=0)
    with pytest.raises(ValidationError): SleeveV1(state=State.UNKNOWN,score=0,reasons=())
    with pytest.raises(ValidationError): RegimeMemoryV1(candidate=State.GREEN,candidate_streak=1)


def test_entire_adapter_and_engine_are_pure_without_file_access(monkeypatch):
    b,v=frames(); before_b=b.copy(deep=True); before_v=v.copy(deep=True)
    inp=regime_input(); serialized=inp.model_dump_json()
    def forbidden(*args,**kwargs): pytest.fail('Regime attempted filesystem access')
    with monkeypatch.context() as m:
        m.setattr(builtins,'open',forbidden); m.setattr(io,'open',forbidden); m.setattr(os,'open',forbidden)
        adapted=regime_input_from_bars(b,v,session=CALENDAR[252],calendar=CALENDAR,source=SOURCE,
            universe=universe(('S0',)),volatility_identity=IDENTITY)
        evaluate_regime(adapted,calendar=CALENDAR)
        evaluate_regime(inp,calendar=CALENDAR)
    assert inp.model_dump_json()==serialized
    assert_frame_equal(b,before_b); assert_frame_equal(v,before_v)


def test_extreme_finite_calculations_stay_finite_or_null():
    calendar=CALENDAR[:22]
    closes={('SPY',d):1e308 for d in calendar}
    assert sma(closes,'SPY',calendar,21,20)==pytest.approx(1e308)
    closes[('SPY',calendar[0])]=1e-308
    assert simple_return(closes,'SPY',calendar,21,21) is None
