import pytest
from pydantic import ValidationError

from tests.leadership_fixtures import *
from market_dashboard.aperture.leadership import percentiles, rank_strength, RULES_FINGERPRINT, POLICY


@pytest.mark.parametrize('values,expected,count',[
    ({'A':1.,'B':2.,'C':3.},{'A':0.,'B':50.,'C':100.},3),
    ({'A':1.,'B':1.,'C':3.},{'A':25.,'B':25.,'C':100.},3),
    ({'A':1.,'B':1.},{'A':50.,'B':50.},2),
    ({'A':None,'B':2.},{'A':None,'B':50.},1),
    ({'A':None},{'A':None},0),({}, {},0),
])
def test_percentiles(values,expected,count):
    assert percentiles(values)==(expected,count)


def test_independent_horizons_weights_and_residuals():
    a=raw('A',{5:3,21:2,63:1,126:2,252:3},residual=3)
    b=raw('B',{5:2,21:3,63:2,126:3,252:1},residual=None)
    c=raw('C',{5:1,21:1,63:3,126:1,252:2},residual=1)
    x,y,z=rank_strength((a,b,c),universe(('A','B','C')),CALENDAR[252])
    assert x.RS_comp==35 and x.RS_rotation==70 and x.rotation_delta==35
    assert y.RS_comp==55 and y.RS_rotation==80 and y.rotation_delta==25
    assert z.RS_comp==60 and z.RS_rotation==0 and z.rotation_delta==-60
    assert [e.residual_percentile for e in (x,y,z)]==[100,None,0]
    assert all(e.residual_valid_count==2 for e in (x,y,z))
    assert all(c.valid_count==3 and c.universe_snapshot_id=='test' and c.universe_policy_version=='research-test-v1' for e in (x,y,z) for c in e.components)


@pytest.mark.parametrize('missing',HORIZONS)
def test_missing_component_never_renormalizes(missing):
    a=raw(values={h:None if h==missing else 1. for h in HORIZONS})
    result=rank_strength((a,),universe(('A',)),CALENDAR[252])[0]
    assert result.RS_comp==(None if missing in (63,126,252) else 50.)
    assert result.RS_rotation==(None if missing in (5,21) else 50.)
    assert result.rotation_delta is None
    assert f'MISSING_R{missing}' in result.reason_codes
    component=next(c for c in result.components if c.horizon==missing)
    assert component.valid_count==0 and component.percentile is None


@pytest.mark.parametrize('short_value',[None,-100.,0.,100.])
def test_short_term_inputs_never_change_slow_composite(short_value):
    a=raw(values={h:short_value if h in (5,21) else 1. for h in HORIZONS})
    b=raw('B')
    result=rank_strength((a,b),universe(),CALENDAR[252])
    assert [s.RS_comp for s in result]==[0.,100.]


def test_optional_context_never_changes_rs():
    base=rank_strength((raw(),),universe(('A',)),CALENDAR[252])[0]
    context=StrengthContextV1(structure_state='DECLINE',legacy=LegacyStrengthContextV1(return_20d_percent=-99),
        setups=(SetupStrengthContextV1(family=list(Family)[0],status='TRIGGERED'),))
    enriched=rank_strength((raw(context=context),),universe(('A',)),CALENDAR[252])[0]
    for field in ('components','RS_comp','RS_rotation','rotation_delta','residual_percentile'):
        assert getattr(base,field)==getattr(enriched,field)


@pytest.mark.parametrize('problem',['duplicate','outside','missing','session','source','expired','future'])
def test_cross_section_requires_exact_dated_universe(problem):
    inputs=(raw(),raw('B'))
    u=universe()
    if problem=='duplicate': inputs=(raw(),raw())
    elif problem=='outside': inputs=(raw(),raw('C'))
    elif problem=='missing': inputs=(raw(),)
    elif problem=='session': inputs=(raw(index=251),raw('B'))
    elif problem=='source': inputs=(raw().model_copy(update={'source':SOURCE.model_copy(update={'dataset_id':'other'})}),raw('B'))
    elif problem=='expired': u=universe(end=251)
    else: u=universe(index=253)
    with pytest.raises(ValueError): rank_strength(inputs,u,CALENDAR[252])


@pytest.mark.parametrize('field,value',[
    ('value',float('nan')),('value',float('inf')),('unexpected',1),('horizon',20)])
def test_finite_extra_forbidden_schemas(field,value):
    with pytest.raises(ValidationError): RawReturnV1.model_validate({'horizon':5,'value':1.,field:value})


def test_frozen_contracts_and_versioned_policy():
    with pytest.raises(ValidationError): raw().symbol='Z'
    with pytest.raises(Exception): POLICY.minimum_group_members=2
    assert len(RULES_FINGERPRINT)==64
    with pytest.raises(ValidationError): ResearchUniverseV1(provenance=provenance(),policy_version='v1',symbols=('a',))
    with pytest.raises(ValidationError): ResearchUniverseV1(provenance=provenance(),policy_version='v1',symbols=('A','A'))
    with pytest.raises(ValidationError): raw().model_validate(raw().model_dump()|{'returns':[{'horizon':5,'value':1}]*5})


@pytest.mark.parametrize('value',[float('nan'),float('inf'),-float('inf')])
def test_rank_helper_rejects_nonfinite(value):
    with pytest.raises(ValueError): percentiles({'A':value})
