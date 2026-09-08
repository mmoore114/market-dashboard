"""Validate a hierarchy capture; publishing requires explicit paths and backup."""

import argparse
from hashlib import sha256
from pathlib import Path

from market_dashboard.data.deepvue_hierarchy import (
    DeepvueHierarchyStore,
    parent_conflicts,
    read_hierarchy,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--source-as-of-date", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--duckdb-path", type=Path)
    parser.add_argument("--parquet-directory", type=Path)
    parser.add_argument("--verified-backup", type=Path)
    args = parser.parse_args()
    digest = lambda p: sha256(p.read_bytes()).hexdigest()
    if digest(args.csv_path) != args.expected_sha256:
        parser.error("Source hash mismatch")
    frame = read_hierarchy(args.csv_path, args.source_as_of_date)
    print(f"rows: {len(frame)}; parent conflicts: {len(parent_conflicts(frame))}")
    if args.publish:
        if not all((args.duckdb_path, args.parquet_directory, args.verified_backup)):
            parser.error(
                "Explicit database, Parquet directory and verified backup required"
            )
        if args.duckdb_path.resolve() == args.verified_backup.resolve() or digest(
            args.duckdb_path
        ) != digest(args.verified_backup):
            parser.error("Independent byte-identical database backup required")
        if args.parquet_directory.exists():
            parser.error(
                "Use a new Parquet publication directory; preserve prior partitions"
            )
        DeepvueHierarchyStore(
            duckdb_path=args.duckdb_path, parquet_directory=args.parquet_directory
        ).persist(frame)
    print("publication_state: " + ("published" if args.publish else "dry_run"))


if __name__ == "__main__":
    main()
