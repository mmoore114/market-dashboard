#!/usr/bin/env python3
"""Explicit offline local materializer. No provider/client or environment loading."""

import argparse
import json
import shlex
import sys
from pathlib import Path

from market_dashboard.workstation.materialization.contracts import MaterializationPlanV1
from market_dashboard.workstation.materialization.io import (
    Refusal,
    describe_plan,
    read_json,
    resolve_plan,
)


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise Refusal("CLI_ARGUMENTS_INVALID")


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "audit", "build", "validate"))
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--plan-fingerprint")
    parser.add_argument("--snapshot", type=Path)
    try:
        args = parser.parse_args(argv)
        if args.mode == "validate":
            if (
                not args.snapshot
                or not args.receipt
                or args.plan
                or args.plan_fingerprint
            ):
                raise Refusal("VALIDATE_ARGUMENTS_INVALID")
            from market_dashboard.workstation.materialization.service import validate

            result = validate(args.snapshot, args.receipt)
        else:
            if not args.plan or args.snapshot:
                raise Refusal("PLAN_ARGUMENT_REQUIRED")
            plan = resolve_plan(
                MaterializationPlanV1.model_validate(read_json(args.plan))
            )
            if args.mode == "plan":
                if args.receipt or args.plan_fingerprint:
                    raise Refusal("PLAN_ARGUMENTS_INVALID")
                result = describe_plan(plan)
                result["next_command"] = shlex.join(
                    [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "audit",
                        "--plan",
                        str(args.plan.absolute()),
                    ]
                )
            elif args.mode == "audit":
                if args.receipt or args.plan_fingerprint:
                    raise Refusal("AUDIT_ARGUMENTS_INVALID")
                from market_dashboard.workstation.materialization.audit import audit

                report = audit(plan)
                result = {
                    "status": "HARD_BLOCKER" if report.hard_blockers else "READY",
                    "hard_blockers": report.hard_blockers,
                    "receipt_fingerprint": report.receipt_fingerprint,
                    "plan_fingerprint": report.plan_fingerprint,
                }
            else:
                if not args.receipt or not args.plan_fingerprint:
                    raise Refusal("BUILD_RECEIPT_AND_PLAN_FINGERPRINT_REQUIRED")
                from market_dashboard.workstation.materialization.service import build

                r = build(plan, args.receipt, args.plan_fingerprint)
                result = {
                    "status": r["status"],
                    "logical_fingerprint": r["logical_fingerprint"],
                    "output_bytes": r["output_bytes"],
                }
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 2 if result.get("hard_blockers", 0) else 0
    except Exception as e:  # noqa: BLE001 — sanitize the external I/O/replay boundary
        print(
            json.dumps(
                {
                    "status": "REFUSED",
                    "code": str(e)
                    if isinstance(e, Refusal)
                    else "INVALID_INPUT_OR_OFFLINE_OPERATION_FAILED",
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
