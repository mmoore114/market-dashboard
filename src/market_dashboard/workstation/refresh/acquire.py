"""Reuse bounded provider receipts, caching successes and limiting failed attempts."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from market_dashboard.data.current_sources import fetch_staged, validate_staged


def acquire_job(root, kind, job, sessions, *, api_key=None, fetch=fetch_staged):
    key = hashlib.sha256(
        json.dumps([kind, job, sessions], sort_keys=True).encode()
    ).hexdigest()
    base = Path(root) / "acquisition" / key
    base.mkdir(parents=True, exist_ok=True)
    for child in sorted(base.iterdir()):
        if (child / "fetch.json").is_file():
            receipt = json.loads((child / "fetch.json").read_text())
            if receipt["complete"]:
                rows = validate_staged(child)
                delayed = kind == "spot" and not any(
                    r["date"] == job["end"] and r["close"] is not None for r in rows
                )
                finished = datetime.fromisoformat(
                    receipt["receipts"][-1]["finished_at"]
                )
                if not delayed or (datetime.now(UTC) - finished).total_seconds() < 900:
                    return rows, child
    # Three total attempts per exact job per UTC day, across timer/process restarts.
    day = datetime.now(UTC).date().isoformat()
    prior = list(base.glob(day + "-*"))
    for attempt in range(len(prior), min(len(prior) + 2, 3)):
        workspace = base / f"{day}-{attempt + 1}"
        plan = {"kind": kind, "jobs": [job], "sessions": sessions, "source_hashes": {}}
        result = fetch(plan, workspace, api_key=api_key)
        if result["complete"]:
            return validate_staged(workspace), workspace
    raise ValueError(f"{kind.upper()}_SOURCE_UNAVAILABLE_RETRY_BUDGET")
