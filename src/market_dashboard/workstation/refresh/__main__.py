"""Local launch, refresh and status. No provider acquisition on API request paths."""

import argparse
import json
import os
import signal
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from .operations import status
from .report import operational_status
from .runner import refresh


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("refresh", "launch", "status"))
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        / "aperture/refresh.json",
    )
    parser.add_argument("--scheduled", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if args.command == "status":
        print(json.dumps(operational_status(config), indent=2))
        return 0
    try:
        result = refresh(config, scheduled=args.scheduled)
    except ValueError as error:
        if str(error) != "REFRESH_ALREADY_RUNNING":
            raise
        result = {
            "state": "REFRESH_ALREADY_RUNNING",
            "last_success": status(config["workspace"], datetime.now(UTC)),
        }
    print(json.dumps(result, indent=2), flush=True)
    if args.command == "refresh":
        return 2 if result["state"] == "BLOCKED" else 0
    current = status(config["workspace"], datetime.now(UTC))
    if not current["available"]:
        print("No usable current snapshot; the last successful artifact is preserved.")
        return 2
    repo = Path(config["repository"])
    env = os.environ.copy()
    env["APERTURE_REFRESH_CONFIG"] = str(args.config.resolve())
    env.update(APERTURE_MODE="LOCAL_SNAPSHOT", APERTURE_SNAPSHOT_PATH=current["path"])
    env["PATH"] = str(Path(config["node_bin"])) + os.pathsep + env["PATH"]
    children = []
    try:
        children.append(
            subprocess.Popen(
                [
                    str(repo / ".venv/bin/python"),
                    "-m",
                    "uvicorn",
                    "api.main:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8000",
                ],
                cwd=repo,
                env=env,
                start_new_session=True,
            )
        )
        children.append(
            subprocess.Popen(
                ["npm", "run", "dev", "--", "--host", "127.0.0.1"],
                cwd=repo / "web",
                env=env,
                start_new_session=True,
            )
        )
        print(
            "Workstation: http://127.0.0.1:5173 — Ctrl-C stops both services.",
            flush=True,
        )
        children[-1].wait()
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
