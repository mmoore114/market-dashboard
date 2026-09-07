"""Immutable normalized snapshot and pure canonical-output materialization."""

from datetime import date, datetime
from types import MappingProxyType
from typing import Literal

from pydantic import Field, PrivateAttr, model_validator

from market_dashboard.aperture.contracts import ContractModel
from market_dashboard.aperture.decision_contracts import (
    DecisionRiskOutputV1,
    Direction,
    SizingInputV1,
)
from market_dashboard.aperture.decision_policy import validate_rules
from market_dashboard.aperture.decision_risk import regime_gate
from market_dashboard.aperture.leadership import fingerprint
from market_dashboard.aperture.leadership_contracts import (
    GroupEvidenceV1,
    LeadershipOutputV1,
    ResearchUniverseV1,
    StrengthSourceV1,
)
from market_dashboard.aperture.regime import calendar_hash
from market_dashboard.aperture.regime_contracts import RegimeOutputV1
from market_dashboard.aperture.rules import ApertureRules
from market_dashboard.data.security_identity import MarketDataSymbol
from market_dashboard.workstation.evidence_graph import (
    REGISTRY_FINGERPRINT,
    Digest,
    EvidenceBuilder,
    EvidenceNodeV2,
    EvidenceReader,
    NodeRef,
)
from market_dashboard.workstation.models import (
    EvaluationV1,
    FreshnessV1,
    FunnelV1,
    Mode,
    SymbolRecordV1,
    VersionsV1,
)


class CompactRecordV2(ContractModel):
    symbol: str
    direction: Direction
    display_name: str
    volume: float | None = Field(ge=0)
    volume_reason: str | None
    context_ref: Digest
    output_ref: NodeRef


from .legacy_registry import LEGACY_REGISTRY_FINGERPRINT, LEGACY_TYPE_CODES


class SharedContextV2(ContractModel):
    registry_fingerprint: Literal[REGISTRY_FINGERPRINT, LEGACY_REGISTRY_FINGERPRINT] = (
        REGISTRY_FINGERPRINT
    )
    source_ref: NodeRef
    universe_ref: NodeRef
    leadership_ref: NodeRef | None
    regime_ref: NodeRef
    rules_ref: NodeRef
    group_refs: tuple[NodeRef, ...]
    calendar: tuple[date, ...]
    versions: VersionsV1


def context_digest(shared, evidence):
    """Bind content IDs, never merely physical table addresses."""
    values = shared.model_dump(mode="json")
    for key in (
        "source_ref",
        "universe_ref",
        "leadership_ref",
        "regime_ref",
        "rules_ref",
    ):
        ref = values[key]
        if ref is not None:
            if ref >= len(evidence):
                raise ValueError("Dangling shared reference")
            values[key] = evidence[ref].id
    if any(ref >= len(evidence) for ref in shared.group_refs):
        raise ValueError("Dangling shared group reference")
    values["group_refs"] = [evidence[ref].id for ref in shared.group_refs]
    return fingerprint(values)


