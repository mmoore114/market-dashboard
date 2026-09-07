from copy import deepcopy
from datetime import date
from pathlib import Path
import socket

import duckdb
import httpx
import pandas as pd
import pytest
import yaml

from market_dashboard.data import security_master_refresh as refresh
from market_dashboard.data.security_master import SecurityMasterStore, SecurityMasterClassifier
from market_dashboard.data.security_master_publication import publish, compare


def row(ticker='AAA', **kwargs):
    return dict(ticker=ticker, name='Example Corporation', market='stocks', locale='us', type='CS', primary_exchange='XNAS', active=True, composite_figi='C'+ticker, share_class_figi='S'+ticker, **kwargs)


@pytest.fixture
def environment(tmp_path):
    production = tmp_path/'production'
    store = SecurityMasterStore(duckdb_path=production/'master.duckdb', parquet_directory=production/'parquet')
    config = yaml.safe_load((refresh.ROOT/'config/settings.yaml').read_text())['security_master']
    store.persist([row('OLD')], '2026-07-26', SecurityMasterClassifier(config))
    taxonomy = tmp_path/'taxonomy.csv'
    taxonomy.write_text('Symbol,Sub-Industry\nAAA,Software\n$SPX,\nS4B--USA,\nUNKNOWN,\n')
    themes = tmp_path/'themes.csv'
    themes.write_text('Theme,Symbol\nExample,AAA\nExample,STLN\n')
    crosswalk = tmp_path/'crosswalk.csv'
    pairs = list(refresh.read_json(refresh.ROOT/'config/deepvue_identity_disposition_v1.json')['proposed_crosswalk'].items())
    pd.DataFrame(pairs, columns=['current_ticker','july_master_ticker']).to_csv(crosswalk,index=False)
    args = dict(workspace=tmp_path/'stage', snapshot_date='2026-09-05', max_requests=3, max_records=3000, database=store.duckdb_path, parquet_directory=store.parquet_directory, taxonomy=taxonomy, themes=themes, crosswalk=crosswalk)
    return args


