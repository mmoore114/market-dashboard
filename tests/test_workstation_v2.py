"""V2 lossless projection, reference integrity, migration and contract parity."""

import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from api.main import create_app
from market_dashboard.aperture.decision_contracts import Direction, SizingProposalV1
from market_dashboard.aperture.decision_risk import evaluate_decision
from market_dashboard.aperture.leadership import fingerprint
from market_dashboard.aperture.rules import load_aperture_rules
from market_dashboard.workstation import projections
from market_dashboard.workstation.evidence_graph import (
    CANONICAL,
    POPULATIONS,
    TYPE_NAMES,
    EvidenceBuilder,
    EvidenceReader,
)
from market_dashboard.workstation.fixtures import fixture_arguments
from market_dashboard.workstation.models import seal_snapshot
from market_dashboard.workstation.snapshot_v2 import (
    WorkstationSnapshotV2,
    materialize_v2,
    sizing_input,
)
from market_dashboard.workstation.store import MAX_SNAPSHOT_BYTES, SnapshotStore


@pytest.fixture(scope="module")
def inputs():
    return fixture_arguments(load_aperture_rules(Path("config/aperture_rules_v1.yaml")))


def convert(values):
    return materialize_v2(
        **values,
        universe=values["regime"].inputs.universe,
        leadership=values["records"][0].output.inputs.leadership,
    )


@pytest.fixture(scope="module")
def v2(inputs):
    return convert(inputs)


def exact_fields(source, decoded):
    """Check every leaf, not just a hand-picked subset of visible metrics."""
    if isinstance(source, BaseModel):
        assert type(source) is type(decoded)
        for key in type(source).model_fields:
            value = getattr(source, key)
            order = POPULATIONS.get((type(source).__name__, key))
            if order is not None:
                value = tuple(sorted(value, key=order))
            exact_fields(value, getattr(decoded, key))
    elif isinstance(source, tuple):
        assert len(source) == len(decoded)
        for a, b in zip(source, decoded, strict=True):
            exact_fields(a, b)
    else:
        assert source == decoded


def test_every_copied_field_has_exact_canonical_source(inputs, v2):
    for before, after in zip(inputs["records"], v2.records, strict=True):
        exact_fields(before, after)
    exact_fields(inputs["regime"], v2.regime)
    exact_fields(inputs["groups"], v2.groups)
    exact_fields(inputs["rules"], v2.rules)
    assert not any(
        isinstance(getattr(r, k), BaseModel)
        for r in v2.record_index
        for k in type(r).model_fields
    )
    # All reachable types have a closed, typed tuple schema. No JSON/dict payload
    # can bypass the canonical field validators during resolution.
    assert all(node.value.model_config["frozen"] for node in v2.evidence)
    assert set(TYPE_NAMES.values()) == set(CANONICAL)


def test_frozen_and_explicit_null(v2):
    with pytest.raises(ValidationError):
        v2.snapshot_id = "changed"
    with pytest.raises(ValidationError):
        v2.record_index[0].symbol = "changed"
    with pytest.raises(ValidationError):
        v2.evidence[0].value.fields = ()
    payload = v2.model_dump(mode="json")
    payload["extra"] = "not allowed"
    with pytest.raises(ValidationError):
        WorkstationSnapshotV2.model_validate(payload)
    assert v2.records[0].volume is None
    assert v2.records[0].output.inputs.features.close is None
    restored = WorkstationSnapshotV2.model_validate_json(v2.model_dump_json())
    assert restored.model_dump_json() == v2.model_dump_json()


def test_shared_evidence_is_stored_once(v2):
    types = [TYPE_NAMES[n.value.model_type] for n in v2.evidence]
    for name in (
        "LeadershipOutputV1",
        "RegimeOutputV1",
        "RegimeInputV1",
        "ResearchUniverseV1",
        "ApertureRules",
        "StrengthSourceV1",
    ):
        assert types.count(name) == 1
    assert types.count("StrengthEvidenceV1") == 120
    assert types.count("GroupEvidenceV1") == len(v2.groups)
    assert types.count("DecisionRiskOutputV1") == 12
    assert len(v2.evidence) == len({n.id for n in v2.evidence})
    # Read-only in-memory hydration also shares these population objects.
    assert all(r.output.inputs.regime is v2.regime for r in v2.records)


