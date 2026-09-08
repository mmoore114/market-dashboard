"""Lossless typed normalization of the closed V1 engine-contract family.

Each canonical model becomes one immutable, content-addressed row. Nested model
fields become foreign keys; scalar fields and ordered scalar tuples are unchanged.
The registry is derived only from DecisionRiskOutputV1's declared schema, never
from a class/module name supplied by a file. No arbitrary object deserialization.
"""

from functools import reduce
from operator import or_
from types import UnionType
from typing import Annotated, Literal, Union, get_args, get_origin

from pydantic import BaseModel, Field, create_model

from market_dashboard.aperture.contracts import ContractModel
from market_dashboard.aperture.decision_contracts import DecisionRiskOutputV1
from market_dashboard.aperture.leadership import fingerprint

from .legacy_registry import CURRENT_GROUP_TYPE_CODES

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
NodeRef = Annotated[int, Field(ge=0, strict=True)]


def _registry():
    result = {}

    def visit(annotation):
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            if annotation.__name__ in result:
                return
            result[annotation.__name__] = annotation
            for field in annotation.model_fields.values():
                visit(field.annotation)
        else:
            for argument in get_args(annotation):
                visit(argument)

    visit(DecisionRiskOutputV1)
    return result


CANONICAL = _registry()
REGISTRY_FINGERPRINT = fingerprint(
    {
        "schema": DecisionRiskOutputV1.model_json_schema(),
        "columns": {
            name: tuple(model.model_fields) for name, model in sorted(CANONICAL.items())
        },
    }
)


def _reference_type(annotation, reference):
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return reference
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, UnionType):
        return reduce(or_, (_reference_type(a, reference) for a in args))
    if origin is tuple:
        return tuple[tuple(_reference_type(a, reference) for a in args)]
    return annotation


TYPE_CODES = dict(CURRENT_GROUP_TYPE_CODES)
TYPE_CODES.update(
    {
        name: len(CURRENT_GROUP_TYPE_CODES) + i
        for i, name in enumerate(sorted(set(CANONICAL) - set(CURRENT_GROUP_TYPE_CODES)))
    }
)
TYPE_NAMES = {i: name for name, i in TYPE_CODES.items()}


def _normalized_types(reference, prefix):
    result = {}
    for name, model in sorted(CANONICAL.items()):
        types = []
        for original in model.model_fields.values():
            annotation = _reference_type(original.annotation, reference)
            if original.metadata:
                annotation = Annotated[annotation, *original.metadata]
            types.append(annotation)
        result[name] = create_model(
            prefix + name,
            __base__=ContractModel,
            model_type=(
                Literal[TYPE_CODES[name] if reference is NodeRef else name],
                ...,
            ),
            fields=(tuple[tuple(types)], ...),
        )
    return result


def node_fields(value):
    return dict(
        zip(
            CANONICAL[TYPE_NAMES.get(value.model_type, value.model_type)].model_fields,
            value.fields,
            strict=True,
        )
    )


HASH_MODELS = _normalized_types(Digest, "Hashed")
NORMALIZED = _normalized_types(NodeRef, "Normalized")
NodeValue = Annotated[
    reduce(or_, NORMALIZED.values()), Field(discriminator="model_type")
]


class EvidenceNodeV2(ContractModel):
    id: Digest
    value: NodeValue


# Only unordered populations are canonicalized. Session windows, setup lifecycle
# arrays, gate order, reason order and event revisions retain their exact order.
POPULATIONS = {
    ("ResearchUniverseV1", "symbols"): lambda x: x,
    ("LeadershipOutputV1", "symbols"): lambda x: x.inputs.symbol,
    ("LeadershipOutputV1", "groups"): lambda x: (x.group_type, x.group_id),
    ("GroupEvidenceV1", "members"): lambda x: (x.group_id, x.source_symbol),
    ("RegimeInputV1", "indexes"): lambda x: x.symbol,
    ("RegimeInputV1", "breadth"): lambda x: x.symbol,
    ("RegimeInputV1", "style"): lambda x: x.symbol,
    ("StructureBreadthContextV1", "evidence"): lambda x: x.inputs.symbol,
    ("GroupGateV1", "themes"): lambda x: (x.group_type, x.group_id),
}


def node_digest(value):
    return fingerprint(value.model_dump(mode="json"))