def offline(monkeypatch):
    calls = []
    def forbidden(*a, **k):
        calls.append(1)
        raise AssertionError('Network prohibited')
    monkeypatch.setattr(httpx.Client, 'send', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    return calls


def mock_fetch(args, pages):
    seen = []
    def handler(request):
        seen.append(request)
        response = pages[len(seen)-1]
        if isinstance(response, Exception):
            raise response
        if isinstance(response, httpx.Response):
            return response
        return httpx.Response(200,json=response)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        state = refresh.fetch(args['workspace'], 'TOP_SECRET_123', client=client)
    return state, seen


def ready(args):
    refresh.plan(**args)
    state, _ = mock_fetch(args, [dict(status='OK',results=[row()])])
    assert state['complete']
    return refresh.validate(args['workspace'])


def test_offline_plan_and_workspace_safety(environment, monkeypatch):
    calls = offline(monkeypatch)
    before = refresh.digest(environment['database'])
    p = refresh.plan(**environment)
    assert p['parameters'] == dict(market='stocks',locale='us',active='true',date='2026-09-05',limit=1000,sort='ticker',order='asc')
    assert refresh.plan(**environment) == p
    assert refresh.digest(environment['database']) == before
    assert calls == []
    with pytest.raises(ValueError):
        refresh.plan(**(environment | {'workspace':environment['database'].parent/'bad'}))
    with pytest.raises(ValueError):
        refresh.plan(**(environment | {'max_records':999}))


def test_validate_publish_offline_and_july_preserved(environment, monkeypatch):
    refresh.plan(**environment)
    mock_fetch(environment,[dict(status='OK',results=[row()])])
    calls = offline(monkeypatch)
    report = refresh.validate(environment['workspace'])
    assert report['taxonomy'] == {'MATCHED':1,'NON_SECURITY_MARKET_SERIES':1,'DEEPVUE_BREADTH_INDICATOR':1,'UNMATCHED':1}
    original = refresh.digest(environment['parquet_directory']/f'snapshot_date={refresh.JULY}/security_master.parquet')
    result = publish(environment['workspace'],confirm=True)
    assert result['action'] == 'published'
    assert publish(environment['workspace'],confirm=True)['action'] == 'no_op'
    assert refresh.digest(environment['parquet_directory']/f'snapshot_date={refresh.JULY}/security_master.parquet') == original
    assert calls == []
    with duckdb.connect(str(environment['database']),read_only=True) as con:
        assert con.execute('select count(*) from security_master').fetchone()[0] == 2
        assert con.execute("select count(*) from information_schema.tables where table_name like '%exposure%'").fetchone()[0] == 0
        compare(con,'2026-09-05',environment['parquet_directory']/'snapshot_date=2026-09-05/security_master.parquet')
    with pytest.raises(ValueError):
        publish(environment['workspace'])


@pytest.mark.parametrize('requests,records,expected',[(1,3000,1),(3,1000,1),(3,1999,1)])
def test_caps_preserve_pages(environment,requests,records,expected):
    environment.update(max_requests=requests,max_records=records)
    refresh.plan(**environment)
    rows = [row(f'A{i:04d}') for i in range(1000)]
    state, seen = mock_fetch(environment,[dict(status='OK',results=rows,next_url=refresh.ENDPOINT+'?cursor=next')])
    assert len(seen)==expected and state['termination']=='budget_cap' and not state['complete']
    assert state['raw_rows']==1000 and len(state['pages'])==1
    with pytest.raises(ValueError):
        refresh.validate(environment['workspace'])


def test_normal_pagination_and_request_scope(environment):
    refresh.plan(**environment)
    state, seen = mock_fetch(environment,[dict(status='OK',results=[row('AAA')],next_url=refresh.ENDPOINT+'?cursor=next'),dict(status='OK',results=[row('BBB')])])
    assert state['complete'] and len(seen)==2
    assert seen[0].url.params['limit']=='1000'
    assert seen[0].url.params['active']=='true'
    assert seen[1].url.params['cursor']=='next'
    assert refresh.validate(environment['workspace'])['distinct_tickers']==2
    assert 'cursor' not in (environment['workspace']/'fetch.json').read_text()


@pytest.mark.parametrize('url',[refresh.ENDPOINT, 'https://evil.example/v3/reference/tickers?cursor=x',refresh.ENDPOINT+'?market=crypto','https://api.massive.com/v2/aggs',refresh.ENDPOINT+'?apiKey=secret'])
def test_unsafe_or_repeated_pagination(environment,url):
    refresh.plan(**environment)
    state, seen = mock_fetch(environment,[dict(status='OK',results=[row()],next_url=url)])
    assert len(seen)==1 and not state['complete']
    assert state['termination']=='schema_or_pagination_failure'
    assert len(state['pages'])==1


@pytest.mark.parametrize('payload',[{}, {'status':'OK','results':[]}, {'status':'OK','results':[dict(ticker='')]}, {'status':'OK','results':[row(snapshot_date='2026-01-01')]}, {'status':'OK','results':[row()]*1001}])
def test_first_page_failure(environment,payload):
    refresh.plan(**environment)
    state, seen=mock_fetch(environment,[payload])
    assert len(seen)==1 and not state['complete'] and state['pages']==[]


@pytest.mark.parametrize('status',[302,400,429,500])
def test_sanitized_bulk_error_no_retry(environment,status):
    refresh.plan(**environment)
    response=httpx.Response(status,json={'error':'apiKey=TOP_SECRET_123 https://api.massive.com/v3/reference/tickers?cursor=private','code':'ERR'},headers={'location':'https://evil.example'})
    state,seen=mock_fetch(environment,[response])
    assert len(seen)==1 and len(state['requests'])==1
    text=(environment['workspace']/'fetch.json').read_text()
    assert 'TOP_SECRET_123' not in text and '?cursor' not in text and 'private' not in text
    assert state['requests'][0]['diagnostic']['endpoint_path']=='/v3/reference/tickers'


def test_transport_no_retry(environment):
    refresh.plan(**environment)
    state,seen=mock_fetch(environment,[httpx.ConnectError('secret URL should not be recorded')])
    assert len(seen)==1 and state['termination']=='transport_failure'
    assert 'secret URL' not in (environment['workspace']/'fetch.json').read_text()


def test_conflicting_duplicates(environment):
    refresh.plan(**environment)
    other=row();other['name']='Different'
    mock_fetch(environment,[dict(status='OK',results=[row(),other])])
    with pytest.raises(ValueError,match='Duplicate exact'):
        refresh.validate(environment['workspace'])


def test_figi_collisions_and_missing(environment):
    refresh.plan(**environment)
    other=row('BBB');other['composite_figi']='CAAA';other['share_class_figi']=None
    mock_fetch(environment,[dict(status='OK',results=[row(),other])])
    report=refresh.validate(environment['workspace'])
    assert report['figis']['composite_figi']['collisions']=={'CAAA':['AAA','BBB']}
    assert report['figis']['share_class_figi']['missing']==1


def test_fingerprints_deterministic(environment):
    ready(environment)
    w=environment['workspace']
    receipt=refresh.read_json(w/'validation.json')
    refresh.validate(w)
    assert refresh.read_json(w/'validation.json')==receipt
    frame=pd.read_parquet(w/'security_master.parquet')
    original=refresh.fingerprint(frame)
    frame['ingested_at']=pd.Timestamp('2020-01-01')
    assert refresh.fingerprint(frame)==original and len(original)==64
    assert refresh.fingerprint(frame,logical=False)!=receipt['exact_fingerprint']


@pytest.mark.parametrize('stage',['staged','committed','renamed'])
def test_interrupted_publication_recovery(environment,stage,monkeypatch):
    ready(environment)
    calls=offline(monkeypatch)
    def interrupt(current):
        if current==stage:
            raise RuntimeError('simulated interruption')
    with pytest.raises(RuntimeError):
        publish(environment['workspace'],confirm=True,checkpoint=interrupt)
    result=publish(environment['workspace'],confirm=True)
    assert result['action']==('published' if stage=='staged' else 'recovered')
    assert calls==[]


def test_changed_same_date_revision(environment):
    ready(environment)
    initial=publish(environment['workspace'],confirm=True)
    environment['workspace']=environment['workspace'].with_name('stage2')
    refresh.plan(**environment)
    mock_fetch(environment,[dict(status='OK',results=[row('BBB')])])
    refresh.validate(environment['workspace'])
    with pytest.raises(ValueError,match='revision'):
        publish(environment['workspace'],confirm=True)
    assert publish(environment['workspace'],confirm=True,authorize_revision=initial['logical_fingerprint'])['action']=='published'


def test_receipt_tampering_and_july_guard(environment):
    ready(environment)
    w=environment['workspace']
    (w/'report.json').write_text('{}')
    with pytest.raises(ValueError,match='changed'):
        publish(w,confirm=True)
    refresh.validate(w)
    july=environment['parquet_directory']/f'snapshot_date={refresh.JULY}/security_master.parquet'
    july.write_bytes(july.read_bytes()+b'changed')
    with pytest.raises(ValueError,match='July'):
        publish(w,confirm=True)


@pytest.mark.parametrize('field,value',[('ticker',' '),('active',False),('market','crypto'),('locale','gb'),('type',None)])
def test_bad_scope_and_schema(environment,field,value):
    refresh.plan(**environment)
    record=row();record[field]=value
    state,_=mock_fetch(environment,[dict(status='OK',results=[record])])
    assert not state['complete']


def test_exact_dispositions_and_crosswalk(environment):
    ready(environment)
    d=refresh.read_json(refresh.ROOT/'config/deepvue_identity_disposition_v1.json')
    assert len(d['NON_SECURITY_MARKET_SERIES'])==7 and len(d['DEEPVUE_BREADTH_INDICATOR'])==22
    cross=pd.read_csv(environment['workspace']/'unapplied-crosswalk.csv')
    assert not cross.mapping_applied.any()
    assert cross.proposal_status.value_counts().to_dict()=={'PROPOSED':21,'QUARANTINED_EXCHANGE_REVIEW':1,'QUARANTINED_CIK_REVIEW':1}
    assert cross.loc[cross.current_ticker.eq('SEPQ'),'july_master_ticker'].tolist()==['TUGN']


@pytest.mark.parametrize('change',[{'complete':False},{'termination':'budget_cap'},{'raw_rows':0}])
def test_offline_validation_rejects_bad_provenance(environment,change,monkeypatch):
    ready(environment)
    w=environment['workspace']
    state=refresh.read_json(w/'fetch.json')
    state.update(change)
    refresh.write_json(w/'fetch.json',state)
    calls=offline(monkeypatch)
    with pytest.raises(ValueError):
        refresh.validate(w)
    assert calls==[]


def test_validation_enforces_request_and_record_limits(environment):
    ready(environment)
    w=environment['workspace']
    state=refresh.read_json(w/'fetch.json')
    state['requests']*=4
    refresh.write_json(w/'fetch.json',state)
    with pytest.raises(ValueError,match='Request'):
        refresh.validate(w)


def test_exact_duplicates_are_fatal(environment):
    refresh.plan(**environment)
    mock_fetch(environment,[dict(status='OK',results=[row(),row()])])
    with pytest.raises(ValueError, match='Duplicate exact'):
        refresh.validate(environment['workspace'])


def test_failure_after_page_preserves_evidence(environment):
    refresh.plan(**environment)
    state,seen=mock_fetch(environment,[dict(status='OK',results=[row()],next_url=refresh.ENDPOINT+'?cursor=next'),httpx.Response(400,text='bad request')])
    assert len(seen)==2 and len(state['pages'])==1 and not state['complete']
    assert (environment['workspace']/state['pages'][0]['file']).exists()
    with pytest.raises(ValueError):
        refresh.fetch(environment['workspace'],'unused')


def test_changed_crosswalk_and_unknown_symbol_not_excluded(environment):
    source=environment['taxonomy']
    source.write_text(source.read_text()+'NH-FUTURE,\n')
    ready(environment)
    report=pd.read_csv(environment['workspace']/'taxonomy-reconciliation.csv')
    assert report.loc[report.source_symbol.eq('NH-FUTURE'),'identity_status'].tolist()==['UNMATCHED']
    cross=pd.read_csv(environment['crosswalk'])
    cross.loc[cross.current_ticker.eq('SEPQ'),'july_master_ticker']='TUNG'
    cross.to_csv(environment['crosswalk'],index=False)
    environment['workspace']=environment['workspace'].with_name('other')
    refresh.plan(**environment)
    mock_fetch(environment,[dict(status='OK',results=[row()])])
    with pytest.raises(ValueError,match='proposals'):
        refresh.validate(environment['workspace'])


def test_unknown_codes_are_reported(environment):
    refresh.plan(**environment)
    record=row();record.update(type='FUTURE_CODE',primary_exchange='XXXX')
    mock_fetch(environment,[dict(status='OK',results=[record])])
    report=refresh.validate(environment['workspace'])
    assert report['normalized_category']=={'Review Needed':1}
    assert report['normalized_exchange']=={'Review Needed':1}
    assert report['exclusion_reason']=={'unknown_security_type':1}


def test_symlink_workspace_rejected(environment,tmp_path):
    target=tmp_path/'real'
    target.mkdir()
    environment['workspace'].symlink_to(target,target_is_directory=True)
    with pytest.raises(ValueError,match='Symlink'):
        refresh.plan(**environment)


def test_publication_exact_field_comparison_detects_drift(environment):
    ready(environment)
    publish(environment['workspace'],confirm=True)
    with duckdb.connect(str(environment['database'])) as con:
        con.execute("UPDATE security_master SET name='changed' WHERE snapshot_date='2026-09-05'")
        with pytest.raises(ValueError,match='field mismatch'):
            compare(con,'2026-09-05',environment['parquet_directory']/'snapshot_date=2026-09-05/security_master.parquet')


def test_exact_case_identity_revalidation_and_reader_gate(environment, monkeypatch):
    environment['taxonomy'].write_text('Symbol,Sub-Industry\nTPC,Industry\nBCPC,Industry\ntPc,\nbcpc,\n')
    refresh.plan(**environment)
    records = [row(t) for t in ['BCPC','BCpC','TPC','TpC']]
    for record in records:
        if record['ticker'] in {'BCpC','TpC'}:
            record['type']='PFD'
    mock_fetch(environment,[dict(status='OK',results=records)])
    w=environment['workspace']
    before={p.name:refresh.digest(p) for p in w.glob('page-*.json')}
    july=environment['parquet_directory']/f'snapshot_date={refresh.JULY}/security_master.parquet'
    original=refresh.digest(july)
    calls=offline(monkeypatch)
    report=refresh.validate(w)
    assert report['distinct_tickers']==4 and report['duplicate_rows']==0
    assert report['mixed_case_type_counts']=={'PFD':2}
    assert report['case_insensitive_collision_groups']=={'bcpc':['BCPC','BCpC'],'tpc':['TPC','TpC']}
    frame=pd.read_parquet(w/'security_master.parquet')
    assert frame.ticker.tolist()==['BCPC','BCpC','TPC','TpC']
    assert len({refresh.fingerprint(frame[frame.ticker.eq(t)]) for t in frame.ticker})==4
    # Hold all other fields constant to prove that ticker case itself is hashed.
    single=frame.iloc[[0]].copy()
    first=refresh.fingerprint(single)
    single['ticker']='BCpC'
    assert refresh.fingerprint(single)!=first
    rec=pd.read_csv(w/'taxonomy-reconciliation.csv',keep_default_na=False)
    assert rec.identity_status.tolist()==['MATCHED','MATCHED','UNMATCHED','UNMATCHED']
    assert rec.case_alias_review.tolist()==['NOT_APPLICABLE','NOT_APPLICABLE','AMBIGUOUS_UNRESOLVED','AMBIGUOUS_UNRESOLVED']
    assert not rec.mapping_applied.any()
    assert not report['publication_blockers'] and report['publication_eligible']
    assert refresh.digest(july)==original
    assert {p.name:refresh.digest(p) for p in w.glob('page-*.json')}==before
    assert calls==[]


def test_exact_case_duckdb_parquet_keys(environment):
    # Temporary schema-level capability test, not publication via either CLI.
    config=yaml.safe_load((refresh.ROOT/'config/settings.yaml').read_text())['security_master']
    store=SecurityMasterStore(duckdb_path=environment['database'],parquet_directory=environment['parquet_directory'])
    classifier=SecurityMasterClassifier(config)
    rows=[row(t) for t in ['TPC','TpC','BCPC','BCpC']]
    frame=store._build_frame(rows,date(2026,9,5),classifier)
    store._write_duckdb(frame,date(2026,9,5))
    path=store.parquet_path(date(2026,9,5))
    store._write_parquet(frame,path)
    with duckdb.connect(str(environment['database']),read_only=True) as con:
        assert len(compare(con,'2026-09-05',path))==4
        assert con.execute("SELECT count(*) FROM security_master WHERE ticker='TPC'").fetchone()[0]==1
    with pytest.raises(ValueError,match='Duplicate exact'):
        store._build_frame([row(),row()],date(2026,9,5),classifier)


@pytest.mark.parametrize('ticker',[' TpC','TpC ','',' '])
def test_provider_identity_never_silently_trimmed(environment,ticker):
    config=yaml.safe_load((refresh.ROOT/'config/settings.yaml').read_text())['security_master']
    with pytest.raises(ValueError,match='exact string'):
        SecurityMasterStore()._build_frame([row(ticker)],date(2026,9,5),SecurityMasterClassifier(config))


def test_unsafe_reader_gate_blocks_both_publication_paths(environment,monkeypatch):
    from market_dashboard.data import security_identity
    ready(environment)
    monkeypatch.setattr(security_identity,'UNSAFE_REFERENCE_READERS',('unmigrated test reader',))
    calls=offline(monkeypatch)
    before=refresh.digest(environment['database'])
    with pytest.raises(ValueError,match='compatibility'):
        publish(environment['workspace'],confirm=True)
    config=yaml.safe_load((refresh.ROOT/'config/settings.yaml').read_text())['security_master']
    store=SecurityMasterStore(duckdb_path=environment['database'],parquet_directory=environment['parquet_directory'])
    with pytest.raises(ValueError,match='compatibility'):
        store.persist([row()],'2026-09-05',SecurityMasterClassifier(config))
    assert refresh.digest(environment['database'])==before and calls==[]