class WorkstationSnapshotV2(ContractModel):
    schema_version: Literal["workstation-snapshot-v2"] = "workstation-snapshot-v2"
    snapshot_id: str = Field(min_length=1)
    generated_at: datetime
    evaluation: EvaluationV1 | None = Field(
        default=None, exclude_if=lambda v: v is None
    )
    as_of_session: date
    action_session: date
    mode: Mode
    freshness: FreshnessV1
    shared: SharedContextV2
    context_id: Digest
    funnel: FunnelV1
    record_index: tuple[CompactRecordV2, ...]
    evidence: tuple[EvidenceNodeV2, ...]
    logical_fingerprint: Digest
    _objects: object = PrivateAttr()
    _records: tuple[SymbolRecordV1, ...] = PrivateAttr()

    @model_validator(mode="after")
    def integrity(self):
        if self.shared.registry_fingerprint == LEGACY_REGISTRY_FINGERPRINT and (
            self.shared.versions.structure != "structure-engine-v1"
            or any(
                n.value.model_type not in LEGACY_TYPE_CODES.values()
                for n in self.evidence
            )
        ):
            raise ValueError("Legacy registry cannot contain V2 engine evidence")
        if self.evaluation:
            self.evaluation.validate_snapshot(
                self.as_of_session, self.action_session, self.generated_at
            )
        if self.generated_at.utcoffset() is None:
            raise ValueError("Generated timestamp must be aware")
        calendar = self.shared.calendar
        if not calendar or tuple(sorted(set(calendar))) != calendar:
            raise ValueError("Calendar must contain increasing unique sessions")
        positions = {d: i for i, d in enumerate(calendar)}
        t = self.as_of_session
        if t not in positions or positions.get(self.action_session) != positions[t] + 1:
            raise ValueError("Action must be exact T+1")
        if context_digest(self.shared, self.evidence) != self.context_id:
            raise ValueError("Shared context reference mismatch")
        reader = EvidenceReader(self.evidence)
        c = self.shared
        source = reader.get(c.source_ref, StrengthSourceV1)
        universe = reader.get(c.universe_ref, ResearchUniverseV1)
        leadership = (
            reader.get(c.leadership_ref, LeadershipOutputV1)
            if c.leadership_ref
            else None
        )
        regime = reader.get(c.regime_ref, RegimeOutputV1)
        rules = reader.get(c.rules_ref, ApertureRules)
        groups = tuple(reader.get(ref, GroupEvidenceV1) for ref in c.group_refs)
        member_groups = {}
        for group in groups:
            for member in group.members:
                if not member.non_security and member.market_data_symbol is not None:
                    member_groups.setdefault(member.market_data_symbol, []).append(
                        group
                    )
        validate_rules(rules)
        prefix = calendar_hash(calendar, t)
        action_prefix = calendar_hash(calendar, self.action_session)
        p = universe.provenance
        if p.bootstrap:
            if not self.evaluation or self.evaluation.bootstrap != p.bootstrap:
                raise ValueError("Bootstrap provenance missing or contradictory")
            if p.bootstrap.market_as_of_session != t:
                raise ValueError("Retrospective bootstrap snapshot prohibited")
            if set(dict(p.bootstrap.first_observations)) != set(universe.symbols):
                raise ValueError("Bootstrap observation population mismatch")
        elif self.evaluation and self.evaluation.bootstrap:
            raise ValueError("Bootstrap membership provenance required")
        if not p.supports_calculation(t) or p.effective_session not in positions:
            raise ValueError("Universe effective interval mismatch")
        if universe.policy_version != rules.universe_policy_version:
            raise ValueError("Universe policy mismatch")
        if (
            regime.inputs.session_date,
            regime.inputs.source,
            regime.inputs.universe,
            regime.inputs.calendar_fingerprint,
            regime.rules_fingerprint,
        ) != (t, source, universe, prefix, c.versions.regime_fingerprint):
            raise ValueError("Shared regime alignment mismatch")
        if regime.inputs.leadership != leadership:
            raise ValueError("Contradictory shared Leadership copies")
        group_keys = [(g.group_type, g.group_id) for g in groups]
        if group_keys != sorted(set(group_keys)):
            raise ValueError("Duplicate or unordered shared group key")
        for g in groups:
            if (
                g.session_date != t
                or not g.membership.effective_session <= t <= g.membership.valid_through
            ):
                raise ValueError("Group session/effective interval mismatch")
            if g.membership.effective_session not in positions:
                raise ValueError("Group calendar mismatch")
            if len({m.source_symbol for m in g.members}) != len(g.members) or any(
                m.group_id != g.group_id for m in g.members
            ):
                raise ValueError("Duplicate or contradictory group members")
        strengths = {}
        if leadership is not None:
            if (
                leadership.session_date,
                leadership.source,
                leadership.universe,
                leadership.calendar_fingerprint,
                leadership.rules_fingerprint,
                leadership.groups,
            ) != (
                t,
                source,
                universe,
                prefix,
                c.versions.leadership_fingerprint,
                groups,
            ):
                raise ValueError("Shared Leadership alignment mismatch")
            strengths = {e.inputs.symbol: e for e in leadership.symbols}
            if len(strengths) != len(leadership.symbols) or set(strengths) != set(
                universe.symbols
            ):
                raise ValueError("Leadership population mismatch")
            for e in leadership.symbols:
                if (
                    e.inputs.session_date,
                    e.inputs.source,
                    e.universe,
                    e.universe_policy_version,
                ) != (t, source, p, universe.policy_version):
                    raise ValueError("Strength provenance mismatch")
                if any(
                    (r.universe_snapshot_id, r.universe_policy_version)
                    != (p.snapshot_id, universe.policy_version)
                    for r in e.components
                ):
                    raise ValueError("Strength component provenance mismatch")
        keys = [(r.symbol, r.direction) for r in self.record_index]
        if keys != sorted(set(keys)):
            raise ValueError("Duplicate or unordered symbol/direction key")
        counts = {k: 0 for k in ("NONE", "WATCH", "TRADE", "ACT")}
        records = []
        per_symbol = {}
        expected_regime_gate = None
        shared_structure = (
            {e.inputs.symbol: e for e in regime.inputs.structure.evidence}
            if regime.inputs.structure
            else {}
        )
        members = set(universe.symbols)
        basis = source.model_dump(exclude={"schema_version", "calendar_id"})
        for record in self.record_index:
            MarketDataSymbol(record.symbol)
            if record.context_ref != self.context_id:
                raise ValueError("Record shared context mismatch")
            out = reader.get(record.output_ref, DecisionRiskOutputV1)
            i, f = out.inputs, out.inputs.features
            symbol_context = (
                f,
                i.structure,
                i.setups,
                i.universe,
                i.events,
                i.event_coverage,
                i.completed_at,
            )
            if f.symbol in per_symbol and per_symbol[f.symbol] != symbol_context:
                raise ValueError("Contradictory symbol evidence across directions")
            per_symbol[f.symbol] = symbol_context
            key = (record.symbol, record.direction)
            if (out.decision.symbol, out.decision.direction) != key or (
                f.symbol,
                i.direction,
            ) != key:
                raise ValueError("Record symbol/direction mismatch")
            if (f.session_date, i.action_session, f.source, f.calendar_fingerprint) != (
                t,
                self.action_session,
                source,
                prefix,
            ):
                raise ValueError("Record date/source/calendar mismatch")
            if i.completed_at.date() != t:
                raise ValueError("Completed-close timestamp mismatch")
            if (
                i.rules != rules
                or i.regime != regime
                or i.leadership != leadership
                or i.universe.universe != universe
            ):
                raise ValueError("Contradictory repeated shared evidence")
            u = i.universe
            if (
                u.symbol,
                u.session_date,
                u.source,
                u.calendar_fingerprint,
                u.aperture_rules_fingerprint,
                u.exposure_policy_version,
            ) != (
                f.symbol,
                t,
                source,
                prefix,
                rules.logical_fingerprint,
                rules.exposure_policy_version,
            ):
                raise ValueError("Record universe membership identity mismatch")
            if u.memberships.equity_research.eligible != (f.symbol in members):
                raise ValueError("Research membership mismatch")
            if (
                out.calendar_id,
                out.calendar_fingerprint,
                out.action_calendar_fingerprint,
                out.aperture_rules_fingerprint,
            ) != (source.calendar_id, prefix, action_prefix, rules.logical_fingerprint):
                raise ValueError("Output calendar/rules identity mismatch")
            for e, version in (
                (i.structure, c.versions.structure_fingerprint),
                (i.setups, c.versions.setup_fingerprint),
            ):
                if e is not None and (
                    e.inputs.symbol,
                    e.inputs.session_date,
                    e.inputs.source.model_dump(),
                    e.rules_fingerprint,
                    e.inputs.close,
                    e.inputs.atr14,
                ) != (f.symbol, t, basis, version, f.close, f.wilder_atr14):
                    raise ValueError("Structure/Setup identity or value mismatch")
            engine_positions = p.engine_positions(calendar, f.symbol)
            if i.structure is not None:
                s = i.structure.inputs
                if (
                    s.sma50 != f.sma50
                    or s.prior_sessions != engine_positions[t]
                    or (
                        s.bar_timestamp_utc is not None
                        and s.bar_timestamp_utc > i.completed_at
                    )
                ):
                    raise ValueError("Structure calendar/price/timestamp mismatch")
            if (
                f.symbol in shared_structure
                and i.structure != shared_structure[f.symbol]
            ):
                raise ValueError("Contradictory shared Structure evidence")
            if i.setups is not None:
                self._setup_integrity(i, engine_positions)
            strength = strengths.get(f.symbol)
            if strength is not None:
                if (
                    out.strength.RS_comp,
                    out.strength.RS_rotation,
                    out.strength.rotation_delta,
                ) != (strength.RS_comp, strength.RS_rotation, strength.rotation_delta):
                    raise ValueError("Strength gate contradicts symbol components")
                context = strength.inputs.context.structure_state
                if context is not None and (
                    i.structure is None
                    or i.structure.error is not None
                    or context != i.structure.state
                ):
                    raise ValueError("Strength Structure context mismatch")
            for group in (out.group.sub_industry, *out.group.themes):
                if group is not None and group not in groups:
                    raise ValueError("Group gate reference mismatch")
            memberships = member_groups.get(f.symbol, ())
            sub_industries = tuple(
                g for g in memberships if g.group_type == "SUB_INDUSTRY"
            )
            expected_sub = sub_industries[0] if len(sub_industries) == 1 else None
            if out.group.sub_industry != expected_sub or out.group.themes != tuple(
                g for g in memberships if g.group_type == "THEME"
            ):
                raise ValueError("Group gate contradicts exact symbol membership")
            if (
                out.extension.inputs.features != f
                or out.extension.inputs.direction != i.direction
            ):
                raise ValueError("Extension feature/direction mismatch")
            if out.extension.bands != rules.extension:
                raise ValueError("Extension rule mismatch")
            sizing = out.sizing.inputs
            if (
                sizing.symbol,
                sizing.direction,
                sizing.session_date,
                sizing.action_session,
                sizing.proposal,
                sizing.wilder_atr14,
                sizing.regime,
                sizing.earnings,
            ) != (
                f.symbol,
                i.direction,
                t,
                i.action_session,
                i.sizing,
                f.wilder_atr14,
                out.regime,
                out.earnings,
            ):
                raise ValueError("Sizing evidence context mismatch")
            if out.earnings.coverage != i.event_coverage or sorted(
                (e.inputs for e in out.earnings.events),
                key=lambda e: (e.source or "", e.source_event_id),
            ) != sorted(i.events, key=lambda e: (e.source or "", e.source_event_id)):
                raise ValueError("Earnings source evidence mismatch")
            if (out.regime.session_date, out.regime.eligible_from_session) != (
                regime.inputs.session_date,
                regime.eligible_from_session,
            ):
                raise ValueError("Regime gate reference mismatch")
            if expected_regime_gate is None:
                expected_regime_gate = regime_gate(i)
            if out.regime != expected_regime_gate:
                raise ValueError("Regime gate contradicts referenced shared evidence")
            counts[out.decision.state] += 1
            records.append(
                SymbolRecordV1(
                    output=out,
                    display_name=record.display_name,
                    volume=record.volume,
                    volume_reason=record.volume_reason,
                )
            )
        if counts != self.funnel.model_dump():
            raise ValueError("Funnel contradicts canonical decisions")
        reader.finish()
        if (
            fingerprint(
                self.model_dump(
                    mode="json", exclude={"generated_at", "logical_fingerprint"}
                )
            )
            != self.logical_fingerprint
        ):
            raise ValueError("Snapshot logical fingerprint mismatch")
        self._objects = MappingProxyType(reader.decoded)
        self._records = tuple(records)
        return self

    @staticmethod
    def _setup_integrity(inputs, positions):
        s, t, symbol = (
            inputs.setups,
            inputs.features.session_date,
            inputs.features.symbol,
        )
        if (
            s.inputs.session_index != positions[t]
            or s.inputs.structure != inputs.structure
        ):
            raise ValueError("Setup embedded Structure/calendar mismatch")
        ma = next((m for m in s.inputs.averages if m.kind == "SMA50"), None)
        if ma is None or ma.value != inputs.features.sma50:
            raise ValueError("Setup SMA50 mismatch")
        ids = [e.instance.setup_id for e in s.setups]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate setup identity")
        for e in s.setups:
            i = e.instance
            if i.symbol != symbol or e.session_date != t:
                raise ValueError("Nested setup identity mismatch")
            for d, idx in (
                (i.detected_at, i.detected_index),
                (i.status_changed_at, i.status_changed_index),
                (i.trigger_date, i.trigger_index),
            ):
                if d is not None and (d > t or positions.get(d) != idx):
                    raise ValueError("Setup lifecycle calendar mismatch")
            for g in (i.birth_geometry, i.geometry, i.next_geometry):
                if g is not None and (
                    g.reference_as_of_session > t
                    or g.reference_as_of_session not in positions
                ):
                    raise ValueError("Setup geometry calendar mismatch")

    @property
    def records(self):
        return self._records

    @property
    def source(self):
        return self._objects[self.shared.source_ref]

    @property
    def rules(self):
        return self._objects[self.shared.rules_ref]

    @property
    def regime(self):
        return self._objects[self.shared.regime_ref]

    @property
    def groups(self):
        return tuple(self._objects[r] for r in self.shared.group_refs)

    @property
    def versions(self):
        return self.shared.versions

    @property
    def calendar(self):
        return self.shared.calendar


