from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

import duckdb
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_dashboard.data.exposure_policy import (
    ExposureClassificationStore,
    load_exposure_policy,
)
from market_dashboard.data.storage import DUCKDB_PATH


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a versioned exposure classification from provider facts."
    )
    parser.add_argument("--snapshot-date", required=True)
    parser.add_argument(
        "--policy-config",
        default=None,
        help="Versioned policy file; defaults to swing_universe.exposure_policy_config.",
    )
    parser.add_argument(
        "--recover",
        action="store_true",
        help="Repair one incomplete snapshot/policy publication without rebuilding.",
    )
    parser.add_argument(
        "--policy-version",
        help="Policy identity to recover; required with --recover.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    snapshot = date.fromisoformat(args.snapshot_date)
    with (PROJECT_ROOT / "config" / "settings.yaml").open(
        "r", encoding="utf-8"
    ) as handle:
        settings = yaml.safe_load(handle)
    policy_path = PROJECT_ROOT / (
        args.policy_config
        or settings["swing_universe"]["exposure_policy_config"]
    )
    store = ExposureClassificationStore(
        duckdb_path=DUCKDB_PATH,
        parquet_directory=(
            PROJECT_ROOT
            / settings["swing_universe"]["exposure_classification_directory"]
        ),
    )
    if args.recover:
        if not args.policy_version:
            print("fatal error: --policy-version is required with --recover")
            return 1
        try:
            result = store.recover(snapshot, args.policy_version)
        except Exception as exc:  # noqa: BLE001 - CLI boundary.
            print(f"fatal error: {exc}")
            return 1
        print("exposure classification recovery summary")
        for key, value in result.items():
            print(f"{key.replace('_', ' ')}: {value}")
        return 0
    policy = load_exposure_policy(policy_path)
    with duckdb.connect(str(DUCKDB_PATH), read_only=True) as connection:
        frame = connection.execute(
            """
            SELECT ticker, name, security_type, normalized_category
            FROM security_master
            WHERE snapshot_date = ?
            ORDER BY ticker
            """,
            [snapshot],
        ).fetchdf()
    if frame.empty:
        print(f"fatal error: security master snapshot not found: {snapshot}")
        return 1
    classified = policy.classify_snapshot(frame, snapshot)
    output = store.persist(classified)
    print("exposure classification build summary")
    print(f"snapshot date: {snapshot}")
    print(f"policy version: {policy.policy_version}")
    print(f"rows: {len(classified)}")
    print(f"parquet path: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
