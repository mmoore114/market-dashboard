import gzip
import hashlib
import json

import pytest

from market_dashboard.workstation.archive import (
    ARCHIVE_VERSION,
    archive_payload,
    read_snapshot,
)


def test_archive_does_not_allow_paths_or_changed_bytes(tmp_path):
    path = tmp_path / "snapshot.json"
    with pytest.raises(ValueError, match="NAME_INVALID"):
        archive_payload(path, {"payload": "../private.json.gz"})
    name = "0" * 64 + ".snapshot.json.gz"
    (tmp_path / name).write_bytes(b"changed")
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        archive_payload(path, {"payload": name})


def test_archive_checks_decode_length_before_typed_decode(tmp_path):
    raw = b"{}"
    compressed = gzip.compress(raw, mtime=0)
    name = hashlib.sha256(compressed).hexdigest() + ".snapshot.json.gz"
    (tmp_path / name).write_bytes(compressed)
    header = {
        "schema_version": ARCHIVE_VERSION,
        "payload": name,
        "record_count": 1,
        "uncompressed_bytes": 3,
        "uncompressed_sha256": hashlib.sha256(raw).hexdigest(),
    }
    p = tmp_path / "snapshot.json"
    p.write_text(json.dumps(header))
    with pytest.raises(ValueError, match="CANONICAL_HASH_MISMATCH"):
        read_snapshot(p)
    header["uncompressed_bytes"] = 1024**3
    p.write_text(json.dumps(header))
    with pytest.raises(ValueError, match="DECODE_BOUND"):
        read_snapshot(p)