def materialize_v2(
    *,
    records,
    source,
    universe,
    leadership,
    regime,
    groups,
    rules,
    calendar,
    versions,
    **metadata,
):
    """Pure lossless projection; all canonical model fields enter the typed graph."""
    builder = EvidenceBuilder()
    refs = {
        "source_ref": builder.add(source),
        "universe_ref": builder.add(universe),
        "leadership_ref": builder.add(leadership) if leadership is not None else None,
        "regime_ref": builder.add(regime),
        "rules_ref": builder.add(rules),
        "group_refs": tuple(
            builder.add(g)
            for g in sorted(groups, key=lambda g: (g.group_type, g.group_id))
        ),
    }
    shared_cache = dict(builder.objects)
    pending = []
    counts = {k: 0 for k in ("NONE", "WATCH", "TRADE", "ACT")}
    for r in records:
        counts[r.output.decision.state] += 1
        pending.append(
            {
                "symbol": r.output.decision.symbol,
                "direction": r.output.decision.direction,
                "display_name": r.display_name,
                "volume": r.volume,
                "volume_reason": r.volume_reason,
                "output_ref": builder.add(r.output),
            }
        )
        # Retain common input identities but release per-row input objects. A
        # streaming producer need not hold thousands of expanded V1 outputs.
        builder.objects = dict(shared_cache)
    addresses, evidence = builder.finish()
    refs = {
        k: (
            tuple(addresses[x] for x in v)
            if isinstance(v, tuple)
            else addresses[v]
            if v is not None
            else None
        )
        for k, v in refs.items()
    }
    shared = SharedContextV2(**refs, calendar=calendar, versions=versions)
    context_id = context_digest(shared, evidence)
    rows = tuple(
        CompactRecordV2(
            **{**r, "output_ref": addresses[r["output_ref"]]}, context_ref=context_id
        )
        for r in sorted(pending, key=lambda r: (r["symbol"], r["direction"]))
    )
    metadata.setdefault("funnel", FunnelV1(**counts))
    values = dict(
        metadata,
        shared=shared,
        context_id=context_id,
        record_index=rows,
        evidence=evidence,
    )
    draft = WorkstationSnapshotV2.model_construct(
        **values, logical_fingerprint="0" * 64
    )
    values["logical_fingerprint"] = fingerprint(
        draft.model_dump(mode="json", exclude={"generated_at", "logical_fingerprint"})
    )
    return WorkstationSnapshotV2.model_validate(values)


def sizing_input(snapshot, symbol, direction, proposal):
    """Exact-key adapter; never borrows another direction's evidence."""
    record = next(
        (
            r
            for r in snapshot.records
            if (r.output.decision.symbol, r.output.decision.direction)
            == (symbol, direction)
        ),
        None,
    )
    if record is None:
        raise ValueError("SIZER_DIRECTION_UNAVAILABLE")
    out = record.output
    return SizingInputV1(
        symbol=symbol,
        direction=direction,
        session_date=snapshot.as_of_session,
        action_session=snapshot.action_session,
        proposal=proposal,
        wilder_atr14=out.inputs.features.wilder_atr14,
        regime=out.regime,
        earnings=out.earnings,
    )
