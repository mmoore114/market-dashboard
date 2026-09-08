"""Dated hierarchy import: exact per-symbol paths, never canonical parent links."""

import json
from datetime import UTC, date, datetime
from hashlib import sha256
from itertools import pairwise
from pathlib import Path

import duckdb
import pandas as pd

from market_dashboard.aperture.leadership_adapters import (
    exact_disposition,
    identity_member,
)
from market_dashboard.aperture.leadership_contracts import GroupMembershipV1, GroupType
from market_dashboard.data.deepvue_taxonomy import (
    _atomic_parquet,
    _clean_classification,
)

LEVELS = ("sector", "group", "industry", "sub_industry")
SOURCE_COLUMNS = ("Sector", "Group", "Industry", "Sub-Industry")


def read_hierarchy(csv_path, source_as_of_date):
    """Keep missing assignments and original row paths in a separate dated table."""
    raw = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    if set(raw.columns) != {"Symbol", *SOURCE_COLUMNS}:
        raise ValueError("EXACT_HIERARCHY_COLUMNS_REQUIRED")
    if (
        raw.Symbol.eq("").any()
        or raw.Symbol.str.strip().ne(raw.Symbol).any()
        or raw.Symbol.duplicated().any()
    ):
        raise ValueError("EXACT_UNIQUE_NONBLANK_SYMBOLS_REQUIRED")
    frame = pd.DataFrame({"ticker": raw.Symbol})
    for level, column in zip(LEVELS, SOURCE_COLUMNS):
        frame[level] = raw[column].map(_clean_classification)
    frame["source_as_of_date"] = date.fromisoformat(str(source_as_of_date))
    frame["source_provider"] = "deepvue"
    frame["source_taxonomy"] = "deepvue_hierarchy_v1"
    frame["source_row_fingerprint"] = [
        sha256(
            json.dumps([str(source_as_of_date), *row], ensure_ascii=False).encode()
        ).hexdigest()
        for row in frame[["ticker", *LEVELS]].itertuples(index=False, name=None)
    ]
    frame["ingested_at"] = datetime.now(UTC).replace(tzinfo=None)
    return frame.sort_values("ticker").reset_index(drop=True)


def parent_conflicts(frame):
    result = []
    for parent, child in pairwise(LEVELS):
        for label, rows in frame.loc[frame[child].notna()].groupby(child):
            parents = sorted(rows[parent].dropna().unique())
            if len(parents) > 1:
                result.append(
                    {
                        "child_level": child,
                        "child_label": label,
                        "parent_level": parent,
                        "observed_parents": parents,
                    }
                )
    return result


def hierarchy_memberships(
    frame, *, provenance, boundary, disposition_config, identity_version
):
    if any(
        pd.Timestamp(d).date() != provenance.source_as_of_date
        for d in frame.source_as_of_date
    ):
        raise ValueError("MIXED_OR_INCORRECT_SOURCE_DATES")
    if frame.ticker.duplicated().any():
        raise ValueError("DUPLICATE_HIERARCHY_SYMBOL")
    disposition = exact_disposition(disposition_config)
    snapshots = []
    for i, level in enumerate(LEVELS):
        members = []
        for row in frame.to_dict("records"):
            if pd.isna(row[level]):
                continue
            # JSON array is an unambiguous path identity, including explicit null parents.
            path = json.dumps(
                [None if pd.isna(row[k]) else row[k] for k in LEVELS[: i + 1]],
                ensure_ascii=False,
            )
            members.append(identity_member(row["ticker"], path, boundary, disposition))
        snapshots.append(
            GroupMembershipV1(
                provenance=provenance,
                group_type=GroupType(level.upper()),
                group_ids=tuple(sorted({m.group_id for m in members})),
                members=tuple(
                    sorted(members, key=lambda m: (m.group_id, m.source_symbol))
                ),
                identity_version=identity_version,
                disposition_version=disposition_config["version"],
            )
        )
    return tuple(snapshots)


class DeepvueHierarchyStore:
    """Same dated DuckDB/Parquet publication boundary as existing Deepvue stores.

    Caller owns a verified backup and recovery before invoking persistence.
    A new table preserves earlier sub-industry/rank publications without migration.
    """

    def __init__(self, *, duckdb_path, parquet_directory):
        self.duckdb_path = Path(duckdb_path)
        self.parquet_directory = Path(parquet_directory)

    def persist(self, frame):
        if frame.empty or frame.source_as_of_date.nunique() != 1:
            raise ValueError("ONE_NONEMPTY_DATED_HIERARCHY_REQUIRED")
        day = pd.Timestamp(frame.source_as_of_date.iloc[0]).date()
        target = (
            self.parquet_directory
            / f"source_as_of_date={day}"
            / "symbol_hierarchy.parquet"
        )
        _atomic_parquet(frame, target)
        self.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(self.duckdb_path)) as con:
            con.register("incoming_hierarchy", frame)
            con.execute("BEGIN TRANSACTION")
            try:
                con.execute(
                    "CREATE TABLE IF NOT EXISTS deepvue_symbol_hierarchy AS SELECT * FROM incoming_hierarchy WHERE FALSE"
                )
                con.execute(
                    "DELETE FROM deepvue_symbol_hierarchy WHERE source_as_of_date = ?",
                    [day],
                )
                con.execute(
                    "INSERT INTO deepvue_symbol_hierarchy SELECT * FROM incoming_hierarchy"
                )
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
        return target
