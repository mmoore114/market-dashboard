"""Bounded current-foundation acquisition: immutable plan, receipts, staged pages.

No production writes, retries, pagination, redirects, identity substitution or
provider error/body logging. A failed workspace cannot be automatically resumed.
"""

import csv
import io
import json
import math
import os
import re
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import quote

import httpx

from market_dashboard.data.adjusted_authority import response_evidence
from market_dashboard.data.security_master_refresh import ROOT, safe_path
from market_dashboard.workstation.materialization.io import file_hash


def write_new(path, payload):
    """Durable no-replace publication for explicitly authorized local artifacts."""
    path = safe_path(path)
    descriptor, temporary = tempfile.mkstemp(prefix=".current-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.unlink(temporary)


CAPS = {"bars": (125, 25000), "reference": (110, 110), "spot": (2, 1000)}
FRED_SOURCE = {
    "version": "fred-vixcls-daily-close-v1",
    "series_id": "$VIX",
    "provider": "Federal Reserve Bank of St. Louis FRED",
    "dataset": "VIXCLS",
    "source": "Cboe Market Statistics",
    "frequency": "daily_close",
    "attribution": "Chicago Board Options Exchange, CBOE Volatility Index: VIX [VIXCLS], retrieved from FRED, Federal Reserve Bank of St. Louis.",
    "license": "Copyright Chicago Board Options Exchange; reprinted with permission by FRED. Source attribution required; no redistribution grant inferred.",
    "source_url": "https://fred.stlouisfed.org/series/VIXCLS",
}


def validate_plan(plan):
    if (
        set(plan) != {"kind", "jobs", "sessions", "source_hashes"}
        or plan["kind"] not in CAPS
    ):
        raise ValueError("INVALID_ACQUISITION_PLAN")
    kind = plan["kind"]
    jobs = plan["jobs"]
    sessions = plan["sessions"]
    if not jobs or len(jobs) > CAPS[kind][0] or sessions != sorted(set(sessions)):
        raise ValueError("INVALID_ACQUISITION_BOUNDS")
    if len({j["ticker"] for j in jobs}) != len(jobs):
        raise ValueError("DUPLICATE_REQUEST_IDENTITY")
    for job in jobs:
        if set(job) != {"ticker", "start", "end"}:
            raise ValueError("INVALID_JOB")
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]*", job["ticker"]):
            raise ValueError("INVALID_EXACT_SYMBOL")
        if (
            not date(2024, 1, 2)
            <= date.fromisoformat(job["start"])
            <= date.fromisoformat(job["end"])
        ):
            raise ValueError("INVALID_DATE_BOUNDS")
        if kind == "spot" and (job["ticker"] != "VIXCLS" or len(jobs) != 1):
            raise ValueError("INVALID_SPOT_IDENTITY")
    for d in sessions:
        date.fromisoformat(d)
    return plan


def request_spec(kind, job):
    symbol = quote(job["ticker"], safe="")
    if kind == "bars":
        return (
            f"https://api.massive.com/v2/aggs/ticker/{symbol}/range/1/day/{job['start']}/{job['end']}",
            {"adjusted": "true", "sort": "asc", "limit": 50000},
        )
    if kind == "reference":
        return f"https://api.massive.com/v3/reference/tickers/{symbol}", {}
    return "https://fred.stlouisfed.org/graph/fredgraph.csv", {
        "id": "VIXCLS",
        "cosd": job["start"],
        "coed": job["end"],
    }


