"""Explicit staged refresh CLI. Only fetch constructs a network client."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from market_dashboard.data.security_master_refresh import plan, fetch, validate
from market_dashboard.data.security_master_publication import publish
from market_dashboard.data.storage import DUCKDB_PATH, PROCESSED_DIRECTORY


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    for mode in ('plan','fetch','validate','publish'):
        command = sub.add_parser(mode)
        command.add_argument('--workspace', type=Path, required=True)
        if mode == 'plan':
            command.add_argument('--snapshot-date', required=True)
            command.add_argument('--max-requests', type=int, required=True)
            command.add_argument('--max-records', type=int, required=True)
            command.add_argument('--database', type=Path, default=DUCKDB_PATH)
            command.add_argument('--parquet-directory', type=Path, default=PROCESSED_DIRECTORY/'security_master')
            for name in ('taxonomy','themes','crosswalk'):
                command.add_argument('--'+name, type=Path, required=True)
        if mode == 'publish':
            command.add_argument('--confirm-publication', action='store_true')
            command.add_argument('--authorize-revision', help='Exact existing logical fingerprint; separate revision authorization')
    args = vars(parser.parse_args(argv))
    mode = args.pop('mode')
    try:
        if mode == 'publish':
            args['confirm'] = args.pop('confirm_publication')
        if mode == 'fetch':
            from dotenv import load_dotenv
            load_dotenv()
            key = os.environ.get('MASSIVE_API_KEY')
            if not key:
                raise ValueError('Massive credential is not configured')
            args['api_key'] = key
        result = dict(plan=plan, fetch=fetch, validate=validate, publish=publish)[mode](**args)
        print(json.dumps(result, indent=2, default=str))
        return 0 if mode != 'fetch' or result['complete'] else 2
    except (ValueError, OSError, KeyError) as error:
        # Do not render exception text: parsing errors can contain raw provider input.
        print(json.dumps({'mode':mode, 'status':'rejected', 'error_type':type(error).__name__}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
