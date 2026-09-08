"""Operator-approved universe expansion; all inputs and outputs remain private."""

import argparse
import fcntl
import json
from pathlib import Path

from dotenv import dotenv_values

from .acquire import Acquirer, verify_overlap
from .coverage import load_coverage, seal
from .plan import create_plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "acquire", "publish", "report"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--details",
        action="store_true",
        help="Include private per-symbol missing-history evidence in report output",
    )
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    root = Path(config["workspace"])
    if args.command == "report":
        from market_dashboard.workstation.refresh.operations import digest

        path = root / "publication/coverage.json"
        coverage = load_coverage(path, digest(path))
        result = {
            "market_session": coverage["market_session"],
            "counts": coverage["counts"],
            "coverage_sha256": digest(path),
            "unresolved": [
                r["source_symbol"]
                for r in coverage["candidates"]
                if r["identity_status"] == "REFERENCE_NOT_IN_SNAPSHOT"
            ],
        }
        if args.details:
            result["incomplete_research"] = [
                {
                    k: r[k]
                    for k in (
                        "source_symbol",
                        "history_status",
                        "provider_list_date",
                        "missing_sessions",
                        "observed_sessions",
                    )
                }
                for r in coverage["candidates"]
                if r["research_eligible"] and not r["history_ready"]
            ]
        print(json.dumps(result, indent=2))
        return
    plan = create_plan(config)
    if args.command == "plan":
        print(
            json.dumps(
                {
                    k: v
                    for k, v in plan.items()
                    if k
                    not in (
                        "candidates",
                        "local_history",
                        "source_hashes",
                        "reference_candidates",
                        "history_sessions",
                    )
                },
                indent=2,
            )
        )
        return
    with (root / "acquisition.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == "publish":
            print(json.dumps(seal(config)["counts"], indent=2))
            return
        key = dotenv_values(config["credentials_file"]).get("MASSIVE_API_KEY")
        if not key:
            raise ValueError("CREDENTIAL_UNAVAILABLE")
        a = Acquirer(root, key)
        try:
            latest = a.job("grouped", plan["market_session"])
            verify_overlap(root, latest)
            history = a.batch("grouped", plan["history_sessions"])
            if history["failures"]:
                raise ValueError("HISTORY_ACQUISITION_INCOMPLETE")
            prices = {r["ticker"]: r["close"] for r in latest["rows"]}
            unresolved = {
                r["source_symbol"]
                for r in plan["candidates"]
                if r["identity_status"] == "REFERENCE_NOT_IN_SNAPSHOT"
            }
            controls = a.batch(
                "reference",
                [
                    s
                    for s in plan["reference_candidates"]
                    if prices.get(s, 0) >= 5 or s in unresolved
                ],
            )
            splits = a.job("splits", "history-window")
            print(
                json.dumps(
                    {
                        "history": history,
                        "controls": controls,
                        "split_events": len(splits["rows"]),
                    },
                    indent=2,
                )
            )
        finally:
            a.close()


if __name__ == "__main__":
    main()
