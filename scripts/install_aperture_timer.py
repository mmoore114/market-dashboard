"""Install the authorized local user timer after reviewing the private config."""

import argparse
from pathlib import Path

from market_dashboard.workstation.refresh.scheduler import install

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument(
        "--config", type=Path, default=Path.home() / ".config/aperture/refresh.json"
    )
    install(p.parse_args().config)
