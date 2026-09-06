import pandas as pd
import pytest

from market_dashboard.data.security_identity import (
    ReferenceTicker, MarketDataSymbol, CompatibilityBoundary,
    compatibility_projection, publication_blockers,
)
from market_dashboard.data.exposure_policy import ExposurePolicy


def test_types_and_explicit_conversion():
    reference=ReferenceTicker('ABC')
    assert reference != MarketDataSymbol('ABC')
    boundary=CompatibilityBoundary([reference, ReferenceTicker('ABpC')])
    assert boundary.convert(reference).symbol==MarketDataSymbol('ABC')
    assert boundary.convert(ReferenceTicker('ABpC')).symbol is None
    assert boundary.convert(ReferenceTicker('UNKNOWN')).reason=='REFERENCE_NOT_IN_SNAPSHOT'
    with pytest.raises(TypeError):
        boundary.convert('ABC')
    with pytest.raises(ValueError,match='uppercase'):
        MarketDataSymbol('ABpC')
    with pytest.raises(ValueError,match='Duplicate'):
        CompatibilityBoundary([reference,reference])


def test_13155_reference_rows_projection_counts_and_no_mutation():
    rows=[(f'SEC{i:05d}','CS') for i in range(12749)]
    rows += [(f'P{i:03d}p','PFD') for i in range(352)]
    rows += [(f'S{i:03d}p','SP') for i in range(30)]
    rows += [(f'R{i:03d}r','RIGHT') for i in range(20)]
    rows += [('TPC','CS'),('TpC','PFD'),('BCPC','CS'),('BCpC','PFD')]
    frame=pd.DataFrame(rows,columns=['ticker','security_type'])
    before=frame.copy(deep=True)
    compatible,audit=compatibility_projection(frame)
    pd.testing.assert_frame_equal(frame,before)
    assert len(frame)==len(audit)==13155
    assert len(compatible)==12751
    assert audit.reason.value_counts().to_dict()=={'COMPATIBLE':12751,'MIXED_CASE_REFERENCE_ONLY':404}
    assert audit.loc[audit.reason.ne('COMPATIBLE'),'market_data_symbol'].isna().all()
    assert {'TPC','BCPC'} <= set(compatible.ticker)
    assert not {'TpC','BCpC'} & set(compatible.ticker)
    assert not publication_blockers(frame.ticker)
    assert not publication_blockers(['ABC','ABpC'])


def test_exposure_boundary_does_not_normalize_reference_identities():
    frame=pd.DataFrame([
        ['TPC','A','CS','Common Stock'],['TpC','B','PFD','Preferred Share'],
        ['ABC','C','CS','Common Stock'],['ABpC','D','PFD','Preferred Share'],
    ],columns=['ticker','name','security_type','normalized_category'])
    policy=ExposurePolicy({'policy_version':'test-boundary-v1'})
    result=policy.classify_snapshot(frame,'2026-09-05')
    assert result.ticker.tolist()==['ABC','TPC']
    assert len(result.attrs['identity_projection'])==4
    with pytest.raises(ValueError,match='uppercase'):
        policy.classify_record(frame.iloc[1].to_dict(),pd.Timestamp('2026-09-05').date(),set())


def test_projection_requires_one_snapshot():
    with pytest.raises(ValueError,match='one dated'):
        compatibility_projection(pd.DataFrame({'ticker':['A','B'],'snapshot_date':['2026-01-01','2026-02-01']}))


def test_legacy_master_cli_does_not_publish_exposure(monkeypatch,capsys):
    from argparse import Namespace
    from scripts import ingest_security_master as cli
    from market_dashboard.data.exposure_policy import ExposureClassificationStore
    from unittest.mock import Mock
    monkeypatch.setattr(cli,'parse_args',lambda:Namespace(snapshot_date='2026-09-05',reclassify_existing=True))
    monkeypatch.setattr(cli.SecurityMasterStore,'reclassify_snapshot',lambda *a,**k:dict(snapshot_date='2026-09-05',rows_fetched=1,unique_tickers=1,rows_written_to_parquet=1,rows_written_to_duckdb=1,candidate_tickers=1,parquet_path='synthetic'))
    forbidden=Mock(side_effect=AssertionError('Exposure publication prohibited'))
    monkeypatch.setattr(ExposureClassificationStore,'persist',forbidden)
    assert cli.main()==0
    assert forbidden.call_count==0
    assert 'exposure publication: not performed (disabled; separate workflow required)' in capsys.readouterr().out


@pytest.mark.parametrize('upper,mixed,nonexact',[('TPC','TpC','tPc'),('BCPC','BCpC','bcpc')])
def test_exact_precedence_and_prohibited_reverse_fallback(upper,mixed,nonexact):
    boundary=CompatibilityBoundary([ReferenceTicker(upper),ReferenceTicker(mixed)])
    assert boundary.convert(ReferenceTicker(upper)).symbol==MarketDataSymbol(upper)
    assert boundary.convert(ReferenceTicker(mixed)).reason=='MIXED_CASE_REFERENCE_ONLY'
    assert boundary.convert(ReferenceTicker(mixed)).symbol is None
    assert boundary.resolve_reference(MarketDataSymbol(upper)).reference==ReferenceTicker(upper)
    assert boundary.resolve_reference(mixed).reference==ReferenceTicker(mixed)
    ambiguous=boundary.resolve_reference(nonexact)
    assert ambiguous.reference is None and ambiguous.reason=='AMBIGUOUS_NO_EXACT_IDENTITY'
    assert set(ambiguous.diagnostic_candidates)=={upper,mixed}
    assert len(boundary.ambiguous)==1


def test_nonexact_reverse_is_ambiguous_even_with_one_or_zero_candidates():
    boundary=CompatibilityBoundary([ReferenceTicker('ABC')])
    for requested in ['abc','UNKNOWN']:
        result=boundary.resolve_reference(requested)
        assert result.reference is None and result.reason=='AMBIGUOUS_NO_EXACT_IDENTITY'
