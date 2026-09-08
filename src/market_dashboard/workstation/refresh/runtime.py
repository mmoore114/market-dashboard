"""Optional pinned deployment guard, evaluated before scheduled acquisition."""

import subprocess
from pathlib import Path


def verify_runtime(config):
    revision = config.get("runtime_commit")
    if revision is None:
        return
    repository = Path(config["repository"]).resolve()

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repository), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    head = git("rev-parse", "HEAD")
    branch = git("symbolic-ref", "-q", "HEAD")
    dirty = git("diff", "--quiet", "HEAD", "--")
    if (
        head.returncode
        or head.stdout.strip() != revision
        or branch.returncode != 1
        or dirty.returncode
    ):
        raise ValueError("PINNED_RUNTIME_REVISION_REQUIRED")
