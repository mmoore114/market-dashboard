from pathlib import Path


def test_expected_project_directories_exist() -> None:
    project_root = Path(__file__).resolve().parents[1]
    expected_directories = [
        "app",
        "config",
        "data/raw",
        "data/processed",
        "data/database",
        "notebooks",
        "src/market_dashboard/data",
        "src/market_dashboard/features",
        "src/market_dashboard/rankings",
        "src/market_dashboard/dashboard",
        "tests",
    ]

    for directory in expected_directories:
        assert (project_root / directory).is_dir()
