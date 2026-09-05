from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_dashboard.data.deepvue_taxonomy import (  # noqa: E402
    DeepvueTaxonomyNormalizer,
    DeepvueTaxonomyStore,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and optionally publish a dated Deepvue taxonomy export."
    )
    parser.add_argument("csv_path", type=Path)
    parser.add_argument(
        "--source-as-of-date",
        required=True,
        help="Date shown by or captured from Deepvue, YYYY-MM-DD.",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Persist normalized DuckDB/Parquet snapshots. Default is validation only.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    date.fromisoformat(args.source_as_of_date)
    normalizer = DeepvueTaxonomyNormalizer()
    try:
        symbols = normalizer.read_csv(args.csv_path, args.source_as_of_date)
        groups = normalizer.build_group_snapshot(symbols)
        summary = normalizer.summarize(symbols, groups)
        paths: tuple[Path, Path] | None = None
        if args.publish:
            paths = DeepvueTaxonomyStore().persist(symbols, groups)
    except Exception as exc:  # noqa: BLE001 - CLI boundary.
        print(f"fatal error: {exc}")
        return 1

    print("Deepvue taxonomy validation")
    for key, value in summary.to_dict().items():
        print(f"{key}: {value}")
    print(f"publication_state: {'published' if paths else 'dry_run'}")
    if paths:
        print(f"symbol_parquet: {paths[0]}")
        print(f"group_parquet: {paths[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
