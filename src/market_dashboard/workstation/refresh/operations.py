"""Locked, recoverable activation; failed candidates never replace the last success."""

import fcntl
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from market_dashboard.workstation.snapshot_v2 import WorkstationSnapshotV2


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_replace(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".activation-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextmanager
def exclusive_lock(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / "refresh.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("REFRESH_ALREADY_RUNNING") from None
        yield


def status(root, now):
    path = Path(root) / "current.json"
    if not path.exists():
        return {"available": False, "reason": "NO_SUCCESSFUL_SNAPSHOT"}
    try:
        s = WorkstationSnapshotV2.model_validate_json(path.read_bytes())
        return {
            "available": s.freshness.state == "FRESH" and now < s.freshness.valid_until,
            "path": str(path),
            "fingerprint": s.logical_fingerprint,
            "market_session": str(s.as_of_session),
            "action_session": str(s.action_session),
            "evaluation": s.evaluation.evaluation_timestamp.isoformat()
            if s.evaluation
            else None,
            "valid_until": s.freshness.valid_until.isoformat(),
            "age_seconds": (now - s.generated_at).total_seconds(),
        }
    except (ValueError, OSError):
        return {"available": False, "reason": "SNAPSHOT_INVALID"}


def activate(candidate, root, *, expected_hash, now=None):
    now = now or datetime.now(UTC)
    candidate, root = Path(candidate), Path(root)
    raw = candidate.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_hash:
        raise ValueError("CANDIDATE_HASH_CHANGED")
    s = WorkstationSnapshotV2.model_validate_json(raw)
    if (
        s.mode != "LOCAL_SNAPSHOT"
        or s.versions.structure != "structure-engine-v2"
        or s.versions.setup != "setup-engine-v2"
        or not s.groups
    ):
        raise ValueError("POPULATED_REAL_V2_REQUIRED")
    if (
        s.freshness.state != "FRESH"
        or not s.generated_at <= now < s.freshness.valid_until
    ):
        raise ValueError("CANDIDATE_NOT_CURRENT")
    target = root / "current.json"
    backups = root / "activation-backups"
    backups.mkdir(exist_ok=True)
    if target.exists():
        before = target.read_bytes()
        h = hashlib.sha256(before).hexdigest()
        backup = backups / f"{h}.json"
        if not backup.exists():
            with backup.open("xb") as stream:
                stream.write(before)
                stream.flush()
                os.fsync(stream.fileno())
        if digest(backup) != h:
            raise ValueError("ACTIVATION_BACKUP_MISMATCH")
    # Intent is recoverable; immutable candidate and prior backup survive any interruption.
    atomic_replace(
        root / "activation-intent.json",
        json.dumps({"candidate": str(candidate), "sha256": expected_hash}).encode(),
    )
    atomic_replace(target, raw)
    if digest(target) != expected_hash:
        raise ValueError("ACTIVATION_READBACK_MISMATCH")
    return status(root, now)
