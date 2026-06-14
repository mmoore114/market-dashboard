from datetime import date, timedelta
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_dashboard.data.massive_client import MassiveClient


def main() -> int:
    end_date = date.today()
    start_date = end_date - timedelta(days=30)

    try:
        client = MassiveClient()
        rows = client.get_adjusted_daily_bars("SPY", start_date, end_date)
    except ValueError as exc:
        print(str(exc))
        return 1

    if rows:
        returned_start = rows[0]["date"]
        returned_end = rows[-1]["date"]
        latest_close = rows[-1]["close"]
    else:
        returned_start = "none"
        returned_end = "none"
        latest_close = "none"

    print("ticker: SPY")
    print(f"date range returned: {returned_start} to {returned_end}")
    print(f"number of rows: {len(rows)}")
    print(f"latest adjusted close: {latest_close}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
