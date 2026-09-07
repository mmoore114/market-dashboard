"""Bounded explicit readers and no-clobber standalone output operations."""

import errno
import hashlib
import json
import os
import tempfile
from pathlib import Path

import pandas as pd

from market_dashboard.aperture.leadership import fingerprint

from .contracts import OPTIONAL, MaterializationPlanV1

REPO = Path(__file__).resolve().parents[4]


class Refusal(ValueError):
    """Only fixed machine-readable categories may reach CLI diagnostics."""


def safe_path(path, *, output=False):
    p = Path(path)
    if (
        not p.is_absolute()
        or ".." in p.parts
        or any(c in str(p) for c in ("\x00", "?", "#", "\n", "\r"))
    ):
        raise Refusal("PATH_UNSAFE")
    if any(x.is_symlink() for x in (p, *p.parents)):
        raise Refusal("SYMLINK_REFUSED")
    if any(part in (".env", ".git", ".codex", ".agents") for part in p.parts):
        raise Refusal("PRIVATE_PATH_REFUSED")
    if output and (p == REPO or REPO in p.parents):
        raise Refusal("OUTPUT_INSIDE_REPOSITORY")
    if output and any(
        part in ("raw", "processed", "database", "security-master-refresh")
        for part in p.parts
    ):
        raise Refusal("PRODUCTION_OUTPUT_REFUSED")
    if output and any(
        "security-master" in part.lower() or "deepvue" in part.lower()
        for part in p.parts
    ):
        raise Refusal("PROVIDER_WORKSPACE_OUTPUT_REFUSED")
    if output and any("staging" in part.lower() for part in p.parts):
        layout = p if p.name == "workstation-local-snapshot-v1" else p.parent
        if (
            layout.name != "workstation-local-snapshot-v1"
            or layout.parent.name != "aperture-staging"
        ):
            raise Refusal("PROVIDER_WORKSPACE_OUTPUT_REFUSED")
    return p


def resolve_plan(plan):
    plan = MaterializationPlanV1.model_validate(plan.model_dump())
    workspace = safe_path(plan.workspace, output=True)
    output = safe_path(plan.output, output=True)
    if (
        output.parent != workspace
        or output.suffix != ".json"
        or output.name
        in (
            "readiness.json",
            "audit-receipt.json",
            "build-receipt.json",
            "failure-receipt.json",
            "plan.json",
        )
    ):
        raise Refusal("OUTPUT_LAYOUT_REFUSED")
    for a in plan.artifacts:
        for p in (*a.paths, *a.parquet_copies):
            safe_path(p)
            if p == workspace or workspace in p.parents or p in workspace.parents:
                raise Refusal("SOURCE_OUTPUT_OVERLAP")
            if "deepvue" in str(p).lower() and p.suffix.lower() != ".parquet":
                raise Refusal("RAW_DEEPVUE_REFUSED")
            if any("staging" in x.lower() for x in p.parts):
                raise Refusal("STAGED_SOURCE_REFUSED")
        if len({*a.paths, *a.parquet_copies}) != len((*a.paths, *a.parquet_copies)):
            raise Refusal("DUPLICATE_ARTIFACT_PATH")
    return plan


def plan_fingerprint(plan):
    payload = plan.model_dump(mode="json")
    payload["artifacts"] = sorted(payload["artifacts"], key=lambda a: a["role"])
    return fingerprint(payload)


def describe_plan(plan):
    plan = resolve_plan(plan)
    return {
        "plan": plan.model_dump(mode="json"),
        "plan_fingerprint": plan_fingerprint(plan),
        "absent_optional": sorted(set(OPTIONAL) - {a.role for a in plan.artifacts}),
    }


def read_handle(path):
    p = safe_path(path)
    if not p.is_file():
        raise Refusal("SOURCE_MISSING")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NOATIME", 0)
    try:
        fd = os.open(p, flags)
    except OSError as e:
        if e.errno not in (errno.EPERM, errno.EINVAL):
            raise
        fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    return os.fdopen(fd, "rb")


def file_hash(path, maximum=8 * 1024**3):
    h = hashlib.sha256()
    total = 0
    with read_handle(path) as f:
        while chunk := f.read(1024**2):
            total += len(chunk)
            if total > maximum:
                raise Refusal("SOURCE_SIZE_LIMIT")
            h.update(chunk)
    return h.hexdigest()


