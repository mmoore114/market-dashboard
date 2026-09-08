"""Regression boundaries for bounded JSON and durable replay recovery."""

import io
import json
from pathlib import Path

import pandas as pd
import pytest

from market_dashboard.aperture.leadership import fingerprint
from market_dashboard.aperture.rules import load_aperture_rules
from market_dashboard.workstation.fixtures import fixture_arguments
from market_dashboard.workstation.materialization.checkpoint import ReplayCheckpoint
from market_dashboard.workstation.snapshot_v2 import materialize_v2
from market_dashboard.workstation.streaming import (
    read_stream,
    snapshot_chunks,
    snapshot_digest,
    snapshot_sizes,
)


@pytest.fixture(scope="module")
def snapshot():
    values = fixture_arguments(
        load_aperture_rules(Path("config/aperture_rules_v1.yaml"))
    )
    return materialize_v2(
        **values,
        universe=values["regime"].inputs.universe,
        leadership=values["records"][0].output.inputs.leadership,
    )


def test_stream_preserves_exact_fingerprint_and_typed_integrity(snapshot):
    assert snapshot_digest(snapshot) == fingerprint(
        snapshot.model_dump(
            mode="json", exclude={"generated_at", "logical_fingerprint"}
        )
    )
    raw = b"".join(snapshot_chunks(snapshot))
    assert snapshot_sizes(snapshot)[0] == len(raw)
    assert json.loads(raw) == snapshot.model_dump(mode="json")
    recovered = read_stream(io.StringIO(raw.decode()))
    assert recovered.logical_fingerprint == snapshot.logical_fingerprint
    assert recovered.records == snapshot.records
    changed = raw.replace(snapshot.logical_fingerprint.encode(), b"0" * 64)
    with pytest.raises(ValueError, match="fingerprint"):
        read_stream(io.StringIO(changed.decode()))
    with pytest.raises(ValueError):
        read_stream(io.StringIO(raw[:-10].decode()))
    with pytest.raises(ValueError):
        read_stream(io.StringIO(raw.decode() + "{}"))


def test_checkpoint_resume_and_invalidation(snapshot, tmp_path):
    structure = snapshot.records[0].output.inputs.structure
    setup = snapshot.records[0].output.inputs.setups
    checkpoint = ReplayCheckpoint(
        tmp_path,
        versions=snapshot.versions,
        source=structure.inputs.source,
        calendar=snapshot.calendar,
        as_of=snapshot.as_of_session,
        corporate_actions={("A", snapshot.as_of_session): ("VERIFIED", ("split",))},
    )
    frame = pd.DataFrame({"ticker": [structure.inputs.symbol], "close": [1.0]})
    key = checkpoint.identity(structure.inputs.symbol, frame)
    assert checkpoint.load(key) is None
    checkpoint.save(key, structure, setup)
    assert checkpoint.load(key) == (structure, setup)
    assert checkpoint.identity(structure.inputs.symbol, frame.assign(close=2.0)) != key
    checkpoint.basis["code_sha256"] = "changed"
    assert checkpoint.identity(structure.inputs.symbol, frame) != key
    with pytest.raises(ValueError):
        checkpoint.save(key, structure, setup)
    path = tmp_path / (key + ".json")
    receipt = json.loads(path.read_text())
    receipt["payload"][0]["value"]["error"] = "tampered"
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        checkpoint.load(key)


def test_disk_normalization_preserves_graph(snapshot):
    values = fixture_arguments(
        load_aperture_rules(Path("config/aperture_rules_v1.yaml"))
    )
    disk = materialize_v2(
        **values,
        universe=values["regime"].inputs.universe,
        leadership=values["records"][0].output.inputs.leadership,
        disk_evidence=True,
    )
    assert disk.logical_fingerprint == snapshot.logical_fingerprint
    assert disk.evidence == snapshot.evidence
    assert disk.records == snapshot.records


def test_streaming_never_dumps_whole_snapshot(snapshot, monkeypatch):
    cls = type(snapshot)
    original = cls.model_dump

    def bounded_dump(self, *args, **kwargs):
        include = kwargs.get("include")
        assert include and "evidence" not in include and "record_index" not in include
        return original(self, *args, **kwargs)

    monkeypatch.setattr(cls, "model_dump", bounded_dump)
    assert snapshot_digest(snapshot) == snapshot.logical_fingerprint
    assert sum(map(len, snapshot_chunks(snapshot))) == snapshot_sizes(snapshot)[0]


def test_plain_archive_writer_retains_snapshot(snapshot, tmp_path):
    from market_dashboard.workstation.archive import read_snapshot, write_snapshot

    path = tmp_path / "snapshot.json"
    receipt = write_snapshot(path, snapshot)
    assert receipt["transport"] == "json"
    assert read_snapshot(path).logical_fingerprint == snapshot.logical_fingerprint
    with pytest.raises(ValueError, match="TARGET_EXISTS"):
        write_snapshot(path, snapshot)


def test_batched_readback_checks_every_row_and_exact_values(tmp_path):
    from market_dashboard.workstation.refresh.readback import verify_frame

    frame = pd.DataFrame(
        {
            "ticker": ["A", "B", "C", "D", "E"],
            "close": [1.0, float("nan"), 3.125, 4.0, 5.0],
        }
    )
    path = tmp_path / "rows.parquet"
    frame.to_parquet(path, index=False)
    verify_frame(path, frame, batch_size=2)
    changed = frame.copy()
    changed.loc[4, "close"] += 1e-12
    with pytest.raises(AssertionError):
        verify_frame(path, changed, batch_size=2)
    with pytest.raises(ValueError, match="ROW_COUNT"):
        verify_frame(path, pd.concat([frame, frame.iloc[:1]]), batch_size=2)


def test_compatible_downstream_change_reuses_shard_but_price_change_refuses(
    snapshot, tmp_path
):
    from market_dashboard.workstation.materialization.checkpoint import (
        engine_code_files,
    )

    structure = snapshot.records[0].output.inputs.structure
    setup = snapshot.records[0].output.inputs.setups
    kwargs = {
        "versions": snapshot.versions,
        "source": structure.inputs.source,
        "calendar": snapshot.calendar,
        "as_of": snapshot.as_of_session,
        "corporate_actions": {},
    }
    before = engine_code_files()
    before["aperture/decision_adapters.py"] = "0" * 64
    old = ReplayCheckpoint(tmp_path, **kwargs)
    old.basis["code_sha256"] = fingerprint(before)
    frame = pd.DataFrame({"ticker": [structure.inputs.symbol], "close": [1.0]})
    old_key = old.identity(structure.inputs.symbol, frame)
    old.save(old_key, structure, setup)
    compatibility = tmp_path / "compatibility"
    compatibility.mkdir()
    proof = {
        "schema_version": "replay-code-compatibility-v1",
        "from": fingerprint(before),
        "to": fingerprint(engine_code_files()),
        "from_files": before,
    }
    path = compatibility / "proof.json"
    path.write_text(json.dumps(proof))
    current = ReplayCheckpoint(tmp_path, **kwargs)
    key = current.identity(structure.inputs.symbol, frame)
    assert key != old_key
    assert current.load(key) == (structure, setup)
    assert (
        current.load(current.identity(structure.inputs.symbol, frame.assign(close=2.0)))
        is None
    )
    proof["from_files"]["aperture/structure_v2.py"] = "0" * 64
    proof["from"] = fingerprint(proof["from_files"])
    path.write_text(json.dumps(proof))
    with pytest.raises(ValueError, match="COMPATIBILITY_PROOF_INVALID"):
        ReplayCheckpoint(tmp_path, **kwargs)
