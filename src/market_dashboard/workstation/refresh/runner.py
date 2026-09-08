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
from .membership import policy_path, resolve_policy
from .operations import activate, atomic_replace, digest, exclusive_lock, status
from .report import read_refresh_state


def save(path, value):
    atomic_replace(path, (json.dumps(value, indent=2, default=str) + "\n").encode())


def refresh(config, *, scheduled=False, now=None):
    clock = (lambda: now) if now is not None else (lambda: datetime.now(UTC))
    now = clock()
    root = Path(config["workspace"])
    root.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(root):
        window = exchange_window(now)
        previous = status(root, now)
        state_path = root / "refresh-status.json"
        previous_state, metadata_error = read_refresh_state(root)
        due = previous_state.get("next_attempt")
        if scheduled and due and now < datetime.fromisoformat(due):
            return {**previous_state, "last_success": previous, "state": "NOT_DUE"}
        if now < window["due"] or now >= window["opening"]:
            result = {
                **previous_state,
                "state": "WAITING_FOR_COMPLETED_SESSION_WINDOW",
                "market_session": str(window["market"]),
                "next_attempt": next_attempt(now, window).isoformat(),
                "last_success": previous,
            }
            save(state_path, result)
            return result
        membership_config = config if policy_path(config).exists() else None
        policy_sha = digest(policy_path(config)) if membership_config else None

        def record(result):
            result.update(
                attempt_started_at=now.isoformat(),
                attempt_finished_at=clock().isoformat(),
                attempt_outcome=result["state"],
                membership_policy_sha256=policy_sha,
                failure_reason=result.get("missing_inputs")
                if result["state"] == "BLOCKED"
                else None,
            )
            if metadata_error:
                result["recovered_status_error"] = metadata_error
            save(state_path, result)

        save(
            state_path,
            {
                **previous_state,
                "state": "RUNNING",
                "attempt_outcome": "RUNNING",
                "attempt_started_at": now.isoformat(),
                "attempt_finished_at": None,
                "last_success": previous,
            },
        )
        try:
            if membership_config:
                resolve_policy(config, now, window)  # Before any provider acquisition.
            else:
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
            if (
                not membership_config
                and not previous.get("available")
                and prepared
                and Path(prepared).exists()
            ):
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
                        "missing_inputs": successful.get("missing_inputs", []),
                        "next_attempt": min(
                            now + timedelta(hours=1), window["opening"]
                        ).isoformat(),
                    }
                    record(result)
                    return result
            if (
                previous.get("available")
                and previous["market_session"] == str(window["market"])
                and previous_state.get("membership_policy_sha256") == policy_sha
                and due
                and now < datetime.fromisoformat(due)
            ):
                result = {
                    **previous_state,
                    "state": "ALREADY_CURRENT",
                    "last_success": previous,
                }
                record(result)
                return result
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
            identity["membership_policy"] = policy_sha
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
                record(result)
                return result
            evaluation = datetime.now(UTC)
            snapshot, diagnostics = build_current(
                seed,
                loaded,
                group_root=config.get("group_workspace", root),
                now=evaluation,
                window=window,
                input_hashes=hashes,
                output=run / "snapshot.json",
                membership_config=membership_config,
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
            record(result)
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
                "last_success": status(root, clock()),
                "market_session": str(window["market"]),
                "next_attempt": next_attempt(now, window, failed=True).isoformat(),
            }
            record(result)
            return result
