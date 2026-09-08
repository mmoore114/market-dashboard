"""Local single-user workstation API. No provider clients or materialization."""

import os
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from market_dashboard.aperture import decision_components
from market_dashboard.aperture.decision_contracts import SizingProposalV1
from market_dashboard.aperture.rules import load_aperture_rules
from market_dashboard.data.security_identity import MarketDataSymbol
from market_dashboard.workstation import projections, research
from market_dashboard.workstation.detail_v2 import (
    EvidencePageV2,
    SymbolDetailV2,
    symbol_view,
)
from market_dashboard.workstation.fixtures import build_fixture, build_industry_fixture
from market_dashboard.workstation.models import (
    BriefV1,
    ErrorFieldV1,
    ErrorV1,
    GroupsViewV1,
    HealthV1,
    RulesViewV1,
    SizerRequestV1,
    SizerResponseV1,
    SymbolDetailV1,
    TapeV1,
)
from market_dashboard.workstation.refresh.report import membership_maintenance
from market_dashboard.workstation.snapshot_v2 import sizing_input
from market_dashboard.workstation.store import SnapshotStore, SnapshotUnavailable


class ApiError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message


def create_app(store=None):
    if store is None:
        mode = os.environ.get("APERTURE_MODE", "FIXTURE")
        fixture = None
        if mode == "FIXTURE":
            rules = load_aperture_rules(
                Path(__file__).resolve().parents[1] / "config/aperture_rules_v1.yaml"
            )
            scenario = os.environ.get("APERTURE_FIXTURE_SCENARIO", "GREEN")
            if scenario in ("GREEN", "YELLOW", "RED"):
                builder = (
                    build_industry_fixture
                    if os.environ.get("APERTURE_FIXTURE_POLICY") == "INDUSTRY"
                    else build_fixture
                )
                fixture = builder(rules, scenario)
        store = SnapshotStore(
            mode, path=os.environ.get("APERTURE_SNAPSHOT_PATH"), fixture=fixture
        )
    app = FastAPI(
        title="Aperture Workstation",
        version="workstation-api-v1",
        openapi_url="/api/v1/openapi.json",
        docs_url=None,
        redoc_url=None,
        responses={
            422: {"model": ErrorV1},
            404: {"model": ErrorV1},
            503: {"model": ErrorV1},
            500: {"model": ErrorV1},
        },
    )
    app.state.store = store
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    def error_response(status, code, message, fields=()):
        error = ErrorV1(
            mode=store.mode,
            mode_label="SYNTHETIC FIXTURE"
            if store.mode == "FIXTURE"
            else "LOCAL SNAPSHOT",
            code=code,
            message=message,
            fields=fields,
        )
        return JSONResponse(
            status_code=status,
            content=error.model_dump(mode="json"),
            headers={"Cache-Control": "no-store"},
        )

    @app.middleware("http")
    async def no_store(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(SnapshotUnavailable)
    async def unavailable(request: Request, exc: SnapshotUnavailable):
        return error_response(503, exc.code, exc.message)

    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError):
        return error_response(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return error_response(
            422,
            "INVALID_REQUEST",
            "Review the supplied fields.",
            tuple(
                ErrorFieldV1(
                    field=".".join(str(v) for v in e["loc"]),
                    message="Invalid or unsupported value.",
                )
                for e in exc.errors()
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error_response(
            exc.status_code,
            "ROUTE_NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR",
            "The requested operation is unavailable.",
        )

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        return error_response(
            500, "INTERNAL_ERROR", "The operation could not be completed safely."
        )

    def exact_records(symbol, snapshot):
        try:
            MarketDataSymbol(symbol)
        except ValueError:
            raise ApiError(
                422, "INVALID_SYMBOL", "Use an exact case-sensitive market-data symbol."
            ) from None
        records = tuple(
            r for r in snapshot.records if r.output.decision.symbol == symbol
        )
        if not records:
            raise ApiError(
                404,
                "SYMBOL_NOT_FOUND",
                "The exact symbol is absent from this snapshot.",
            )
        return records

    @app.get("/api/v1/health", response_model=HealthV1)
    def health():
        try:
            store.require()
            available = True
        except SnapshotUnavailable:
            available = False
        return HealthV1(meta=store.meta(), available=available)

    @app.get("/api/v1/brief", response_model=BriefV1)
    def brief():
        return projections.brief(store.require(), store.meta())

    @app.get("/api/v1/tape", response_model=TapeV1)
    def tape(
        page: int = Query(1, ge=1, le=100000),
        page_size: int = Query(25, ge=1, le=100),
        sort: Literal[
            "symbol",
            "price",
            "RS_comp",
            "RS_rotation",
            "rotation_delta",
            "extension_atr",
            "decision",
            "group_rank",
        ] = "symbol",
        order: Literal["asc", "desc"] = "asc",
        action: Literal["NONE", "WATCH", "TRADE", "ACT"] | None = None,
        structure: Literal["NEUTRAL", "EMERGING", "UPTREND", "DETERIORATING", "DECLINE"]
        | None = None,
        setup: Literal["EP", "CONTRACTION", "TREND_PULLBACK", "RANGE"] | None = None,
        min_rs_comp: float | None = Query(None, ge=0, le=100),
        min_rs_rotation: float | None = Query(None, ge=0, le=100),
        group: str | None = Query(None, min_length=1, max_length=160),
        veto: bool | None = None,
    ):
        snapshot = store.require()
        if group is not None and group not in {
            g.group_id for g in snapshot.groups if g.group_type == "SUB_INDUSTRY"
        }:
            raise ApiError(
                422, "INVALID_GROUP", "Choose a sub-industry present in this snapshot."
            )
        return projections.tape(
            snapshot,
            store.meta(),
            page=page,
            page_size=page_size,
            sort=sort,
            order=order,
            action=action,
            structure=structure,
            setup=setup,
            min_rs_comp=min_rs_comp,
            min_rs_rotation=min_rs_rotation,
            group=group,
            veto=veto,
        )

    @app.get("/api/v1/symbols/{symbol}", response_model=SymbolDetailV1)
    def symbol_detail(symbol: str):
        snapshot = store.require()
        records = exact_records(symbol, snapshot)
        if (
            snapshot.evaluation
            and snapshot.evaluation.bootstrap
            and snapshot.evaluation.bootstrap.version == "coverage-current-state-v1"
        ):
            raise ApiError(
                409,
                "NORMALIZED_SYMBOL_DETAIL_REQUIRED",
                "Expanded coverage uses /api/v2/symbols/{symbol}; complete shared evidence is available through /api/v2/evidence.",
            )
        return SymbolDetailV1(meta=store.meta(), records=records)

    @app.get("/api/v2/symbols/{symbol}", response_model=SymbolDetailV2)
    def symbol_detail_v2(symbol: str):
        snapshot = store.require()
        return symbol_view(snapshot, exact_records(symbol, snapshot), store.meta())

    @app.get("/api/v2/evidence", response_model=EvidencePageV2)
    def evidence_page(
        fingerprint: str,
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
    ):
        snapshot = store.require()
        if fingerprint != snapshot.logical_fingerprint:
            raise ApiError(
                409,
                "SNAPSHOT_CHANGED",
                "Request evidence from the same snapshot fingerprint.",
            )
        return EvidencePageV2(
            meta=store.meta(),
            offset=offset,
            total=len(snapshot.evidence),
            nodes=snapshot.evidence[offset : offset + limit],
        )

    @app.post("/api/v1/sizer", response_model=SizerResponseV1)
    def sizer(body: SizerRequestV1):
        snapshot = store.require()
        exact_records(body.symbol, snapshot)
        proposal = SizingProposalV1(
            account_equity=body.account_equity,
            available_buying_power=body.available_buying_power,
            entry=body.entry,
            stop=body.stop,
        )
        try:
            inputs = sizing_input(snapshot, body.symbol, body.direction, proposal)
        except ValueError:
            raise ApiError(
                422,
                "SIZER_DIRECTION_UNAVAILABLE",
                "No exact symbol/direction record exists in this snapshot.",
            ) from None
        return SizerResponseV1(
            meta=store.meta(),
            result=decision_components.size_idea(inputs, snapshot.rules),
        )

    @app.get("/api/v1/rules", response_model=RulesViewV1)
    def rules():
        return projections.rules_view(store.require(), store.meta())

    @app.get("/api/v2/research/health", response_model=research.ResearchHealthV1)
    def research_health():
        snapshot = store.require()
        missing = []
        if snapshot.regime.inputs.volatility.close is None:
            missing.append("VIX unavailable")
        if snapshot.regime.status == "UNKNOWN":
            missing.append("Market regime unconfirmed")
        if any(r.output.earnings.eligibility == "UNKNOWN" for r in snapshot.records):
            missing.append("Earnings coverage incomplete")
        if any(
            r.output.earnings.coverage_required_through is None
            for r in snapshot.records
        ):
            missing.append("Retained earnings calendar too short")
        return research.ResearchHealthV1(
            meta=store.meta(),
            missing=tuple(missing),
            risk_fraction=snapshot.rules.risk.risk_per_idea_fraction,
            regime_multiplier=getattr(
                snapshot.rules.risk.regime_multipliers,
                snapshot.regime.status.lower(),
                None,
            ),
            allowed_risk_fraction=(
                snapshot.rules.risk.risk_per_idea_fraction
                * getattr(
                    snapshot.rules.risk.regime_multipliers,
                    snapshot.regime.status.lower(),
                )
            )
            if snapshot.regime.status in ("GREEN", "YELLOW", "RED")
            else None,
            membership_maintenance=membership_maintenance(store, snapshot),
        )

    @app.get("/api/v2/research/tape", response_model=research.ResearchTapeV1)
    def research_tape(
        page: int = Query(1, ge=1),
        page_size: int = Query(25, ge=1, le=100),
        direction: Literal["LONG", "SHORT"] | None = None,
        action: Literal["NONE", "WATCH", "TRADE", "ACT"] | None = None,
        structure: Literal["NEUTRAL", "EMERGING", "UPTREND", "DETERIORATING", "DECLINE"]
        | None = None,
        setup: Literal["EP", "CONTRACTION", "TREND_PULLBACK", "RANGE"] | None = None,
        group: str | None = Query(None, max_length=512),
        min_rs_comp: float | None = Query(None, ge=0, le=100),
        min_rs_rotation: float | None = Query(None, ge=0, le=100),
        veto: bool | None = None,
        sort: Literal[
            "symbol", "price", "RS_comp", "RS_rotation", "decision"
        ] = "symbol",
        descending: bool = False,
    ):
        return research.tape_view(
            store.require(),
            store.meta(),
            page=page,
            page_size=page_size,
            direction=direction,
            action=action,
            structure=structure,
            setup=setup,
            group=group,
            min_rs_comp=min_rs_comp,
            min_rs_rotation=min_rs_rotation,
            veto=veto,
            sort=sort,
            descending=descending,
        )

    @app.get("/api/v2/research/brief", response_model=BriefV1)
    def research_brief():
        return projections.brief(store.require(), store.meta(), group_kind="INDUSTRY")

    @app.get("/api/v2/research/groups", response_model=research.ResearchGroupsV1)
    def research_groups(
        kind: Literal[
            "SECTOR", "GROUP", "INDUSTRY", "SUB_INDUSTRY", "THEME"
        ] = "INDUSTRY",
        include_unranked: bool = False,
        sort: Literal[
            "leadership_rank",
            "median_RS_comp",
            "median_RS_rotation",
            "median_rotation_delta",
            "valid_members",
            "watch_count",
            "name",
        ] = "leadership_rank",
        descending: bool = False,
        q: str = Query("", max_length=100),
        page: int = Query(1, ge=1),
        page_size: int = Query(25, ge=1, le=100),
    ):
        return research.groups_view(
            store.require(),
            store.meta(),
            kind=kind,
            include_unranked=include_unranked,
            sort=sort,
            descending=descending,
            q=q,
            page=page,
            page_size=page_size,
        )

    @app.get("/api/v2/research/members", response_model=research.ResearchMembersV1)
    def research_members(
        group_id: str = Query(..., max_length=512),
        kind: Literal[
            "SECTOR", "GROUP", "INDUSTRY", "SUB_INDUSTRY", "THEME"
        ] = "SUB_INDUSTRY",
        page: int = Query(1, ge=1),
        page_size: int = Query(25, ge=1, le=100),
    ):
        snapshot = store.require()
        group = next(
            (
                g
                for g in snapshot.groups
                if (g.group_type, g.group_id) == (kind, group_id)
            ),
            None,
        )
        if group is None:
            raise ApiError(
                404, "GROUP_NOT_FOUND", "Choose an exact published group identity."
            )
        records = {
            r.output.decision.symbol: r
            for r in snapshot.records
            if r.output.decision.direction == "LONG"
        }
        members = sorted(group.members, key=lambda m: m.source_symbol)
        return research.ResearchMembersV1(
            meta=store.meta(),
            total=len(members),
            page=page,
            pages=(len(members) + page_size - 1) // page_size,
            members=tuple(
                research.ResearchMemberV1(
                    symbol=m.source_symbol,
                    row=research.research_row(records[m.market_data_symbol])
                    if not m.non_security and m.market_data_symbol in records
                    else None,
                    reason=None
                    if not m.non_security and m.market_data_symbol in records
                    else "Outside calculated research coverage; " + m.identity_reason,
                )
                for m in members[(page - 1) * page_size : page * page_size]
            ),
        )

    @app.get(
        "/api/v2/research/symbols", response_model=tuple[research.SymbolSearchV1, ...]
    )
    def research_symbols(
        q: str = Query("", max_length=80), limit: int = Query(20, ge=1, le=50)
    ):
        snapshot = store.require()
        found = {}
        for r in snapshot.records:
            symbol = r.output.decision.symbol
            if q.casefold() in (symbol + " " + r.display_name).casefold():
                entry = found.setdefault(
                    symbol, {"symbol": symbol, "name": r.display_name, "directions": []}
                )
                entry["directions"].append(r.output.decision.direction)
        return tuple(research.SymbolSearchV1(**found[s]) for s in sorted(found)[:limit])

    @app.get("/api/v1/groups", response_model=GroupsViewV1)
    def groups():
        snapshot = store.require()
        return GroupsViewV1(
            meta=store.meta(),
            groups=snapshot.groups,
            membership_maintenance=membership_maintenance(store, snapshot),
            reasons=()
            if snapshot.groups
            else (
                decision_components.reason(
                    "GROUP_MEMBERSHIP_UNKNOWN",
                    "No published group membership evidence is available.",
                ),
            ),
        )

    @app.get("/api/v1/groups/{group_id}", response_model=GroupsViewV1)
    def group_detail(group_id: str):
        snapshot = store.require()
        selected = tuple(g for g in snapshot.groups if g.group_id == group_id)
        if not selected:
            raise ApiError(
                404, "GROUP_NOT_FOUND", "No published evidence for this exact group."
            )
        return GroupsViewV1(
            meta=store.meta(),
            groups=selected,
            reasons=(),
            membership_maintenance=membership_maintenance(store, snapshot),
        )

    @app.get("/api/v1/time-machine/{session}", response_model=ErrorV1)
    def time_machine(session: date):
        snapshot = store.require()
        bootstrap = snapshot.evaluation.bootstrap if snapshot.evaluation else None
        if bootstrap and session < bootstrap.action_session:
            raise ApiError(
                422,
                "UNKNOWN_BEFORE_BOOTSTRAP",
                "Current-cohort calculations are not historical membership or backtest evidence before "
                + str(bootstrap.action_session)
                + ".",
            )
        raise ApiError(
            404,
            "HISTORICAL_SNAPSHOT_UNAVAILABLE",
            "No historical snapshot is configured for this session.",
        )

    return app
