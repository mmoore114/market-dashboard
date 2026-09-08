"""Explicit JSON loading only; no provider, database or production-data fallback."""

import json
from datetime import UTC, datetime
from pathlib import Path

from market_dashboard.aperture.decision_components import reason
from market_dashboard.workstation.models import ViewMetaV1
from market_dashboard.workstation.snapshot_v2 import WorkstationSnapshotV2

MAX_SNAPSHOT_BYTES = 32 * 1024 * 1024


class SnapshotUnavailable(Exception):
    def __init__(
        self,
        code="SNAPSHOT_UNAVAILABLE",
        message="The configured snapshot is unavailable.",
    ):
        self.code = code
        self.message = message
        super().__init__(message)


class SnapshotStore:
    def __init__(self, mode="FIXTURE", *, path=None, fixture=None, now=None):
        self.mode = mode if mode in ("FIXTURE", "LOCAL_SNAPSHOT") else "LOCAL_SNAPSHOT"
        self.now = now or (lambda: datetime.now(UTC))
        self.snapshot = None
        self.failure = None
        self.path = path if mode == "LOCAL_SNAPSHOT" else None
        self._file_signature = None
        self._archive_payload = None
        try:
            if mode not in ("FIXTURE", "LOCAL_SNAPSHOT"):
                raise SnapshotUnavailable(
                    "MODE_INVALID", "Choose FIXTURE or LOCAL_SNAPSHOT explicitly."
                )
            if mode == "FIXTURE":
                if (
                    not isinstance(fixture, WorkstationSnapshotV2)
                    or fixture.mode != "FIXTURE"
                ):
                    raise SnapshotUnavailable(
                        "FIXTURE_UNAVAILABLE",
                        "The synthetic fixture could not be constructed.",
                    )
                self.snapshot = fixture
            else:
                self.snapshot = self._load(path)
                self._file_signature = self._signature()
        except SnapshotUnavailable as error:
            self.failure = error

    def _load(self, path):
        if not path:
            raise SnapshotUnavailable(
                "SNAPSHOT_PATH_REQUIRED",
                "Local mode requires an explicitly configured JSON snapshot.",
            )
        try:
            target = Path(path).resolve()
            workstation_staging = (
                target.parent.name == "workstation-local-snapshot-v1"
                and target.parent.parent.name == "aperture-staging"
                and sum("staging" in p.lower() for p in target.parts) == 1
            )
            forbidden = any(
                ("staging" in p.lower() and not workstation_staging)
                or "deepvue" in p.lower()
                for p in target.parts
            )
            forbidden = forbidden or any(
                tuple(target.parts[i : i + 2]) == ("data", folder)
                for i in range(len(target.parts))
                for folder in ("raw", "processed", "database")
            )
            if forbidden or target.suffix != ".json":
                raise SnapshotUnavailable(
                    "SNAPSHOT_PATH_REFUSED",
                    "Only a standalone workstation JSON snapshot is permitted.",
                )
            if target.stat().st_size > MAX_SNAPSHOT_BYTES:
                raise SnapshotUnavailable(
                    "SNAPSHOT_TOO_LARGE",
                    "The local snapshot exceeds the bounded size limit.",
                )
            with target.open("rb") as handle:
                raw = handle.read(MAX_SNAPSHOT_BYTES + 1)
            if len(raw) > MAX_SNAPSHOT_BYTES:
                raise SnapshotUnavailable(
                    "SNAPSHOT_TOO_LARGE",
                    "The local snapshot exceeds the bounded size limit.",
                )
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise SnapshotUnavailable(
                    "SNAPSHOT_INVALID",
                    "The local snapshot does not match the required contract.",
                )
            if payload.get("schema_version") == "workstation-snapshot-archive-v1":
                from .archive import read_snapshot

                snapshot = read_snapshot(target)
                self._archive_payload = target.parent / payload["payload"]
                if snapshot.mode != "LOCAL_SNAPSHOT":
                    raise SnapshotUnavailable("SNAPSHOT_MODE_MISMATCH")
                return snapshot
            if payload.get("schema_version") != "workstation-snapshot-v2":
                raise SnapshotUnavailable(
                    "SNAPSHOT_VERSION_UNSUPPORTED",
                    "The local snapshot schema version is unsupported.",
                )
            from market_dashboard.aperture.leadership import fingerprint

            content = {
                k: v
                for k, v in payload.items()
                if k not in ("generated_at", "logical_fingerprint")
            }
            if fingerprint(content) != payload.get("logical_fingerprint"):
                raise SnapshotUnavailable(
                    "SNAPSHOT_FINGERPRINT_MISMATCH",
                    "The local snapshot failed its logical fingerprint check.",
                )
            snapshot = WorkstationSnapshotV2.model_validate(payload)
            self._archive_payload = None
            if snapshot.mode != "LOCAL_SNAPSHOT":
                raise SnapshotUnavailable(
                    "SNAPSHOT_MODE_MISMATCH",
                    "Local mode requires a snapshot explicitly labeled LOCAL_SNAPSHOT.",
                )
            return snapshot
        except FileNotFoundError:
            raise SnapshotUnavailable(
                "SNAPSHOT_MISSING", "The configured local snapshot file is missing."
            ) from None
        except SnapshotUnavailable:
            raise
        except (OSError, ValueError, TypeError, RecursionError):
            raise SnapshotUnavailable(
                "SNAPSHOT_INVALID", "The local snapshot could not be safely validated."
            ) from None

    def _signature(self):
        if not self.path:
            return None
        stat = Path(self.path).stat()
        signature = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
        if self._archive_payload:
            payload = self._archive_payload.stat()
            signature += (payload.st_ino, payload.st_mtime_ns, payload.st_size)
        return signature

    def _reload(self):
        if self.mode != "LOCAL_SNAPSHOT" or not self.path:
            return
        try:
            signature = self._signature()
            if signature != self._file_signature:
                candidate = self._load(self.path)
                self.snapshot, self.failure = candidate, None
                self._file_signature = signature
        except OSError:
            self.failure = SnapshotUnavailable(
                "SNAPSHOT_UNAVAILABLE", "Activated snapshot file is unavailable."
            )
        except SnapshotUnavailable as error:
            self.failure = error

    def require(self):
        self._reload()
        if self.failure:
            raise self.failure
        s = self.snapshot
        if s is None:
            raise SnapshotUnavailable()
        if self.mode == "LOCAL_SNAPSHOT":
            now = self.now()
            if s.generated_at > now or s.as_of_session > now.date():
                raise SnapshotUnavailable(
                    "SNAPSHOT_FUTURE",
                    "The local snapshot is dated after the current evaluation time.",
                )
            if s.freshness.state != "FRESH" or now > s.freshness.valid_until:
                raise SnapshotUnavailable(
                    "SNAPSHOT_STALE",
                    "The local snapshot is stale or lacks explicit fresh status.",
                )
        return s

    def meta(self):
        error = None
        try:
            self.require()
        except SnapshotUnavailable as caught:
            error = caught
        s = self.snapshot
        return ViewMetaV1(
            evaluation=s.evaluation if s else None,
            mode=self.mode,
            mode_label="SYNTHETIC FIXTURE"
            if self.mode == "FIXTURE"
            else "LOCAL SNAPSHOT",
            snapshot_id=s.snapshot_id if s else None,
            as_of_session=s.as_of_session if s else None,
            action_session=s.action_session if s else None,
            freshness="STALE"
            if error and error.code == "SNAPSHOT_STALE"
            else "UNKNOWN"
            if error
            else s.freshness.state,
            reasons=(reason(error.code, error.message),)
            if error
            else s.freshness.reasons,
            fingerprint=s.logical_fingerprint if s else None,
        )
