"""Lossless, hash-bound compressed transport for expanded V2 evidence graphs.

The ordinary JSON limit is unchanged. Archives keep the complete canonical graph
and its typed integrity checks; neither engine evidence nor validations are dropped.
"""

import gzip
import hashlib
import json
import re
from pathlib import Path

from market_dashboard.workstation.snapshot_v2 import WorkstationSnapshotV2

MAX_TRANSPORT_BYTES = 32 * 1024**2
FIXED_BYTES = 24 * 1024**2
BYTES_PER_RECORD = 65536
# Independent anti-decompression-bomb bound, not a research-universe threshold.
MAX_DECODE_BYTES = 512 * 1024**2
ARCHIVE_VERSION = "workstation-snapshot-archive-v1"


def archive_payload(path, envelope):
    name = envelope.get("payload", "")
    if not re.fullmatch(r"[0-9a-f]{64}\.snapshot\.json\.gz", name):
        raise ValueError("ARCHIVE_PAYLOAD_NAME_INVALID")
    payload = Path(path).parent / name
    if payload.is_symlink() or payload.stat().st_size > MAX_TRANSPORT_BYTES:
        raise ValueError("ARCHIVE_TRANSPORT_BOUND")
    raw = payload.read_bytes()
    if hashlib.sha256(raw).hexdigest() != name[:64]:
        raise ValueError("ARCHIVE_PAYLOAD_HASH_MISMATCH")
    return payload, raw


def read_snapshot(path):
    path = Path(path)
    if path.stat().st_size > MAX_TRANSPORT_BYTES:
        raise ValueError("SNAPSHOT_TRANSPORT_BOUND")
    raw = path.read_bytes()
    header = json.loads(raw)
    if not isinstance(header, dict):
        raise ValueError("SNAPSHOT_OBJECT_REQUIRED")  # noqa: TRY004 — retained snapshot error boundary
    if header.get("schema_version") != ARCHIVE_VERSION:
        return WorkstationSnapshotV2.model_validate_json(raw)
    count, size = header.get("record_count"), header.get("uncompressed_bytes")
    if (
        type(count) is not int
        or count < 1
        or type(size) is not int
        or not 0 < size <= min(MAX_DECODE_BYTES, FIXED_BYTES + count * BYTES_PER_RECORD)
    ):
        raise ValueError("ARCHIVE_DECODE_BOUND")
    payload, _ = archive_payload(path, header)
    with gzip.open(payload, "rb") as stream:
        raw = stream.read(size + 1)
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != header.get(
        "uncompressed_sha256"
    ):
        raise ValueError("ARCHIVE_CANONICAL_HASH_MISMATCH")
    snapshot = WorkstationSnapshotV2.model_validate_json(raw)
    if len(
        snapshot.record_index
    ) != count or snapshot.logical_fingerprint != header.get("logical_fingerprint"):
        raise ValueError("ARCHIVE_CANONICAL_IDENTITY_MISMATCH")
    if (
        snapshot.evaluation is None
        or snapshot.evaluation.bootstrap is None
        or snapshot.evaluation.bootstrap.version != "coverage-current-state-v1"
    ):
        raise ValueError("EXPANDED_COVERAGE_CONTEXT_REQUIRED")
    return snapshot


def write_snapshot(path, snapshot):
    from market_dashboard.workstation.refresh.operations import atomic_replace

    path = Path(path)
    if path.exists():
        raise ValueError("SNAPSHOT_TARGET_EXISTS")
    raw = snapshot.model_dump_json().encode()
    if len(raw) <= FIXED_BYTES:
        with path.open("xb") as stream:
            stream.write(raw)
        return {
            "transport_bytes": len(raw),
            "uncompressed_bytes": len(raw),
            "transport": "json",
        }
    count = len(snapshot.record_index)
    if len(raw) > min(MAX_DECODE_BYTES, FIXED_BYTES + count * BYTES_PER_RECORD):
        raise ValueError("ARCHIVE_DECODE_BOUND")
    compressed = gzip.compress(raw, compresslevel=6, mtime=0)
    if len(compressed) > MAX_TRANSPORT_BYTES:
        raise ValueError("ARCHIVE_TRANSPORT_BOUND")
    sha = hashlib.sha256(compressed).hexdigest()
    name = sha + ".snapshot.json.gz"
    atomic_replace(path.parent / name, compressed)
    envelope = {
        "schema_version": ARCHIVE_VERSION,
        "payload": name,
        "record_count": count,
        "logical_fingerprint": snapshot.logical_fingerprint,
        "uncompressed_bytes": len(raw),
        "uncompressed_sha256": hashlib.sha256(raw).hexdigest(),
    }
    atomic_replace(path, (json.dumps(envelope, indent=2) + "\n").encode())
    return {
        "transport_bytes": path.stat().st_size + len(compressed),
        "uncompressed_bytes": len(raw),
        "transport": ARCHIVE_VERSION,
    }


def copy_payload(source, destination_directory):
    from market_dashboard.workstation.refresh.operations import atomic_replace

    source = Path(source)
    header = json.loads(source.read_bytes())
    if header.get("schema_version") != ARCHIVE_VERSION:
        return
    payload, raw = archive_payload(source, header)
    target = Path(destination_directory) / payload.name
    if target.exists():
        if target.is_symlink() or target.read_bytes() != raw:
            raise ValueError("ARCHIVE_DESTINATION_CHANGED")
    else:
        atomic_replace(target, raw)
