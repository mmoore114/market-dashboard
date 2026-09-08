"""Symbol-local views with complete shared evidence addressed in the validated graph.

The legacy V1 response expands the entire universe twice for each symbol. V2
keeps canonical local values and replaces only shared Leadership/Regime inputs
with hash-bound references. No calculation or persisted evidence is removed.
"""

from copy import deepcopy
from typing import Literal

from pydantic import Field, create_model

from market_dashboard.aperture.contracts import ContractModel
from market_dashboard.aperture.decision_contracts import (
    DecisionInputV1,
    DecisionRiskOutputV1,
)
from market_dashboard.aperture.industry_contracts import (
    DecisionInputV2,
    DecisionRiskOutputV2,
)

from .evidence_graph import Digest, EvidenceNodeV2, NodeRef
from .models import SymbolRecordV1, ViewMetaV1
from .research import DecisionReviewV1, review


class EvidenceRefV2(ContractModel):
    index: NodeRef
    id: Digest


def view_model(name, original, replacements, omitted=()):
    fields = {
        key: (field.annotation, deepcopy(field))
        for key, field in original.model_fields.items()
        if key not in omitted
    }
    fields.update(replacements)
    return create_model(name, __base__=ContractModel, **fields)


DecisionInputViewV2 = view_model(
    "DecisionInputViewV2",
    DecisionInputV1,
    {
        "schema_version": (Literal["decision-input-view-v2"], "decision-input-view-v2"),
        "leadership_ref": (EvidenceRefV2 | None, ...),
        "regime_ref": (EvidenceRefV2 | None, ...),
    },
    omitted={"leadership", "regime"},
)
DecisionOutputViewV2 = view_model(
    "DecisionOutputViewV2",
    DecisionRiskOutputV1,
    {
        "schema_version": (
            Literal["decision-output-view-v2"],
            "decision-output-view-v2",
        ),
        "inputs": (DecisionInputViewV2, ...),
    },
)
IndustryInputViewV2 = view_model(
    "IndustryInputViewV2",
    DecisionInputV2,
    {
        "schema_version": (Literal["industry-input-view-v2"], "industry-input-view-v2"),
        "leadership_ref": (EvidenceRefV2 | None, ...),
        "regime_ref": (EvidenceRefV2 | None, ...),
    },
    omitted={"leadership", "regime"},
)
IndustryOutputViewV2 = view_model(
    "IndustryOutputViewV2",
    DecisionRiskOutputV2,
    {
        "schema_version": (
            Literal["industry-output-view-v2"],
            "industry-output-view-v2",
        ),
        "inputs": (IndustryInputViewV2, ...),
    },
)
SymbolRecordV2 = view_model(
    "SymbolRecordV2",
    SymbolRecordV1,
    {
        "output": (DecisionOutputViewV2 | IndustryOutputViewV2, ...),
        "output_ref": (EvidenceRefV2, ...),
        "review": (DecisionReviewV1, ...),
    },
)


class SymbolDetailV2(ContractModel):
    schema_version: Literal["symbol-detail-v2"] = "symbol-detail-v2"
    meta: ViewMetaV1
    records: tuple[SymbolRecordV2, ...]


class EvidencePageV2(ContractModel):
    schema_version: Literal["evidence-page-v2"] = "evidence-page-v2"
    meta: ViewMetaV1
    offset: int = Field(ge=0)
    total: int = Field(ge=0)
    nodes: tuple[EvidenceNodeV2, ...]


def symbol_view(snapshot, records, meta):
    def ref(index):
        return (
            None
            if index is None
            else EvidenceRefV2(index=index, id=snapshot.evidence[index].id)
        )

    indexes = {(r.symbol, r.direction): r.output_ref for r in snapshot.record_index}
    rows = []
    for record in records:
        output = record.output
        industry = output.engine_version == "decision-risk-v2"
        input_view = IndustryInputViewV2 if industry else DecisionInputViewV2
        output_view = IndustryOutputViewV2 if industry else DecisionOutputViewV2
        inputs = {
            k: getattr(output.inputs, k)
            for k in DecisionInputV1.model_fields
            if k not in {"leadership", "regime", "schema_version"}
        }
        inputs.update(
            leadership_ref=ref(snapshot.shared.leadership_ref),
            regime_ref=ref(snapshot.shared.regime_ref),
        )
        values = {
            k: getattr(output, k)
            for k in DecisionRiskOutputV1.model_fields
            if k not in {"inputs", "schema_version"}
        }
        rows.append(
            SymbolRecordV2(
                **{
                    k: getattr(record, k)
                    for k in SymbolRecordV1.model_fields
                    if k != "output"
                },
                review=review(output),
                output=output_view(**values, inputs=input_view(**inputs)),
                output_ref=ref(
                    indexes[output.decision.symbol, output.decision.direction]
                ),
            )
        )
    return SymbolDetailV2(meta=meta, records=tuple(rows))