def test_order_generation_whitespace_and_mapping_order(inputs, v2):
    reversed_values = {
        **inputs,
        "records": tuple(reversed(inputs["records"])),
        "groups": tuple(reversed(inputs["groups"])),
        "generated_at": inputs["generated_at"] + timedelta(seconds=1),
    }
    changed = convert(reversed_values)
    assert changed.logical_fingerprint == v2.logical_fingerprint
    assert changed.context_id == v2.context_id
    payload = dict(reversed(list(v2.model_dump(mode="json").items())))
    restored = WorkstationSnapshotV2.model_validate_json(json.dumps(payload, indent=3))
    assert restored.logical_fingerprint == v2.logical_fingerprint
    values = {
        **inputs,
        "records": (
            inputs["records"][0].model_copy(
                update={"display_name": "Different fictional name"}
            ),
            *inputs["records"][1:],
        ),
    }
    assert convert(values).logical_fingerprint != v2.logical_fingerprint


def test_reordered_shared_populations_have_same_ids(inputs, v2):
    leader = inputs["regime"].inputs.leadership
    universe = leader.universe.model_copy(
        update={"symbols": tuple(reversed(leader.universe.symbols))}
    )
    groups = tuple(
        g.model_copy(update={"members": tuple(reversed(g.members))})
        for g in reversed(leader.groups)
    )
    leader = leader.model_copy(
        update={
            "symbols": tuple(reversed(leader.symbols)),
            "groups": groups,
            "universe": universe,
        }
    )
    regime = inputs["regime"].model_copy(
        update={
            "inputs": inputs["regime"].inputs.model_copy(
                update={
                    "universe": universe,
                    "leadership": leader,
                    "breadth": tuple(reversed(inputs["regime"].inputs.breadth)),
                }
            )
        }
    )
    records = tuple(
        r.model_copy(
            update={
                "output": r.output.model_copy(
                    update={
                        "inputs": r.output.inputs.model_copy(
                            update={
                                "regime": regime,
                                "leadership": leader,
                                "universe": r.output.inputs.universe.model_copy(
                                    update={"universe": universe}
                                ),
                            }
                        )
                    }
                )
            }
        )
        for r in inputs["records"]
    )
    rebuilt = convert(
        {**inputs, "regime": regime, "groups": groups, "records": records}
    )
    assert rebuilt.logical_fingerprint == v2.logical_fingerprint


