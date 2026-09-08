"""One supported current-cohort refresh boundary, safe for timer and launch use."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from market_dashboard.workstation.materialization.bootstrap import verify_hashes
from market_dashboard.workstation.materialization.contracts import GroupScheduleV1
from market_dashboard.workstation.snapshot_v2 import WorkstationSnapshotV2

from .build import build_current
from .clocks import exchange_window, next_attempt
from .inputs import prepare
from .operations import activate, atomic_replace, digest, exclusive_lock, status


def save(path, value):
    atomic_replace(path, (json.dumps(value, indent=2, default=str) + "\n").encode())


def refresh(config, *, scheduled=False, now=None):
    now = now or datetime.now(UTC)
    root = Path(config["workspace"])
    root.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(root):
        window = exchange_window(now)
        previous = status(root, now)
        state_path = root / "refresh-status.json"
        previous_state = (
            json.loads(state_path.read_text()) if state_path.exists() else {}
        )
        due = previous_state.get("next_attempt")
        if scheduled and due and now < datetime.fromisoformat(due):
            return {**previous_state, "last_success": previous, "state": "NOT_DUE"}
        if now < window["due"] or now >= window["opening"]:
            result = {
                "state": "WAITING_FOR_COMPLETED_SESSION_WINDOW",
                "market_session": str(window["market"]),
                "next_attempt": next_attempt(now, window).isoformat(),
                "last_success": previous,
            }
            save(state_path, result)
            return result
        try:
            # No acquisition can resolve unapproved membership validity. Fail before spending.
            group_root = Path(config["group_workspace"])
            r = json.loads((group_root / "publication-receipt.json").read_text())
            verify_hashes(r["files"])
            for name in ("taxonomy", "themes"):
                schedule = GroupScheduleV1.model_validate_json(
                    (group_root / f"{name}-schedule.json").read_bytes()
                )
                if any(
                    not g.provenance.effective_session
                    <= window["action"]
                    <= g.provenance.valid_through
                    for g in schedule.snapshots
                ):
                    raise ValueError(
                        "MEMBERSHIP_VALIDITY_REQUIRED_FOR_ACTION_"
                        + str(window["action"])
                    )
            prepared = config.get("prepared_candidate")
            if not previous.get("available") and prepared and Path(prepared).exists():
                candidate = WorkstationSnapshotV2.model_validate_json(
                    Path(prepared).read_bytes()
                )
                if (candidate.as_of_session, candidate.action_session) == (
                    window["market"],
                    window["action"],
                ) and now < candidate.freshness.valid_until:
                    plan = json.loads(
                        (Path(prepared).parent / "manifest.json").read_text()
                    )
                    verify_hashes(dict(plan["artifact_hashes"]))
                    successful = activate(
                        prepared, root, expected_hash=digest(prepared), now=now
                    )
                    result = {
                        "state": "ACTIVATED_VERIFIED_CANDIDATE",
                        "last_success": successful,
                        "source_snapshot": prepared,
                        "missing_inputs": [
                            "VIX_COMPLETED_SESSION_UNPUBLISHED_VOLATILITY_UNKNOWN"
                        ],
                        "next_attempt": min(
                            now + timedelta(hours=1), window["opening"]
                        ).isoformat(),
                    }
                    save(state_path, result)
                    return result
            if (
                previous.get("available")
                and previous["market_session"] == str(window["market"])
                and due
                and now < datetime.fromisoformat(due)
            ):
                return {
                    **previous_state,
                    "state": "ALREADY_CURRENT",
                    "last_success": previous,
                }
            run = root / "runs" / now.strftime("%Y%m%dT%H%M%S%fZ")
            run.mkdir(parents=True)
            from dotenv import load_dotenv

            load_dotenv(config["credentials_file"])
            seed, loaded, hashes, paths, missing = prepare(
                config, run, window, api_key=os.environ.get("MASSIVE_API_KEY")
            )
            identity = {
                name: digest(path)
                for name, path in paths.items()
                if name not in ("database", "population")
            }
            old_inputs = root / "last-inputs.json"
            unchanged = (
                old_inputs.exists()
                and json.loads(old_inputs.read_text()).get("identity") == identity
            )
            if (
                previous.get("available")
                and previous["market_session"] == str(window["market"])
                and unchanged
            ):
                result = {
                    "state": "ALREADY_CURRENT",
                    "last_success": previous,
                    "missing_inputs": missing,
                    "next_attempt": (
                        min(now + timedelta(hours=1), window["opening"])
                        if missing
                        else next_attempt(now, window)
                    ).isoformat(),
                }
                save(state_path, result)
                return result
            evaluation = datetime.now(UTC)
            snapshot, diagnostics = build_current(
                seed,
                loaded,
                group_root=group_root,
                now=evaluation,
                window=window,
                input_hashes=hashes,
                output=run / "snapshot.json",
            )
            save(
                run / "build-receipt.json",
                {
                    "fingerprint": snapshot.logical_fingerprint,
                    "diagnostics": diagnostics,
                    "missing_inputs": missing,
                },
            )
            successful = activate(
                run / "snapshot.json", root, expected_hash=digest(run / "snapshot.json")
            )
            save(
                old_inputs,
                {
                    "bars": paths["bars"],
                    "spot": paths["spot"],
                    "population": paths["population"],
                    "hashes": {p: digest(p) for p in paths.values()},
                    "identity": identity,
                },
            )
            result = {
                "state": "COMPLETE",
                "market_session": str(window["market"]),
                "last_success": successful,
                "source_snapshot": str(run / "snapshot.json"),
                "missing_inputs": missing,
                "next_attempt": (
                    min(evaluation + timedelta(hours=1), window["opening"])
                    if missing
                    else next_attempt(evaluation, window)
                ).isoformat(),
            }
            save(state_path, result)
            return result
        except Exception as error:  # noqa: BLE001 — sanitize external/provider boundary
            # Only our fixed categories reach logs. Provider payload/credentials never do.
            text = str(error)
            category = (
                text
                if text and all(c.isupper() or c.isdigit() or c in "_-" for c in text)
                else type(error).__name__
            )
            result = {
                "state": "BLOCKED",
                "missing_inputs": [category],
                "last_success": status(root, datetime.now(UTC)),
                "market_session": str(window["market"]),
                "next_attempt": next_attempt(now, window, failed=True).isoformat(),
            }
            save(state_path, result)
            return result
