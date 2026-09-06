"""Bounded reference staging. No network client is constructed by offline modes."""
from __future__ import annotations

from datetime import date, datetime, UTC
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

import httpx
import duckdb
import pandas as pd
import yaml

from .reference_errors import capture_reference_error
from .security_master import SecurityMasterStore, SecurityMasterClassifier, SECURITY_MASTER_COLUMNS
from .deepvue_taxonomy import _clean_classification
from .security_identity import IDENTITY_VERSION, COMPATIBILITY_VERSION, case_collision_groups, publication_blockers, compatibility_projection

ROOT = Path(__file__).resolve().parents[3]
ENDPOINT = 'https://api.massive.com/v3/reference/tickers'
JULY = '2026-07-26'
FIELDS = ('ticker name market locale primary_exchange type active currency_name currency_symbol cik composite_figi share_class_figi last_updated_utc list_date delisted_utc').split()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + '\n')
    temporary.replace(path)


def read_json(path):
    return json.loads(Path(path).read_text())


def fingerprint(frame, *, logical=True):
    columns = sorted(c for c in frame.columns if not logical or c not in {'ingested_at', 'last_updated_utc'})
    def scalar(value):
        if pd.isna(value):
            return None
        if isinstance(value, (datetime, date, pd.Timestamp)):
            return pd.Timestamp(value).isoformat()
        if hasattr(value, 'item'):
            return value.item()
        return value
    rows = [[scalar(v) for v in row] for row in frame[columns].itertuples(index=False, name=None)]
    encoded = sorted(json.dumps(r, separators=(',', ':'), ensure_ascii=True) for r in rows)
    return hashlib.sha256(json.dumps([columns, encoded], separators=(',', ':')).encode()).hexdigest()


