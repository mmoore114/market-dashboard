import json
from types import SimpleNamespace

import pytest

from market_dashboard.workstation.refresh import runtime
from market_dashboard.workstation.refresh.scheduler import units


@pytest.mark.parametrize("changed", ["head", "branch", "dirty"])
def test_pinned_runtime_refuses_changed_checkout(tmp_path, monkeypatch, changed):
    def run(args, **kwargs):
        if "rev-parse" in args:
            return SimpleNamespace(
                returncode=0,
                stdout=("b" * 40 if changed == "head" else "a" * 40) + "\n",
            )
        if "symbolic-ref" in args:
            return SimpleNamespace(
                returncode=0 if changed == "branch" else 1, stdout=""
            )
        return SimpleNamespace(returncode=1 if changed == "dirty" else 0, stdout="")

    monkeypatch.setattr(runtime.subprocess, "run", run)
    with pytest.raises(ValueError, match="PINNED_RUNTIME"):
        runtime.verify_runtime(
            {"repository": str(tmp_path), "runtime_commit": "a" * 40}
        )


def test_scheduler_uses_explicit_bounded_expansion_budget(tmp_path):
    p = tmp_path / "config.json"
    config = {"repository": str(tmp_path / "release"), "coverage_manifest": "private"}
    p.write_text(json.dumps(config))
    service, timer = units(p)
    assert "TimeoutStartSec=90min" in service
    assert "OnCalendar=*:0/15" in timer
    config["refresh_timeout_minutes"] = 0
    p.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="BOUNDED_REFRESH_TIMEOUT"):
        units(p)
