from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIRECTORY = DATA_DIR / "raw"
PROCESSED_DIRECTORY = DATA_DIR / "processed"
DATABASE_DIRECTORY = DATA_DIR / "database"
DUCKDB_FILENAME = "market_dashboard.duckdb"
DUCKDB_PATH = DATABASE_DIRECTORY / DUCKDB_FILENAME

# Backward-compatible aliases for early project setup code.
RAW_DATA_DIR = RAW_DIRECTORY
PROCESSED_DATA_DIR = PROCESSED_DIRECTORY
DATABASE_DIR = DATABASE_DIRECTORY


def create_required_directories() -> None:
    """Create local data directories required by ingestion and storage."""
    for directory in (RAW_DIRECTORY, PROCESSED_DIRECTORY, DATABASE_DIRECTORY):
        directory.mkdir(parents=True, exist_ok=True)
