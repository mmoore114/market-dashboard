#!/usr/bin/env python3
"""Bounded current-source plan/fetch/validate. Publication is a maintenance operation."""

import argparse
import json
import os
from pathlib import Path

from market_dashboard.data.current_sources import (
    CAPS,
    fetch_staged,
    validate_plan,
    validate_staged,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("plan", "fetch", "validate"))
    parser.add_argument("--plan-json")
    parser.add_argument("--workspace", type=Path)
    args = parser.parse_args()
    try:
        if args.mode == "validate":
            if args.workspace is None:
                raise ValueError("Workspace required")
            rows = validate_staged(args.workspace)
            print(json.dumps({"state": "validated", "rows": len(rows)}))
            return 0
        plan = validate_plan(json.loads(args.plan_json))
        if args.mode == "plan":
            print(
                json.dumps(
                    {
                        "state": "planned",
                        "kind": plan["kind"],
                        "requests": len(plan["jobs"]),
                        "attempt_cap": CAPS[plan["kind"]][0],
                        "record_cap": CAPS[plan["kind"]][1],
                        "production_writes": 0,
                    }
                )
            )
            return 0
        if args.workspace is None:
            raise ValueError("Workspace required")
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        result = fetch_staged(
            plan, args.workspace, api_key=os.environ.get("MASSIVE_API_KEY")
        )
        print(
            json.dumps({k: result[k] for k in ("kind", "attempts", "rows", "complete")})
        )
        return 0 if result["complete"] else 2
    except Exception as error:  # noqa: BLE001 — sanitize provider/CLI diagnostics
        print(json.dumps({"state": "refused", "category": type(error).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
