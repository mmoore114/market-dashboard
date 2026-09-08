"""Read-only operational reporting, independent of snapshot validity and providers."""

import fcntl
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from .clocks import exchange_window, next_attempt
from .membership import resolve_policy
from .operations import status


def read_refresh_state(root):
    try:
        value = json.loads((Path(root) / "refresh-status.json").read_text())
        if not isinstance(value, dict) or not isinstance(value.get("state"), str):
            raise TypeError
        if not isinstance(value.get("missing_inputs", []), list) or any(
            not isinstance(v, str) for v in value.get("missing_inputs", [])
        ):
            raise ValueError
        for name in ("next_attempt", "attempt_started_at", "attempt_finished_at"):
            if (
                value.get(name)
                and datetime.fromisoformat(value[name]).utcoffset() is None
            ):
                raise ValueError
        return value, None
    except FileNotFoundError:
        return {}, "REFRESH_STATUS_MISSING"
    except (OSError, ValueError, TypeError):
        return {}, "REFRESH_STATUS_MALFORMED"


def running(root):
    # Open an existing lock read-only: status must not create even a lock file.
    try:
        with (Path(root) / "refresh.lock").open("rb") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(lock, fcntl.LOCK_UN)
        return False
    except FileNotFoundError:
        return False
    except OSError:
        return None


def scheduler_status():
    try:
        result = subprocess.run(
            [
                "systemctl",
                "--user",
                "show",
                "aperture-refresh.timer",
                "--property=LoadState,ActiveState,UnitFileState,NextElapseUSecRealtime",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
        data = dict(
            line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
        )
        return {
            "available": data.get("LoadState") == "loaded",
            "active": data.get("ActiveState"),
            "enabled": data.get("UnitFileState"),
            "next_dispatch": data.get("NextElapseUSecRealtime") or None,
        }
    except (OSError, subprocess.SubprocessError):
        return {
            "available": False,
            "reason": "USER_SCHEDULER_UNAVAILABLE",
            "next_dispatch": None,
        }


def membership_report(config, now, window=None):
    try:
        _, selected = resolve_policy(
            config, now, window or exchange_window(now), require=False
        )
        return {
            "sources": [item["status"] for item in selected],
            "error": None,
            "authority": "OPERATOR_APPROVED_REUSE_NOT_PROVIDER_RECONFIRMATION",
        }
    except (OSError, ValueError, KeyError, TypeError) as error:
        reason = str(error)
        safe = (
            reason
            if reason and all(c.isupper() or c.isdigit() or c in "_-" for c in reason)
            else type(error).__name__
        )
        return {
            "sources": [],
            "error": "MEMBERSHIP_POLICY_UNAVAILABLE_" + safe,
            "authority": "OPERATOR_APPROVED_REUSE_NOT_PROVIDER_RECONFIRMATION",
        }


def operational_status(config, *, now=None, scheduler=scheduler_status):
    now = now or datetime.now(UTC)
    root = config["workspace"]
    snapshot = status(root, now)
    state, metadata_error = read_refresh_state(root)
    window = exchange_window(now)
    membership = membership_report(config, now, window)
    missing = sorted(
        set(
            state.get("missing_inputs", [])
            + snapshot.get("missing_inputs", [])
            + [s["reason"] for s in membership["sources"] if s["reason"]]
        )
    )
    if membership["error"]:
        missing.append(membership["error"])
    is_running = running(root)
    outcome = state.get("attempt_outcome", state.get("state"))
    return {
        "reported_at": now.isoformat(),
        "snapshot": snapshot,
        "refresh_running": is_running,
        "last_refresh": {
            "attempt_started_at": state.get("attempt_started_at"),
            "attempt_finished_at": state.get("attempt_finished_at"),
            "outcome": outcome,
            "failure_reason": state.get("failure_reason")
            or (state.get("missing_inputs") if outcome == "BLOCKED" else None),
            "metadata_error": metadata_error,
            "interrupted": outcome == "RUNNING" and is_running is False,
        },
        "missing_inputs": missing,
        "membership": membership,
        "latest_completed_session": str(window["market"]),
        "next_action_session": str(window["action"]),
        "next_eligible_attempt": state.get("next_attempt")
        or (
            now
            if window["due"] <= now < window["opening"]
            else next_attempt(now, window)
        ).isoformat(),
        "next_attempt_source": "RECORDED"
        if state.get("next_attempt")
        else "CALENDAR_FALLBACK",
        "scheduler": scheduler(),
    }


def membership_maintenance(store, snapshot):
    """Read-only operational overlay, explicitly distinct from frozen snapshot evidence."""
    import os

    if store.mode != "LOCAL_SNAPSHOT" or not snapshot.groups:
        return ()
    now = store.now()
    config = {"workspace": str(Path(store.path).parent)}
    try:
        if os.environ.get("APERTURE_REFRESH_CONFIG"):
            config = json.loads(Path(os.environ["APERTURE_REFRESH_CONFIG"]).read_text())
        report = membership_report(config, now)
    except (OSError, ValueError, TypeError, KeyError):
        report = {"sources": [], "error": "MEMBERSHIP_CONFIGURATION_UNAVAILABLE"}
    result = []
    for role in ("hierarchy", "themes"):
        groups = [
            g
            for g in snapshot.groups
            if (g.group_type == "THEME") == (role == "themes")
        ]
        if not groups:
            continue
        dates = {str(g.membership.source_as_of_date) for g in groups}
        selected = next((s for s in report["sources"] if s["role"] == role), None)
        if selected:
            result.append(
                {
                    **selected,
                    "applies_to_snapshot_capture": dates == {selected["capture_date"]},
                }
            )
        else:
            for source in sorted(dates):
                result.append(
                    {
                        "role": role,
                        "capture_date": source,
                        "age_days": (
                            now.astimezone(UTC).date()
                            - datetime.fromisoformat(source).date()
                        ).days,
                        "reuse_status": "POLICY_UNAVAILABLE",
                        "reason": report["error"],
                        "original_valid_through": min(
                            g.membership.valid_through for g in groups
                        ),
                    }
                )
    return tuple(result)