def normalized_page(kind, job, response, sessions):
    if response.status_code != 200 or response.history:
        raise ValueError("HTTP_OR_REDIRECT_REFUSED")
    if kind == "spot":
        reader = csv.DictReader(io.StringIO(response.text))
        if reader.fieldnames != ["observation_date", "VIXCLS"]:
            raise ValueError("FRED_SCHEMA_MISMATCH")
        rows = []
        for item in reader:
            d = date.fromisoformat(item["observation_date"]).isoformat()
            v = None if item["VIXCLS"] in ("", ".") else float(item["VIXCLS"])
            if v is not None and (not math.isfinite(v) or v <= 0):
                raise ValueError("INVALID_SPOT_CLOSE")
            rows.append({"series_id": "$VIX", "date": d, "close": v})
        if len(rows) > CAPS[kind][1]:
            raise ValueError("RECORD_CAP")
        metadata = FRED_SOURCE
    else:
        payload = response.json()
        if payload.get("next_url"):
            raise ValueError("PAGINATION_REFUSED")
        if kind == "reference":
            item = payload.get("results", {})
            if not isinstance(item, dict) or item.get("ticker") != job["ticker"]:
                raise ValueError("REFERENCE_IDENTITY_MISMATCH")
            fields = (
                "ticker",
                "active",
                "market",
                "locale",
                "type",
                "primary_exchange",
                "market_cap",
                "share_class_shares_outstanding",
                "weighted_shares_outstanding",
                "list_date",
                "last_updated_utc",
            )
            rows = [{k: item.get(k) for k in fields}]
            cap = rows[0]["market_cap"]
            if cap is not None and (
                isinstance(cap, bool)
                or not isinstance(cap, (int, float))
                or not math.isfinite(cap)
                or cap < 0
            ):
                raise ValueError("INVALID_MARKET_CAP")
            return rows, {
                "source_version": "massive-ticker-details-current-v1",
                "market_cap_as_of": "UNKNOWN",
                "role": "decision_time_control",
            }
        if (
            payload.get("adjusted") is not True
            or payload.get("ticker") != job["ticker"]
        ):
            raise ValueError("EXPLICIT_ADJUSTED_IDENTITY_REQUIRED")
        values = payload.get("results")
        if not isinstance(values, list):
            raise ValueError("AGGREGATE_SCHEMA_MISMATCH")
        rows = []
        for item in values:
            d = datetime.fromtimestamp(item["t"] / 1000, UTC).date().isoformat()
            row = {
                "ticker": job["ticker"],
                "date": d,
                **{
                    target: item.get(source)
                    for source, target in (
                        ("o", "open"),
                        ("h", "high"),
                        ("l", "low"),
                        ("c", "close"),
                        ("v", "volume"),
                        ("vw", "vwap"),
                        ("n", "transactions"),
                    )
                },
            }
            for key in ("open", "high", "low", "close"):
                v = row[key]
                if (
                    isinstance(v, bool)
                    or not isinstance(v, (int, float))
                    or not math.isfinite(v)
                    or v <= 0
                ):
                    raise ValueError("INVALID_OHLC")
            if (
                not row["low"]
                <= min(row["open"], row["close"])
                <= max(row["open"], row["close"])
                <= row["high"]
            ):
                raise ValueError("INVALID_OHLC_RANGE")
            rows.append(row)
        metadata = response_evidence(
            job["ticker"], job["start"], job["end"], payload, rows
        ).model_dump(mode="json")
    dates = [r["date"] for r in rows]
    if dates != sorted(set(dates)) or any(
        not job["start"] <= d <= job["end"] for d in dates
    ):
        raise ValueError("SESSION_KEYS_OR_BOUNDS_INVALID")
    expected = [d for d in sessions if job["start"] <= d <= job["end"]]
    if kind == "bars" and dates != expected:
        raise ValueError("REQUESTED_SESSION_COVERAGE_INCOMPLETE")
    return rows, metadata


