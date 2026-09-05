from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_dashboard.data.deepvue_themes import (  # noqa: E402
    DeepvueThemeNormalizer,
    DeepvueThemeStore,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and optionally publish a dated Deepvue theme snapshot."
    )
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--source-as-of-date", required=True)
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Persist normalized DuckDB/Parquet snapshots. Default is validation only.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    date.fromisoformat(args.source_as_of_date)
    normalizer = DeepvueThemeNormalizer()
    try:
        catalog, memberships = normalizer.read_csv(
            args.csv_path, args.source_as_of_date
        )
        source_rows = len(memberships) + int(
            catalog["membership_status"].eq("EMPTY").sum()
        )
        summary = normalizer.summarize(
            catalog, memberships, source_rows=source_rows
        )
        paths: tuple[Path, Path] | None = None
        if args.publish:
            paths = DeepvueThemeStore().persist(catalog, memberships)
    except Exception as exc:  # noqa: BLE001 - CLI boundary.
        print(f"fatal error: {exc}")
        return 1

    print("Deepvue theme validation")
    for key, value in summary.to_dict().items():
        print(f"{key}: {value}")
    print(f"publication_state: {'published' if paths else 'dry_run'}")
    if paths:
        print(f"catalog_parquet: {paths[0]}")
        print(f"membership_parquet: {paths[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
