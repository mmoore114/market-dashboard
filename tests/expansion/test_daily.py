from datetime import UTC, date, datetime

import pytest

from market_dashboard.data.expansion import daily


def test_daily_resume_after_success_uses_original_acquisition_plan(
    tmp_path, monkeypatch
):
    config = {
        "workspace": str(tmp_path),
        "coverage_manifest": str(tmp_path / "coverage.json"),
        "coverage_manifest_sha256": "a" * 64,
    }
    coverage = {
        "covered_symbols": ["AAA", "NEW", "QQQ"],
        "required_benchmarks": ["QQQ"],
    }
    window = {"market": date(2026, 9, 8), "action": date(2026, 9, 9)}
    observed = []

    class Cached:
        def __init__(self, root, key):
            self.root = root

        def batch(self, kind, keys):
            observed.append((kind, tuple(keys)))
            return {"failures": {}}

        def job(self, kind, key):
            if kind == "reference":
                return {"rows": [{"ticker": key}]}
            return {
                "rows": [
                    {"ticker": s, "date": key} for s in coverage["covered_symbols"]
                ]
            }

        def close(self):
            pass

    monkeypatch.setattr(daily, "Acquirer", Cached)
    jobs = {s: ["2026-09-04", "2026-09-08"] for s in coverage["covered_symbols"]}
    bars, controls, _ = daily.prefetch(
        config, coverage, jobs, window, controls=True, api_key="synthetic"
    )
    assert set(bars) == set(controls) == set(coverage["covered_symbols"])
    plan = tmp_path / "expanded-acquisition/2026-09-09/plan.json"
    original = plan.read_bytes()
    # Repeated supporting-input attempt after the completed prices were published.
    daily.prefetch(config, coverage, {}, window, controls=True, api_key="synthetic")
    assert plan.read_bytes() == original
    assert observed[-1] == ("reference", ("AAA", "NEW", "QQQ"))
    with pytest.raises(ValueError, match="PLAN_CHANGED"):
        daily.prefetch(
            config,
            coverage,
            {"AAA": ["2026-09-03", "2026-09-08"]},
            window,
            controls=True,
            api_key="synthetic",
        )


def test_failed_expansion_source_guard_preserves_last_snapshot_before_http(
    tmp_path, monkeypatch
):
    from market_dashboard.workstation.refresh import runner
    from market_dashboard.workstation.refresh.operations import atomic_replace

    root = tmp_path / "refresh"
    root.mkdir()
    atomic_replace(root / "current.json", b"retained")
    config = {
        "workspace": str(root),
        "group_workspace": str(tmp_path / "groups"),
        "coverage_manifest": str(tmp_path / "absent.json"),
        "coverage_manifest_sha256": "0" * 64,
    }
    monkeypatch.setattr(runner, "policy_path", lambda config: root / "current.json")
    monkeypatch.setattr(runner, "resolve_policy", lambda *args: None)
    monkeypatch.setattr(
        runner,
        "prepare",
        lambda *args, **kwargs: pytest.fail("Provider preparation forbidden"),
    )
    result = runner.refresh(config, now=datetime(2026, 9, 8, 21, tzinfo=UTC))
    assert result["state"] == "BLOCKED"
    assert (root / "current.json").read_bytes() == b"retained"
