"""Local single-user workstation API. No provider clients or materialization."""

import os
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
from market_dashboard.workstation import projections
from market_dashboard.workstation.fixtures import build_fixture
from market_dashboard.workstation.models import (
    BriefV1,
    ErrorFieldV1,
    ErrorV1,
    HealthV1,
    RulesViewV1,
    SizerRequestV1,
    SizerResponseV1,
    SymbolDetailV1,
    TapeV1,
)
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
                fixture = build_fixture(rules, scenario)
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
        return SymbolDetailV1(
            meta=store.meta(), records=exact_records(symbol, store.require())
        )

    @app.post("/api/v1/sizer", response_model=SizerResponseV1)
    def sizer(body: SizerRequestV1):
        snapshot = store.require()
        rows = exact_records(body.symbol, snapshot)
        record = next(
            (r for r in rows if r.output.decision.direction == body.direction), rows[0]
        )
        original = record.output.sizing.inputs
        proposal = SizingProposalV1(
            account_equity=body.account_equity,
            available_buying_power=body.available_buying_power,
            entry=body.entry,
            stop=body.stop,
        )
        inputs = original.model_copy(
            update={"proposal": proposal, "direction": body.direction}
        )
        return SizerResponseV1(
            meta=store.meta(),
            result=decision_components.size_idea(inputs, snapshot.rules),
        )

    @app.get("/api/v1/rules", response_model=RulesViewV1)
    def rules():
        return projections.rules_view(store.require(), store.meta())

    return app