def safe_path(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError('Symlink paths are prohibited')
    return path.resolve()


def plan(workspace, snapshot_date, max_requests, max_records, database, parquet_directory, taxonomy, themes, crosswalk):
    date.fromisoformat(snapshot_date)
    if snapshot_date <= JULY or max_requests < 1 or max_records < 1000:
        raise ValueError('Require date after protected snapshot, positive requests and at least 1000 records')
    workspace, database, parquet_directory = map(safe_path, (workspace, database, parquet_directory))
    for protected in (ROOT, database.parent, parquet_directory):
        if workspace == protected or workspace in protected.parents or protected in workspace.parents:
            raise ValueError('Workspace must be separate from repository and production storage')
    inputs = {k: safe_path(v) for k, v in dict(taxonomy=taxonomy, themes=themes, crosswalk=crosswalk).items()}
    inputs.update(config=ROOT/'config/settings.yaml', disposition=ROOT/'config/deepvue_identity_disposition_v1.json', july=parquet_directory/f'snapshot_date={JULY}/security_master.parquet')
    hashes = {k: digest(v) for k,v in inputs.items()}
    if not database.is_file():
        raise ValueError('Existing master database required')
    with duckdb.connect(str(database), read_only=True) as connection:
        baseline = connection.execute('SELECT * FROM security_master WHERE snapshot_date=?', [JULY]).df()
    if not len(baseline) or fingerprint(baseline, logical=False) != fingerprint(pd.read_parquet(inputs['july']), logical=False):
        raise ValueError('July DuckDB/Parquet mismatch')
    result = dict(version=1, snapshot_date=snapshot_date, max_requests=max_requests, max_records=max_records,
                  maximum_pages=min(max_requests, max_records // 1000), estimated_pages_from_july=(len(baseline)+999)//1000,
                  endpoint_path='/v3/reference/tickers', parameters=dict(market='stocks', locale='us', active='true', date=snapshot_date, limit=1000, sort='ticker', order='asc'),
                  database=str(database), parquet_directory=str(parquet_directory), input_hashes=hashes,
                  protected_fingerprint=fingerprint(pd.read_parquet(inputs['july']), logical=False))
    if workspace.exists() and any(workspace.iterdir()):
        if (workspace/'plan.json').exists() and read_json(workspace/'plan.json') == result:
            load_plan(workspace)
            return result
        raise ValueError('Workspace is not empty or plan differs')
    workspace.mkdir(parents=True, exist_ok=True)
    for key, source in inputs.items():
        (workspace/key).write_bytes(source.read_bytes())
    write_json(workspace/'plan.json', result)
    return result


def load_plan(workspace):
    workspace = safe_path(workspace)
    if any(path.is_symlink() or path.is_dir() for path in workspace.iterdir()):
        raise ValueError('Workspace must contain only regular staging files')
    p = read_json(workspace/'plan.json')
    if set(p['input_hashes']) != {'taxonomy', 'themes', 'crosswalk', 'config', 'disposition', 'july'}:
        raise ValueError('Invalid plan inputs')
    for key, expected in p['input_hashes'].items():
        if digest(safe_path(workspace/key)) != expected:
            raise ValueError('Input artifact changed')
    for target in (ROOT, safe_path(p['database']).parent, safe_path(p['parquet_directory'])):
        if target == workspace or target in workspace.parents or workspace in target.parents:
            raise ValueError('Unsafe workspace')
    if p['parameters'] != dict(market='stocks', locale='us', active='true', date=p['snapshot_date'], limit=1000, sort='ticker', order='asc'):
        raise ValueError('Invalid reference scope')
    if p['snapshot_date'] <= JULY or p['max_requests'] < 1 or p['max_records'] < 1000:
        raise ValueError('Invalid bounds')
    date.fromisoformat(p['snapshot_date'])
    return p


def records_valid(records):
    if not isinstance(records, list) or not records or len(records) > 1000:
        raise ValueError('Invalid page size/schema')
    for row in records:
        if not isinstance(row, dict):
            raise ValueError('Invalid record schema')
        for key in ('ticker', 'name', 'market', 'locale', 'type', 'primary_exchange'):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError('Missing required reference field')
        if row['ticker'] != row['ticker'].strip() or row['active'] is not True or row['market'] != 'stocks' or row['locale'] != 'us':
            raise ValueError('Incorrect reference scope')
        for key in FIELDS:
            if key != 'active' and row.get(key) is not None and not isinstance(row[key], str):
                raise ValueError('Invalid reference field type')
        if row.get('last_updated_utc'):
            pd.Timestamp(row['last_updated_utc'])
        for key in ('list_date', 'delisted_utc'):
            if row.get(key):
                pd.Timestamp(row[key])


def next_valid(url, parameters):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.netloc != 'api.massive.com' or parsed.path != '/v3/reference/tickers' or parsed.fragment or parsed.username:
        raise ValueError('Unsafe pagination URL')
    for key, values in parse_qs(parsed.query).items():
        if key not in {'cursor', *parameters} or (key in parameters and values != [str(parameters[key])]):
            raise ValueError('Pagination scope changed')


def fetch(workspace, api_key, *, client=None):
    w = safe_path(workspace)
    p = load_plan(w)
    if (w/'fetch.json').exists():
        raise ValueError('Fetch evidence already exists; use a new workspace')
    state = dict(plan_hash=digest(w/'plan.json'), started_at=datetime.now(UTC).isoformat(), requests=[], pages=[], raw_rows=0, complete=False, termination='started')
    owned = client is None
    client = client or httpx.Client(transport=httpx.HTTPTransport(retries=0), timeout=30, follow_redirects=False)
    url, seen = ENDPOINT, set()
    try:
        while True:
            if len(state['requests']) >= p['max_requests'] or state['raw_rows'] + 1000 > p['max_records']:
                state['termination'] = 'budget_cap'
                break
            next_valid(url, p['parameters'])
            parsed = httpx.URL(url)
            key = (str(parsed.copy_with(query=None)), tuple(sorted(parsed.params.multi_items())))
            if key in seen:
                raise ValueError('Repeated pagination URL')
            seen.add(key)
            attempt = dict(method='GET', endpoint_path=p['endpoint_path'], captured_at=datetime.now(UTC).isoformat(), outcome='started')
            state['requests'].append(attempt)
            write_json(w/'fetch.json', state)
            try:
                response = client.get(url, params=p['parameters'] if len(seen) == 1 else None, headers={'Authorization': f'Bearer {api_key}'}, follow_redirects=False)
            except httpx.TransportError:
                attempt['outcome'] = 'transport_failure'
                state['termination'] = 'transport_failure'
                break
            attempt['http_status'] = response.status_code
            if response.status_code != 200:
                attempt.update(outcome='http_failure', diagnostic=capture_reference_error(response, None))
                state['termination'] = 'http_failure'
                break
            attempt['outcome'] = 'received'
            payload = response.json()
            if not isinstance(payload, dict) or payload.get('status') != 'OK':
                raise ValueError('Invalid provider response schema')
            records = payload.get('results')
            records_valid(records)
            if any(r.get('snapshot_date', p['snapshot_date']) != p['snapshot_date'] for r in records):
                raise ValueError('Incorrect snapshot date')
            if any(r.get('list_date') and pd.Timestamp(r['list_date']).date() > date.fromisoformat(p['snapshot_date']) for r in records):
                raise ValueError('Listing after requested snapshot')
            records = [{k:r.get(k) for k in FIELDS} for r in records]
            filename = f'page-{len(state["pages"])+1:05d}.json'
            write_json(w/filename, dict(snapshot_date=p['snapshot_date'], results=records))
            state['pages'].append(dict(file=filename, sha256=digest(w/filename), rows=len(records), request=len(state['requests']), next_url_present=bool(payload.get('next_url'))))
            state['raw_rows'] += len(records)
            attempt['outcome'] = 'validated_page'
            url = payload.get('next_url')
            if url is None or url == '':
                state.update(complete=True, termination='normal')
                break
            if not isinstance(url, str):
                raise ValueError('Invalid pagination schema')
    except (ValueError, KeyError, TypeError, OverflowError):
        state['termination'] = 'schema_or_pagination_failure'
    finally:
        write_json(w/'fetch.json', state)
        if owned:
            client.close()
    return state


def validate(workspace):
    w = safe_path(workspace)
    p = load_plan(w)
    s = read_json(w/'fetch.json')
    if s['plan_hash'] != digest(w/'plan.json') or s['complete'] is not True or s['termination'] != 'normal':
        raise ValueError('Incomplete or changed fetch')
    if not 0 < len(s['requests']) <= p['max_requests'] or len(s['requests']) != len(s['pages']):
        raise ValueError('Request limit/outcome violation')
    rows = []
    for i, page in enumerate(s['pages'], 1):
        if page['next_url_present'] != (i < len(s['pages'])):
            raise ValueError('Pagination did not terminate normally')
        if page['file'] != f'page-{i:05d}.json' or page['request'] != i or digest(safe_path(w/page['file'])) != page['sha256']:
            raise ValueError('Page evidence mismatch')
        if len(rows) + 1000 > p['max_records'] or s['requests'][i-1]['outcome'] != 'validated_page' or s['requests'][i-1]['http_status'] != 200:
            raise ValueError('Page budget/outcome violation')
        content = read_json(w/page['file'])
        if content['snapshot_date'] != p['snapshot_date']:
            raise ValueError('Incorrect snapshot date')
        records_valid(content['results'])
        if any(r.get('list_date') and pd.Timestamp(r['list_date']).date() > date.fromisoformat(p['snapshot_date']) for r in content['results']):
            raise ValueError('Listing after requested snapshot')
        if len(content['results']) != page['rows']:
            raise ValueError('Page count mismatch')
        rows.extend(content['results'])
    if not rows or len(rows) != s['raw_rows'] or len(rows) > p['max_records']:
        raise ValueError('Empty snapshot or record limit/count violation')
    unique = {}
    for row in rows:
        if row['ticker'] in unique:
            raise ValueError('Duplicate exact snapshot/ticker key')
        unique[row['ticker']] = row
    if [r['ticker'] for r in rows] != sorted(r['ticker'] for r in rows):
        raise ValueError('Ticker order is not ascending')
    config = yaml.safe_load((w/'config').read_text())['security_master']
    frame = SecurityMasterStore()._build_frame(list(unique.values()), date.fromisoformat(p['snapshot_date']), SecurityMasterClassifier(config))
    frame['ingested_at'] = pd.Timestamp(s['started_at']).tz_convert(None)
    if list(frame.columns) != SECURITY_MASTER_COLUMNS:
        raise ValueError('Master schema changed')
    report = dict(request_count=len(s['requests']), page_count=len(s['pages']), raw_rows=len(rows), distinct_tickers=len(frame), duplicate_rows=len(rows)-len(frame), logical_fingerprint=fingerprint(frame), figis={})
    report['snapshot_date'] = p['snapshot_date']
    report['identity_version'] = IDENTITY_VERSION
    report['case_insensitive_collision_groups'] = case_collision_groups(frame.ticker)
    mixed = frame[frame.ticker.ne(frame.ticker.str.upper())]
    report['mixed_case_rows'] = len(mixed)
    report['mixed_case_type_counts'] = mixed.security_type.value_counts().to_dict()
    report['publication_blockers'] = publication_blockers(frame.ticker)
    report['publication_eligible'] = not report['publication_blockers']
    compatible, projection = compatibility_projection(frame)
    projection.to_csv(w/'compatibility-projection.csv', index=False)
    report['compatibility'] = dict(version=COMPATIBILITY_VERSION, reference_rows=len(frame), compatible_rows=len(compatible), ambiguous_automatic_conversions=int(projection.reason.str.startswith('AMBIGUOUS').sum()), reasons=projection.reason.value_counts().to_dict(), exclusions_by_type_and_reason=projection[projection.reason.ne('COMPATIBLE')].groupby(['security_type','reason']).size().reset_index(name='rows').to_dict('records'))
    report['active_counts'] = {'true': int(frame.active.sum()), 'false': int((~frame.active).sum())}
    july = pd.read_parquet(w/'july')
    report['july_tickers_absent'] = sorted(set(july.ticker) - set(frame.ticker))
    report['tickers_absent_from_july'] = sorted(set(frame.ticker) - set(july.ticker))
    for field in ('composite_figi', 'share_class_figi'):
        valid = frame[frame[field].notna() & frame[field].ne('')]
        groups = valid.groupby(field)['ticker'].agg(list)
        report['figis'][field] = dict(missing=int(len(frame)-len(valid)), collisions={k:v for k,v in groups.items() if len(v)>1})
    for field in ('security_type', 'primary_exchange', 'normalized_category', 'normalized_exchange', 'exclusion_reason'):
        report[field] = frame[field].fillna('NONE').value_counts().to_dict()
    disposition = read_json(w/'disposition')
    exclusions = {symbol:category for category in ('NON_SECURITY_MARKET_SERIES','DEEPVUE_BREADTH_INDICATOR') for symbol in disposition[category]}
    tickers = set(frame.ticker)
    aliases = {}
    for ticker in tickers:
        aliases.setdefault(ticker.casefold(), []).append(ticker)
    outputs = ['compatibility-projection.csv']
    for source in ('taxonomy', 'themes'):
        source_frame = pd.read_csv(w/source, dtype=str, keep_default_na=False)
        column = next((c for c in ('Symbol', 'ticker', 'symbol') if c in source_frame), None)
        if column is None:
            raise ValueError('Missing source symbol column')
        source_frame['source_symbol'] = source_frame[column]
        source_frame['identity_status'] = [exclusions.get(t, 'EMPTY_SOURCE_RECORD' if not t else 'MATCHED' if t in tickers else 'UNMATCHED') for t in source_frame[column]]
        source_frame['included_in_security_denominator'] = ~source_frame[column].isin(exclusions) & source_frame[column].ne('')
        source_frame['mapping_applied'] = False
        # Diagnostic only: neither alias candidates nor their cardinality can
        # change the exact-match status or provide a persistence key.
        source_frame['case_alias_review'] = [
            'NOT_APPLICABLE' if t in tickers or t in exclusions or not t else
            'AMBIGUOUS_UNRESOLVED' if len(aliases.get(t.casefold(), [])) > 1 else
            'CASE_VARIANT_UNAPPLIED' if aliases.get(t.casefold()) else 'NONE'
            for t in source_frame[column]
        ]
        if source == 'taxonomy':
            classified = source_frame['Sub-Industry'].map(_clean_classification).notna()
            source_frame['classification_status'] = classified.map({True:'CLASSIFIED', False:'UNCLASSIFIED'})
            candidates = source_frame.included_in_security_denominator
            report['taxonomy_denominators'] = dict(total_rows=len(source_frame), non_security_rows=int(source_frame[column].isin(exclusions).sum()), security_candidates=int(candidates.sum()), classified_security_candidates=int((candidates & classified).sum()), unclassified_security_candidates=int((candidates & ~classified).sum()))
        filename = f'{source}-reconciliation.csv'
        source_frame.to_csv(w/filename, index=False)
        outputs.append(filename)
        report[source] = source_frame.identity_status.value_counts().to_dict()
    cross = pd.read_csv(w/'crosswalk', dtype=str, keep_default_na=False)
    if len(cross) != 23 or cross.current_ticker.nunique() != 23 or cross.july_master_ticker.nunique() != 23:
        raise ValueError('Expected separate 23 unique crosswalk proposals')
    if dict(zip(cross.current_ticker, cross.july_master_ticker)) != disposition['proposed_crosswalk']:
        raise ValueError('Crosswalk must preserve exact versioned proposals')
    for symbol, target in [('NXH','BBBY'),('SEPQ','TUGN'),('STLN','TOI'),('VMRK','EQR')]:
        if cross.loc[cross.current_ticker.eq(symbol), 'july_master_ticker'].tolist() != [target]:
            raise ValueError('Crosswalk proposal changed')
    cross['mapping_applied'] = False
    evidence = []
    for proposal in cross.to_dict('records'):
        composite = proposal.get('current_composite_figi')
        share = proposal.get('current_share_class_figi')
        matches = july[july.composite_figi.eq(composite) & july.share_class_figi.eq(share)] if composite and share else july.iloc[:0]
        evidence.append('EXACT_DUAL_FIGI_MATCH' if len(matches) == 1 and matches.iloc[0].ticker == proposal['july_master_ticker'] else 'UNRESOLVED_EVIDENCE')
    cross['local_july_evidence'] = evidence
    cross['proposal_status'] = ['QUARANTINED_'+disposition['quarantined_proposals'][t]['reason'] if t in disposition['quarantined_proposals'] else 'PROPOSED' for t in cross.current_ticker]
    cross.to_csv(w/'unapplied-crosswalk.csv', index=False)
    outputs.append('unapplied-crosswalk.csv')
    frame.to_parquet(w/'security_master.parquet', index=False)
    write_json(w/'report.json', report)
    files = ['plan.json','fetch.json','security_master.parquet','report.json', *outputs, *p['input_hashes'], *[page['file'] for page in s['pages']]]
    implementation = ['security_master_refresh.py', 'security_master.py', 'security_identity.py']
    receipt = dict(version=2, identity_version=IDENTITY_VERSION, compatibility_version=COMPATIBILITY_VERSION, implementation_hashes={name:digest(Path(__file__).parent/name) for name in implementation}, publication_blockers=report['publication_blockers'], logical_fingerprint=fingerprint(frame), exact_fingerprint=fingerprint(frame, logical=False), hashes={f:digest(w/f) for f in files})
    write_json(w/'validation.json', receipt)
    return report


def validated_artifact(workspace):
    w = safe_path(workspace)
    p = load_plan(w)
    receipt = read_json(w/'validation.json')
    required = {'plan.json','fetch.json','security_master.parquet','report.json', *p['input_hashes']}
    if not required.issubset(receipt['hashes']):
        raise ValueError('Incomplete validation receipt')
    for filename, expected in receipt['hashes'].items():
        if Path(filename).name != filename or digest(safe_path(w/filename)) != expected:
            raise ValueError('Validated artifact changed')
    frame = pd.read_parquet(w/'security_master.parquet')
    if fingerprint(frame) != receipt['logical_fingerprint'] or fingerprint(frame, logical=False) != receipt['exact_fingerprint']:
        raise ValueError('Validated content changed')
    return p, receipt, frame
