#!/usr/bin/env python3
"""Offline plan/simulate/validate authority workflow. No production apply or fetch."""

import argparse
import json

from market_dashboard.workstation.materialization.foundation_authority import (
    FoundationAuthorityPlanV1,
    describe_authority,
    run_authority,
    validate_authority,
)
from market_dashboard.workstation.materialization.io import Refusal


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "simulate", "validate"))
    parser.add_argument("--plan-json", required=True)
    args = parser.parse_args(argv)
    try:
        plan = FoundationAuthorityPlanV1.model_validate_json(args.plan_json)
        if args.mode == "plan":
            result = describe_authority(plan)
        elif args.mode == "simulate":
            report = run_authority(plan)
            result = {
                "status": "STAGED_AUTHORITY_NOT_PUBLISHED",
                "logical_fingerprint": report["logical_fingerprint"],
            }
        else:
            result = validate_authority(plan)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:  # noqa: BLE001 — never expose proprietary rows/paths in errors
        print(
            json.dumps(
                {
                    "status": "REFUSED",
                    "code": str(exc)
                    if isinstance(exc, Refusal)
                    else "INVALID_AUTHORITY_OPERATION",
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
