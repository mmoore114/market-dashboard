import json
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from market_dashboard.aperture.leadership import aggregate_groups, select_snapshot
from market_dashboard.aperture.leadership_contracts import DatedProvenanceV1
from market_dashboard.data.deepvue_hierarchy import (
    DeepvueHierarchyStore,
    hierarchy_memberships,
    parent_conflicts,
    read_hierarchy,
)
from market_dashboard.data.deepvue_themes import DeepvueThemeNormalizer
from market_dashboard.data.security_identity import (
    CompatibilityBoundary,
    ReferenceTicker,
)
from market_dashboard.workstation.models import VersionsV1


def source(tmp_path):
    path = tmp_path / "hierarchy.csv"
    path.write_text(
        "Symbol,Sub-Industry,Industry,Group,Sector\nAAA,Shared,Parent A,G,S\nBBB,Shared,Parent B,G,S\nCCC,-,-,-,-\nMixed,Other,Parent B,G,S\n"
    )
    return read_hierarchy(path, "2026-09-07")


def schedules(frame):
    return hierarchy_memberships(
        frame,
        provenance=DatedProvenanceV1(
            snapshot_id="test",
            version="test",
            source_as_of_date=date(2026, 9, 7),
            known_session=date(2026, 9, 8),
            effective_session=date(2026, 9, 8),
            valid_through=date(2026, 9, 8),
        ),
        boundary=CompatibilityBoundary([ReferenceTicker(s) for s in frame.ticker]),
        disposition_config=json.loads(
            Path("config/deepvue_identity_disposition_v1.json").read_text()
        ),
        identity_version="synthetic-master-v1",
    )


def test_default_pair_and_explicit_v1():
    v = VersionsV1(security_master="test")
    assert (v.structure, v.setup) == ("structure-engine-v2", "setup-engine-v2")
    old = VersionsV1.v1(security_master="test")
    assert VersionsV1.model_validate_json(old.model_dump_json()) == old
    with pytest.raises(ValueError, match="coherent"):
        VersionsV1.model_validate(v.model_dump() | {"structure": "structure-engine-v1"})


def test_paths_conflicts_nulls_and_no_backdating(tmp_path):
    frame = source(tmp_path)
    groups = schedules(frame)
    assert frame.loc[frame.ticker == "CCC", "sector"].isna().all()
    assert len(parent_conflicts(frame)) == 1
    assert len(groups[-1].group_ids) == 3
    assert all(
        "Shared" in m.group_id
        for m in groups[-1].members
        if m.source_symbol in ("AAA", "BBB")
    )
    mixed = next(m for m in groups[-1].members if m.source_symbol == "Mixed")
    assert (
        mixed.market_data_symbol is None
        and mixed.identity_reason == "MIXED_CASE_REFERENCE_ONLY"
    )
    assert select_snapshot((groups[0],), date(2026, 9, 4)) is None
    with pytest.raises(ValueError, match="Membership not valid"):
        aggregate_groups((), groups, date(2026, 9, 4))
    evidence = aggregate_groups((), groups, date(2026, 9, 8))
    assert {str(g.group_type) for g in evidence} == {
        "SECTOR",
        "GROUP",
        "INDUSTRY",
        "SUB_INDUSTRY",
    }
    assert all(g.leadership_rank is None for g in evidence)
    with pytest.raises(ValueError, match="Expired"):
        select_snapshot((groups[0],), date(2026, 9, 9))


def test_hierarchy_publication_roundtrip(tmp_path):
    frame = source(tmp_path)
    store = DeepvueHierarchyStore(
        duckdb_path=tmp_path / "local.duckdb", parquet_directory=tmp_path / "hierarchy"
    )
    path = store.persist(frame)
    pd.testing.assert_frame_equal(pd.read_parquet(path), frame)
    with duckdb.connect(str(tmp_path / "local.duckdb"), read_only=True) as con:
        assert (
            con.execute("select count(*) from deepvue_symbol_hierarchy").fetchone()[0]
            == 4
        )
        assert con.execute(
            "select sector from deepvue_symbol_hierarchy where ticker='CCC'"
        ).fetchone() == (None,)


def test_separately_dated_many_to_many_and_empty_theme(tmp_path):
    p = tmp_path / "themes.csv"
    p.write_text("Theme,Symbol\nOne,AAA\nTwo,AAA\nBitcoin,\n")
    catalog, members = DeepvueThemeNormalizer().read_csv(p, "2026-09-05")
    assert len(catalog) == 3 and len(members) == 2
    assert set(members.source_as_of_date) == {date(2026, 9, 5)}
    assert catalog.loc[catalog.theme == "Bitcoin", "constituent_count"].iloc[0] == 0


def test_default_replay_with_all_dated_levels(tmp_path):
    from market_dashboard.workstation.materialization.audit import inspect
    from market_dashboard.workstation.materialization.contracts import GroupScheduleV1
    from market_dashboard.workstation.materialization.replay import replay
    from market_dashboard.workstation.snapshot_v2 import WorkstationSnapshotV2
    from tests.materialization_fixtures import attach, synthetic_plan

    plan = synthetic_plan(tmp_path, n=260, symbols=("AAA", "BBB"))
    loaded, _, findings, _, _ = inspect(plan)
    assert not any(f.status == "HARD_BLOCKER" for f in findings)
    frame = source(tmp_path)
    frame = frame[frame.ticker.isin(("AAA", "BBB"))]
    groups = schedules(frame)
    p = groups[0].provenance.model_copy(
        update={
            "source_as_of_date": plan.as_of_session,
            "known_session": plan.as_of_session,
            "effective_session": plan.as_of_session,
            "valid_through": plan.as_of_session,
        }
    )
    plan = attach(
        plan,
        "taxonomy",
        GroupScheduleV1(
            snapshots=tuple(g.model_copy(update={"provenance": p}) for g in groups)
        ),
    )
    loaded, _, findings, _, _ = inspect(plan)
    assert not any(f.status == "HARD_BLOCKER" for f in findings), findings
    selected = plan.model_copy(
        update={"versions": VersionsV1(security_master=plan.versions.security_master)}
    )
    snapshot, _ = replay(selected, loaded)
    result = WorkstationSnapshotV2.model_validate_json(snapshot.model_dump_json())
    assert result.versions.structure == "structure-engine-v2"
    assert (
        result.records[0].output.inputs.structure.engine_version
        == "structure-engine-v2"
    )
    assert {str(g.group_type) for g in result.groups} == {
        "SECTOR",
        "GROUP",
        "INDUSTRY",
        "SUB_INDUSTRY",
    }
    assert all(g.rank_change_5 is None for g in result.groups)
    assert any(g.valid_RS_comp_count > 0 for g in result.groups)