def read_json(path, maximum=32 * 1024**2):
    with read_handle(path) as f:
        raw = f.read(maximum + 1)
    if len(raw) > maximum:
        raise Refusal("JSON_SIZE_LIMIT")

    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise Refusal("DUPLICATE_JSON_KEY")
            result[k] = v
        return result

    return json.loads(raw, object_pairs_hook=unique)


def artifact_hashes(a, plan):
    return tuple(
        file_hash(p, plan.max_source_bytes) for p in (*a.paths, *a.parquet_copies)
    )


def _select(frame, selection):
    for item in selection:
        if item.column not in frame:
            raise Refusal("SELECTION_COLUMN_MISSING")
        frame = frame.loc[frame[item.column].astype(str) == item.value]
    return frame.reset_index(drop=True)


def read_table(a, plan, *, copies=False):
    paths = a.parquet_copies if copies else a.paths
    if a.format == "duckdb" and not copies:
        import duckdb

        # External access disabled: table names cannot invoke a view's file/network scan.
        # Read-only connections never create tables, WALs, or checkpoints.
        with duckdb.connect(
            str(paths[0]),
            read_only=True,
            config={
                "enable_external_access": False,
                "threads": 1,
                "memory_limit": "512MB",
            },
        ) as con:
            where = " AND ".join(
                f'CAST("{x.column}" AS VARCHAR) = ?' for x in a.selection
            )
            sql = (
                f'SELECT * FROM "{a.table}"'
                + (f" WHERE {where}" if where else "")
                + f" LIMIT {plan.max_rows + 1}"
            )
            frame = con.execute(sql, [x.value for x in a.selection]).fetchdf()
    else:
        import pyarrow.parquet as pq

        frames = []
        rows = 0
        for path in paths:
            with read_handle(path) as f:
                parquet = pq.ParquetFile(f)
                if parquet.metadata.num_rows + rows > plan.max_rows:
                    raise Refusal("SOURCE_ROW_LIMIT")
                part = _select(parquet.read().to_pandas(), a.selection)
            rows += len(part)
            frames.append(part)
        frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if len(frame) > plan.max_rows:
        raise Refusal("SOURCE_ROW_LIMIT")
    return frame


def frame_fingerprint(frame):
    """All columns and exact timestamp precision, independent of physical row order."""

    def scalar(value):
        if pd.isna(value):
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        if hasattr(value, "item"):
            return value.item()
        return value

    columns = sorted(frame.columns)
    rows = [
        [
            scalar(pd.Timestamp(v).date())
            if c in ("date", "snapshot_date") and not pd.isna(v)
            else scalar(v)
            for c, v in zip(columns, row)
        ]
        for row in frame[columns].itertuples(index=False, name=None)
    ]
    rows.sort(key=lambda r: json.dumps(r, sort_keys=True, allow_nan=False))
    return fingerprint({"columns": columns, "rows": rows})


def atomic_write(path, raw, validator=None):
    """A caught failure removes temporary output; existing evidence is never replaced."""
    target = safe_path(path, output=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    safe_path(target, output=True)
    if target.exists():
        raise Refusal("OUTPUT_EXISTS")
    fd, name = tempfile.mkstemp(
        prefix=".materializer-", suffix=".json", dir=target.parent
    )
    temporary = Path(name)
    renamed = False
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        if validator:
            validator(temporary)
        # Linux renameat2(RENAME_NOREPLACE) provides an atomic rename without
        # overwriting a concurrently created user artifact. Fail closed elsewhere.
        import ctypes

        libc = ctypes.CDLL(None, use_errno=True)
        rename = getattr(libc, "renameat2", None)
        if rename is None:
            raise Refusal("ATOMIC_NOREPLACE_RENAME_UNAVAILABLE")
        if rename(-100, os.fsencode(temporary), -100, os.fsencode(target), 1):
            raise OSError(ctypes.get_errno(), "Atomic publication refused")
        renamed = True
        directory = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        if renamed:
            target.unlink(missing_ok=True)
        raise
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path, value):
    atomic_write(
        path,
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode(),
    )
