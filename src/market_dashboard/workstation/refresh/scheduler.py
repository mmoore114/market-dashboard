"""Portable user-systemd units; dispatch uses pinned XNYS rather than fixed closes."""

import json
import subprocess
from pathlib import Path


def units(config_path):
    config_path = Path(config_path).resolve()
    config = json.loads(config_path.read_text())
    repo = Path(config["repository"]).resolve()
    if any(c in str(repo) + str(config_path) for c in ("%", "\n", '"')):
        raise ValueError("UNSAFE_SYSTEMD_PATH")
    service = f'''[Unit]
Description=Aperture verified after-close refresh

[Service]
Type=oneshot
WorkingDirectory={repo}
ExecStart="{repo}/.venv/bin/python" -m market_dashboard.workstation.refresh refresh --config "{config_path}" --scheduled
TimeoutStartSec=30min
UMask=0077
'''
    timer = """[Unit]
Description=Aperture exchange-close and resume catch-up dispatcher

[Timer]
OnCalendar=*:0/15
OnStartupSec=2min
Persistent=true
AccuracySec=30s
Unit=aperture-refresh.service

[Install]
WantedBy=timers.target
"""
    return service, timer


def install(config_path, *, directory=None):
    directory = Path(directory or Path.home() / ".config/systemd/user")
    directory.mkdir(parents=True, exist_ok=True)
    for name, contents in zip(
        ("aperture-refresh.service", "aperture-refresh.timer"), units(config_path)
    ):
        path = directory / name
        if path.exists() and path.read_text() != contents:
            raise ValueError("EXISTING_SCHEDULER_CONFIGURATION_CHANGED_REVIEW_REQUIRED")
        path.write_text(contents)
    subprocess.run(
        [
            "systemd-analyze",
            "--user",
            "verify",
            str(directory / "aperture-refresh.service"),
            str(directory / "aperture-refresh.timer"),
        ],
        check=True,
    )
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(
        ["systemctl", "--user", "enable", "--now", "aperture-refresh.timer"], check=True
    )