class EvidenceBuilder:
    """Invocation-local interning; identity cache never outlives its source models."""

    def __init__(self):
        self.nodes = {}
        self.objects = {}

    def add(self, model):
        known = self.objects.get(id(model))
        if known is not None and known[0] is model:
            return known[1]
        name = type(model).__name__
        if CANONICAL.get(name) is not type(model):
            raise ValueError("Unsupported evidence model")
        values = {}
        for key in type(model).model_fields:
            value = getattr(model, key)
            ordering = POPULATIONS.get((name, key))
            if ordering is not None:
                value = tuple(sorted(value, key=ordering))
            values[key] = self._value(value)
        value = HASH_MODELS[name](model_type=name, fields=tuple(values.values()))
        digest = node_digest(value)
        node = value
        if digest in self.nodes and self.nodes[digest] != node:
            raise ValueError("Evidence digest collision")
        self.nodes[digest] = node
        self.objects[id(model)] = (model, digest)
        return digest

    def finish(self):
        addresses = {key: i for i, key in enumerate(sorted(self.nodes))}
        nodes = []
        for digest in addresses:
            value = self.nodes[digest]
            name = value.model_type
            fields = {
                key: map_references(
                    node_fields(value)[key], field.annotation, addresses.__getitem__
                )
                for key, field in CANONICAL[name].model_fields.items()
            }
            nodes.append(
                EvidenceNodeV2(
                    id=digest,
                    value=NORMALIZED[name](
                        model_type=TYPE_CODES[name], fields=tuple(fields.values())
                    ),
                )
            )
        return addresses, tuple(nodes)

    def _value(self, value):
        if isinstance(value, BaseModel):
            return self.add(value)
        if isinstance(value, tuple):
            return tuple(self._value(v) for v in value)
        return value


class EvidenceReader:
    """Validate hashes, foreign-key types, cycles and canonical model validators."""

    def __init__(self, nodes):
        self.nodes = dict(enumerate(nodes))
        ids = [node.id for node in nodes]
        if len(set(ids)) != len(nodes):
            raise ValueError("Duplicate evidence ID")
        if ids != sorted(ids):
            raise ValueError("Evidence index must be sorted by ID")
        for node in nodes:
            name = TYPE_NAMES[node.value.model_type]
            fields = {
                key: map_references(
                    node_fields(node.value)[key], field.annotation, self._digest
                )
                for key, field in CANONICAL[name].model_fields.items()
            }
            if (
                node_digest(
                    HASH_MODELS[name](model_type=name, fields=tuple(fields.values()))
                )
                != node.id
            ):
                raise ValueError("Evidence ID/content mismatch")
        self.decoded = {}
        self.visiting = set()

    def _digest(self, ref):
        if ref not in self.nodes:
            raise ValueError("Dangling evidence reference")
        return self.nodes[ref].id

    def get(self, ref, expected):
        node = self.nodes.get(ref)
        if node is None or TYPE_NAMES[node.value.model_type] != expected.__name__:
            raise ValueError("Dangling or wrong-type evidence reference")
        if ref in self.decoded:
            return self.decoded[ref]
        if ref in self.visiting:
            raise ValueError("Cyclic evidence reference")
        self.visiting.add(ref)
        values = {
            key: self._value(node_fields(node.value)[key], field.annotation)
            for key, field in expected.model_fields.items()
        }
        result = expected.model_validate(values)
        for key in expected.model_fields:
            ordering = POPULATIONS.get((expected.__name__, key))
            if ordering is not None and getattr(result, key) != tuple(
                sorted(getattr(result, key), key=ordering)
            ):
                raise ValueError("Shared population must be canonically sorted")
        self.visiting.remove(ref)
        self.decoded[ref] = result
        return result

    def _value(self, value, annotation):
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return self.get(value, annotation)
        origin, args = get_origin(annotation), get_args(annotation)
        if origin in (Union, UnionType):
            if value is None and type(None) in args:
                return None
            nonnull = [a for a in args if a is not type(None)]
            if len(nonnull) == 1:
                return self._value(value, nonnull[0])
            if all(isinstance(a, type) and issubclass(a, BaseModel) for a in nonnull):
                node = self.nodes.get(value)
                expected = next(
                    (
                        a
                        for a in nonnull
                        if node is not None
                        and a.__name__ == TYPE_NAMES[node.value.model_type]
                    ),
                    None,
                )
                if expected is None:
                    raise ValueError("Wrong-type versioned evidence reference")
                return self.get(value, expected)
        if origin is tuple:
            return tuple(
                self._value(v, args[0] if args[-1] is Ellipsis else args[i])
                for i, v in enumerate(value)
            )
        return value

    def finish(self):
        if set(self.decoded) != set(self.nodes):
            raise ValueError("Unreferenced evidence is not permitted")


def map_references(value, annotation, convert):
    """Transform only declared model references; ordinary hashes/strings stay exact."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return convert(value)
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, UnionType):
        if value is None and type(None) in args:
            return None
        nonnull = [a for a in args if a is not type(None)]
        if len(nonnull) == 1:
            return map_references(value, nonnull[0], convert)
        if all(isinstance(a, type) and issubclass(a, BaseModel) for a in nonnull):
            return convert(value)
    if origin is tuple:
        return tuple(
            map_references(v, args[0] if args[-1] is Ellipsis else args[i], convert)
            for i, v in enumerate(value)
        )
    return value
