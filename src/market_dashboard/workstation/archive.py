"""Lossless, hash-bound compressed transport for expanded V2 evidence graphs.

The ordinary JSON limit is unchanged. Archives keep the complete canonical graph
and its typed integrity checks; neither engine evidence nor validations are dropped.
"""

import gzip
import hashlib
import io
import json
import os
import re
import tempfile
from pathlib import Path

from market_dashboard.workstation.snapshot_v2 import WorkstationSnapshotV2

from .streaming import read_stream, snapshot_chunks

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
    # Verify bounded decompression to disk before any typed loading. The second
    # pass decodes a single graph row, not a full JSON byte buffer/dictionary.
    with tempfile.TemporaryFile() as canonical:
        digest = hashlib.sha256()
        actual = 0
        with gzip.open(payload, "rb") as stream:
            while chunk := stream.read(min(65536, size + 1 - actual)):
                actual += len(chunk)
                if actual > size:
                    raise ValueError("ARCHIVE_CANONICAL_HASH_MISMATCH")
                digest.update(chunk)
                canonical.write(chunk)
        if actual != size or digest.hexdigest() != header.get("uncompressed_sha256"):
            raise ValueError("ARCHIVE_CANONICAL_HASH_MISMATCH")
        canonical.seek(0)
        snapshot = read_stream(io.TextIOWrapper(canonical, encoding="utf-8"))
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
    count = len(snapshot.record_index)
    limit = min(MAX_DECODE_BYTES, FIXED_BYTES + count * BYTES_PER_RECORD)
    with tempfile.TemporaryFile() as canonical:
        digest = hashlib.sha256()
        size = 0
        for chunk in snapshot_chunks(snapshot):
            size += len(chunk)
            if size > limit:
                raise ValueError("ARCHIVE_DECODE_BOUND")
            digest.update(chunk)
            canonical.write(chunk)
        canonical.seek(0)
        if size <= FIXED_BYTES:
            with path.open("xb") as stream:
                while chunk := canonical.read(65536):
                    stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
            return {
                "transport_bytes": size,
                "uncompressed_bytes": size,
                "transport": "json",
            }
        with tempfile.TemporaryFile() as compressed:
            with gzip.GzipFile(
                fileobj=compressed, mode="wb", compresslevel=6, mtime=0
            ) as stream:
                while chunk := canonical.read(65536):
                    stream.write(chunk)
            transport_size = compressed.tell()
            if transport_size > MAX_TRANSPORT_BYTES:
                raise ValueError("ARCHIVE_TRANSPORT_BOUND")
            compressed.seek(0)
            compressed_digest = hashlib.sha256()
            while chunk := compressed.read(65536):
                compressed_digest.update(chunk)
            name = compressed_digest.hexdigest() + ".snapshot.json.gz"
            compressed.seek(0)
            # Compressed transport is independently limited to 32 MiB.
            atomic_replace(path.parent / name, compressed.read())
    envelope = {
        "schema_version": ARCHIVE_VERSION,
        "payload": name,
        "record_count": count,
        "logical_fingerprint": snapshot.logical_fingerprint,
        "uncompressed_bytes": size,
        "uncompressed_sha256": digest.hexdigest(),
    }
    atomic_replace(path, (json.dumps(envelope, indent=2) + "\n").encode())
    return {
        "transport_bytes": path.stat().st_size + transport_size,
        "uncompressed_bytes": size,
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
