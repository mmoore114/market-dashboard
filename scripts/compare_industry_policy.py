"""Read-only bounded policy comparison; never rebuilds or activates a snapshot."""

import argparse
import json
import resource
from pathlib import Path

from market_dashboard.aperture.industry import (
    evaluate_industry_decision,
    evaluate_industry_regime,
)
from market_dashboard.aperture.industry_contracts import DecisionInputV2
from market_dashboard.aperture.industry_policy import DECISION_RULES
from market_dashboard.model_validation import ModelValidationCache
from market_dashboard.workstation.archive import read_snapshot
from market_dashboard.workstation.research import research_row

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--snapshot", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--symbols", nargs="+", default=["A", "ABCL", "ABNB", "ADM", "AEM"])
args = parser.parse_args()
if len(set(args.symbols)) > 20:
    parser.error("Choose at most 20 comparison symbols")
if args.output.exists():
    parser.error("Output must be a new file")
path = args.snapshot
before = path.read_bytes()
s = read_snapshot(path)
expected = s.logical_fingerprint
print("Retained snapshot decoded with original fingerprint", flush=True)
regime = evaluate_industry_regime(s.regime.inputs, calendar=s.calendar)
cache = ModelValidationCache()
rows = []
for r in s.records:
    if r.output.decision.symbol not in args.symbols:
        continue
    o = r.output
    i = o.inputs
    v = DecisionInputV2(
        **{
            k: getattr(i, k)
            for k in type(i).model_fields
            if k not in ("schema_version", "regime")
        },
        regime=regime,
    )
    new = evaluate_industry_decision(v, calendar=s.calendar, validation_cache=cache)
    rows.append(
        {
            "symbol": o.decision.symbol,
            "stored": o.decision.state,
            "comparison": new.decision.state,
            "old_group_status": o.group.status,
            "old_rank": o.group.sub_industry.leadership_rank
            if o.group.sub_industry
            else None,
            "old_limit": o.group.rank_limit,
            "industry": new.group.industry.group_id if new.group.industry else None,
            "industry_status": new.group.status,
            "industry_rank": new.group.industry.leadership_rank
            if new.group.industry
            else None,
            "industry_population": new.group.industry.eligible_group_count
            if new.group.industry
            else None,
            "new_limit": new.group.rank_limit,
            "current_setup": research_row(r).current_setup.model_dump(mode="json"),
        }
    )
    print(
        rows[-1]["symbol"],
        rows[-1]["old_group_status"],
        rows[-1]["industry_status"],
        new.decision.state,
        flush=True,
    )
report = {
    "kind": "HISTORICAL_POLICY_COMPARISON_NOT_FRESH",
    "fingerprint": s.logical_fingerprint,
    "valid_until": s.freshness.valid_until.isoformat(),
    "versions": s.versions.model_dump(mode="json"),
    "new_policy": "decision-risk-v2",
    "new_policy_fingerprint": DECISION_RULES,
    "regime_initialization": "V2 initialized from existing completed-session inputs without V1 memory; no historical replay",
    "regime": regime.status,
    "old_regime": s.regime.status,
    "industry_paths": sum(g.group_type == "INDUSTRY" for g in s.groups),
    "industry_ranked": sum(
        g.group_type == "INDUSTRY" and g.leadership_rank is not None for g in s.groups
    ),
    "samples": rows,
    "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
}
assert path.read_bytes() == before and s.logical_fingerprint == expected
with args.output.open("x") as output:
    output.write(json.dumps(report, indent=2) + "\n")
print(
    json.dumps(
        {k: v for k, v in report.items() if k not in ("samples", "versions")}, indent=2
    ),
    flush=True,
)