def fetch_staged(plan, workspace, *, api_key=None, client=None):
    validate_plan(plan)
    workspace = safe_path(workspace)
    if (
        workspace == ROOT
        or ROOT in workspace.parents
        or any(
            part in (".git", ".env", ".codex", ".agents")
            or "security-master" in part.lower()
            or "deepvue" in part.lower()
            for part in workspace.parts
        )
    ):
        raise ValueError("STAGING_OUTPUT_SCOPE_REFUSED")
    if workspace.exists():
        raise ValueError("ACQUISITION_WORKSPACE_EXISTS")
    for path, digest in plan["source_hashes"].items():
        if file_hash(Path(path)) != digest:
            raise ValueError("PLANNED_SOURCE_CHANGED")
    if plan["kind"] != "spot" and not api_key:
        raise ValueError("CREDENTIAL_UNAVAILABLE")
    workspace.mkdir(parents=True)

    def write(name, value):
        write_new(
            workspace / name,
            (json.dumps(value, sort_keys=True, indent=2) + "\n").encode(),
        )

    write("plan.json", plan)
    receipts = []
    count = 0
    owned = client is None
    if owned:
        client = httpx.Client(
            timeout=45, follow_redirects=False, transport=httpx.HTTPTransport(retries=0)
        )
    try:
        for i, job in enumerate(plan["jobs"]):
            # Persist reservation before the HTTP boundary; a crash still counts.
            request = {
                "attempt": i + 1,
                "kind": plan["kind"],
                "ticker": job["ticker"],
                "started_at": datetime.now(UTC).isoformat(),
                "status": "reserved",
            }
            write(f"attempt-{i + 1:03}.json", request)
            url, params = request_spec(plan["kind"], job)
            try:
                headers = (
                    {}
                    if plan["kind"] == "spot"
                    else {"Authorization": "Bearer " + api_key}
                )
                response = client.get(
                    url, params=params, headers=headers, follow_redirects=False
                )
                request["http_status"] = response.status_code
                rows, metadata = normalized_page(
                    plan["kind"], job, response, plan["sessions"]
                )
                if count + len(rows) > CAPS[plan["kind"]][1]:
                    raise ValueError("TOTAL_RECORD_CAP")
                count += len(rows)
                page = {
                    "rows": rows,
                    "source": metadata,
                    "retrieved_at": datetime.now(UTC).isoformat(),
                    "request": job,
                }
                name = f"page-{i + 1:03}.json"
                write(name, page)
                request.update(
                    status="complete",
                    rows=len(rows),
                    artifact=name,
                    sha256=file_hash(workspace / name),
                    finished_at=page["retrieved_at"],
                )
            except Exception as exc:  # noqa: BLE001 — sanitize provider/CLI diagnostics
                # Exception strings and response bodies may contain secrets or rows.
                request.update(
                    status="failed",
                    error_category=type(exc).__name__,
                    finished_at=datetime.now(UTC).isoformat(),
                )
                write(f"receipt-{i + 1:03}.json", request)
                receipts.append(request)
                break
            write(f"receipt-{i + 1:03}.json", request)
            receipts.append(request)
    finally:
        if owned:
            client.close()
    state = {
        "kind": plan["kind"],
        "attempts": len(receipts),
        "rows": count,
        "complete": len(receipts) == len(plan["jobs"])
        and all(r["status"] == "complete" for r in receipts),
        "receipts": receipts,
    }
    write("fetch.json", state)
    return state


def validate_staged(workspace):
    workspace = safe_path(workspace)
    plan = validate_plan(json.loads((workspace / "plan.json").read_text()))
    state = json.loads((workspace / "fetch.json").read_text())
    if not state["complete"] or state["attempts"] != len(plan["jobs"]):
        raise ValueError("FETCH_INCOMPLETE")
    if len(state["receipts"]) != len(plan["jobs"]):
        raise ValueError("RECEIPT_COUNT_MISMATCH")
    rows = []
    for i, (job, receipt) in enumerate(zip(plan["jobs"], state["receipts"])):
        if receipt["artifact"] != f"page-{i + 1:03}.json" or receipt[
            "sha256"
        ] != file_hash(workspace / receipt["artifact"]):
            raise ValueError("STAGED_PAGE_CHANGED")
        page = json.loads((workspace / receipt["artifact"]).read_text())
        if page["request"] != job or len(page["rows"]) != receipt["rows"]:
            raise ValueError("STAGED_RECEIPT_MISMATCH")
        if receipt.get("status") != "complete" or receipt.get("http_status") != 200:
            raise ValueError("INCOMPLETE_REQUEST_RECEIPT")
        if plan["kind"] == "bars":
            days = [r["date"] for r in page["rows"]]
            expected = [d for d in plan["sessions"] if job["start"] <= d <= job["end"]]
            if days != expected or any(
                r["ticker"] != job["ticker"] for r in page["rows"]
            ):
                raise ValueError("STAGED_SESSION_IDENTITY_MISMATCH")
            evidence = response_evidence(
                job["ticker"],
                job["start"],
                job["end"],
                {"ticker": job["ticker"], "adjusted": True},
                page["rows"],
            )
            if evidence.model_dump(mode="json") != page["source"]:
                raise ValueError("STAGED_BASIS_RECEIPT_MISMATCH")
        elif plan["kind"] == "reference":
            if len(page["rows"]) != 1 or page["rows"][0]["ticker"] != job["ticker"]:
                raise ValueError("STAGED_REFERENCE_IDENTITY_MISMATCH")
        else:
            days = [r["date"] for r in page["rows"]]
            if days != sorted(set(days)) or any(
                not job["start"] <= d <= job["end"] for d in days
            ):
                raise ValueError("STAGED_SPOT_DATES_INVALID")
            if any(r["series_id"] != "$VIX" for r in page["rows"]):
                raise ValueError("STAGED_SPOT_IDENTITY_INVALID")
        rows.extend(page["rows"])
    if len(rows) != state["rows"] or len(rows) > CAPS[plan["kind"]][1]:
        raise ValueError("STAGED_RECORD_CAP")
    return rows