@pytest.mark.parametrize(
    "mutation",
    [
        "source",
        "symbol",
        "date",
        "action",
        "calendar",
        "universe",
        "leadership",
        "group",
        "existing_group",
        "regime_gate",
        "sizing",
        "extension",
        "setup",
        "output_calendar",
    ],
)
def test_rejects_inconsistent_canonical_copies(inputs, mutation):
    row = inputs["records"][-1]
    out, i = row.output, row.output.inputs
    if mutation == "source":
        i = i.model_copy(
            update={
                "features": i.features.model_copy(
                    update={
                        "source": i.features.source.model_copy(
                            update={"dataset_id": "other"}
                        )
                    }
                )
            }
        )
    if mutation == "symbol":
        i = i.model_copy(
            update={"features": i.features.model_copy(update={"symbol": "OTHER"})}
        )
    if mutation == "date":
        i = i.model_copy(
            update={
                "features": i.features.model_copy(
                    update={"session_date": inputs["action_session"]}
                )
            }
        )
    if mutation == "action":
        i = i.model_copy(update={"action_session": inputs["as_of_session"]})
    if mutation == "calendar":
        i = i.model_copy(
            update={
                "features": i.features.model_copy(
                    update={"calendar_fingerprint": "0" * 64}
                )
            }
        )
    if mutation == "universe":
        i = i.model_copy(
            update={
                "universe": i.universe.model_copy(
                    update={
                        "universe": i.universe.universe.model_copy(
                            update={"policy_version": "other"}
                        )
                    }
                )
            }
        )
    if mutation == "leadership":
        i = i.model_copy(
            update={
                "leadership": i.leadership.model_copy(
                    update={"symbols": i.leadership.symbols[:-1]}
                )
            }
        )
    if mutation == "group":
        out = out.model_copy(
            update={
                "group": out.group.model_copy(
                    update={
                        "sub_industry": out.group.sub_industry.model_copy(
                            update={"group_id": "dangling"}
                        )
                    }
                )
            }
        )
    if mutation == "existing_group":
        other = next(
            g
            for g in inputs["groups"]
            if g.group_type == "SUB_INDUSTRY"
            and g.group_id != out.group.sub_industry.group_id
        )
        out = out.model_copy(
            update={"group": out.group.model_copy(update={"sub_industry": other})}
        )
    if mutation == "regime_gate":
        out = out.model_copy(
            update={"regime": out.regime.model_copy(update={"eligible": False})}
        )
    if mutation == "sizing":
        out = out.model_copy(
            update={
                "sizing": out.sizing.model_copy(
                    update={
                        "inputs": out.sizing.inputs.model_copy(
                            update={"direction": "SHORT"}
                        )
                    }
                )
            }
        )
    if mutation == "extension":
        out = out.model_copy(
            update={
                "extension": out.extension.model_copy(
                    update={
                        "inputs": out.extension.inputs.model_copy(
                            update={"direction": "SHORT"}
                        )
                    }
                )
            }
        )
    if mutation == "setup":
        i = i.model_copy(
            update={
                "setups": i.setups.model_copy(
                    update={
                        "inputs": i.setups.inputs.model_copy(update={"symbol": "OTHER"})
                    }
                )
            }
        )
    if mutation == "output_calendar":
        out = out.model_copy(update={"action_calendar_fingerprint": "0" * 64})
    row = row.model_copy(update={"output": out.model_copy(update={"inputs": i})})
    with pytest.raises((ValidationError, ValueError)):
        convert({**inputs, "records": (*inputs["records"][:-1], row)})


@pytest.mark.parametrize(
    "mutation",
    [
        "dangling",
        "wrong_type",
        "duplicate",
        "unsorted",
        "extra",
        "arity",
        "context",
        "registry",
        "record_duplicate",
    ],
)
def test_rejects_invalid_index_and_schemas(v2, mutation):
    p = v2.model_dump(mode="json")
    if mutation == "dangling":
        p["record_index"][0]["output_ref"] = len(p["evidence"])
    if mutation == "wrong_type":
        p["record_index"][0]["output_ref"] = p["shared"]["source_ref"]
    if mutation == "duplicate":
        p["evidence"].append(p["evidence"][0])
    if mutation == "unsorted":
        p["evidence"].reverse()
    if mutation == "extra":
        p["evidence"][0]["value"]["extra"] = 1
    if mutation == "arity":
        p["evidence"][0]["value"]["fields"].pop()
    if mutation == "context":
        p["record_index"][0]["context_ref"] = "0" * 64
    if mutation == "registry":
        p["shared"]["registry_fingerprint"] = "0" * 64
    if mutation == "record_duplicate":
        p["record_index"].append(p["record_index"][0])
    p["logical_fingerprint"] = fingerprint(
        {k: v for k, v in p.items() if k not in ("generated_at", "logical_fingerprint")}
    )
    with pytest.raises((ValidationError, ValueError)):
        WorkstationSnapshotV2.model_validate(p)


def test_unreferenced_nodes_rejected(inputs):
    builder = EvidenceBuilder()
    root = builder.add(inputs["source"])
    builder.add(inputs["rules"])
    addresses, nodes = builder.finish()
    reader = EvidenceReader(nodes)
    reader.get(addresses[root], type(inputs["source"]))
    with pytest.raises(ValueError, match="Unreferenced"):
        reader.finish()


