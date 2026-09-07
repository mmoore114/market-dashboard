#!/usr/bin/env python3
"""Explicit offline foundation reconciliation; no provider or publication modes."""

import argparse
import json

from market_dashboard.workstation.materialization.io import Refusal
from market_dashboard.workstation.materialization.reconciliation import (
    ReconciliationPlanV1,
    describe_reconciliation,
    reconcile,
    validate_reconciliation,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=("reconcile-plan", "reconcile", "reconcile-validate")
    )
    # Literal JSON keeps planning genuinely free of file and database reads.
    parser.add_argument("--plan-json", required=True)
    args = parser.parse_args(argv)
    try:
        plan = ReconciliationPlanV1.model_validate_json(args.plan_json)
        if args.mode == "reconcile-plan":
            result = describe_reconciliation(plan)
        elif args.mode == "reconcile":
            report = reconcile(plan)
            result = {
                "status": "RECONCILED_NOT_BUILD_READY",
                "logical_fingerprint": report["logical_fingerprint"],
                "findings": len(report["evidence"]["ledger"]),
            }
        else:
            result = validate_reconciliation(plan)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as e:  # noqa: BLE001 — no proprietary exception contents
        print(
            json.dumps(
                {
                    "status": "REFUSED",
                    "code": str(e)
                    if isinstance(e, Refusal)
                    else "INVALID_OFFLINE_RECONCILIATION",
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