def test_public_views_equal_v1_and_openapi_unchanged(inputs, v2):
    old = seal_snapshot(**inputs)
    meta = SnapshotStore(fixture=v2).meta()
    assert projections.brief(old, meta) == projections.brief(v2, meta)
    for sort in projections.SORT_FIELDS:
        for order in ("asc", "desc"):
            assert projections.tape(
                old, meta, sort=sort, order=order
            ) == projections.tape(v2, meta, sort=sort, order=order)
    assert projections.rules_view(old, meta) == projections.rules_view(v2, meta)
    assert create_app(SnapshotStore(fixture=v2)).openapi() == json.loads(
        Path("api/openapi.json").read_text()
    )


def test_snapshot_schema_catalog_and_input_immutability(inputs):
    from api.export_snapshot_schema import document

    assert Path("docs/workstation-snapshot-v2.schema.json").read_text() == document()
    before = tuple(r.model_dump_json() for r in inputs["records"])
    regime_before = inputs["regime"].model_dump_json()
    convert(inputs)
    assert before == tuple(r.model_dump_json() for r in inputs["records"])
    assert regime_before == inputs["regime"].model_dump_json()


def test_v1_and_oversized_local_refusal(inputs, v2, tmp_path):
    path = tmp_path / "snapshot.json"
    old = seal_snapshot(**inputs)
    path.write_text(old.model_dump_json())
    store = SnapshotStore("LOCAL_SNAPSHOT", path=path)
    assert store.failure.code == "SNAPSHOT_VERSION_UNSUPPORTED"
    assert SnapshotStore(fixture=old).failure.code == "FIXTURE_UNAVAILABLE"
    with path.open("wb") as f:
        f.truncate(MAX_SNAPSHOT_BYTES + 1)
    assert (
        SnapshotStore("LOCAL_SNAPSHOT", path=path).failure.code == "SNAPSHOT_TOO_LARGE"
    )


def test_exact_short_adapter_and_refusal(inputs, v2):
    proposal = SizingProposalV1(
        entry=104, stop=107.2, account_equity=25000, available_buying_power=1000
    )
    with pytest.raises(ValueError, match="SIZER_DIRECTION_UNAVAILABLE"):
        sizing_input(v2, "SIM110", "SHORT", proposal)
    original = next(
        r for r in inputs["records"] if r.output.decision.symbol == "SIM110"
    )
    output = evaluate_decision(
        original.output.inputs.model_copy(
            update={"direction": Direction.SHORT, "sizing": proposal}
        ),
        calendar=inputs["calendar"],
    )
    values = {
        **inputs,
        "records": (*inputs["records"], original.model_copy(update={"output": output})),
    }
    values.pop("funnel")
    snapshot = convert(values)
    result = sizing_input(snapshot, "SIM110", "SHORT", proposal)
    assert result == output.sizing.inputs
    from market_dashboard.aperture import decision_components

    client = TestClient(create_app(SnapshotStore(fixture=snapshot)))
    with patch.object(
        decision_components, "size_idea", wraps=decision_components.size_idea
    ) as spy:
        response = client.post(
            "/api/v1/sizer",
            json={"symbol": "SIM110", "direction": "SHORT", **proposal.model_dump()},
        )
        assert response.status_code == 200
        assert spy.call_args.args[0] == result


def test_two_directions_cannot_disagree_on_symbol_event_context(inputs):
    original = next(
        r for r in inputs["records"] if r.output.decision.symbol == "SIM110"
    )
    proposal = SizingProposalV1(
        entry=104, stop=107.2, account_equity=25000, available_buying_power=1000
    )
    changed = original.output.inputs.model_copy(
        update={
            "direction": Direction.SHORT,
            "sizing": proposal,
            "event_coverage": original.output.inputs.event_coverage.model_copy(
                update={"source": "different-synthetic-source"}
            ),
        }
    )
    output = evaluate_decision(changed, calendar=inputs["calendar"])
    values = {
        **inputs,
        "records": (*inputs["records"], original.model_copy(update={"output": output})),
    }
    values.pop("funnel")
    with pytest.raises(ValidationError, match="across directions"):
        convert(values)
