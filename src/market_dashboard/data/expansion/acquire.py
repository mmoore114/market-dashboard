"""Explicit-plan, resumable acquisition from the existing Massive provider.

Receipts reserve attempts before HTTP. Only allowlisted data survives the HTTP
boundary; credentials, URLs with query strings and error bodies are never logged.
"""

import gzip
import hashlib
import json
import math
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote

import httpx
import pandas as pd

from market_dashboard.data.current_sources import normalized_page
from market_dashboard.workstation.refresh.operations import digest

from .plan import write_json


class AcquisitionError(ValueError):
    pass


def grouped_rows(payload, session, allowed):
    if payload.get("adjusted") is not True or payload.get("next_url"):
        raise AcquisitionError("EXPLICIT_COMPLETE_SPLIT_ADJUSTED_RESPONSE_REQUIRED")
    items = payload.get("results")
    if not isinstance(items, list) or len(items) > 50000:
        raise AcquisitionError("GROUPED_RESPONSE_BOUNDS")
    rows, seen = [], set()
    for item in items:
        symbol = item.get("T")
        if symbol in seen:
            raise AcquisitionError("DUPLICATE_PROVIDER_IDENTITY")
        seen.add(symbol)
        if symbol not in allowed:
            continue
        day = datetime.fromtimestamp(item["t"] / 1000, UTC).date().isoformat()
        if day != session:
            raise AcquisitionError("NON_SESSION_OBSERVATION")
        row = {"ticker": symbol, "date": day}
        for short, name in (
            ("o", "open"),
            ("h", "high"),
            ("l", "low"),
            ("c", "close"),
            ("v", "volume"),
            ("vw", "vwap"),
            ("n", "transactions"),
        ):
            row[name] = item.get(short)
        for name in ("open", "high", "low", "close", "volume"):
            value = row[name]
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
                or (name != "volume" and value == 0)
            ):
                raise AcquisitionError("INVALID_OHLCV")
        if (
            not row["low"]
            <= min(row["open"], row["close"])
            <= max(row["open"], row["close"])
            <= row["high"]
        ):
            raise AcquisitionError("INVALID_OHLC_RANGE")
        rows.append(row)
    return sorted(rows, key=lambda r: r["ticker"])


class Acquirer:
    def __init__(self, root, api_key, *, client=None):
        self.root = Path(root)
        self.plan = json.loads((self.root / "plan.json").read_text())
        if self.plan["schema_version"] != "universe-expansion-plan-v1":
            raise AcquisitionError("UNSUPPORTED_PLAN")
        for path, sha in self.plan["source_hashes"].items():
            if digest(path) != sha:
                raise AcquisitionError("PLANNED_SOURCE_CHANGED")
        self.plan_hash = digest(self.root / "plan.json")
        self.client = client or httpx.Client(timeout=45, follow_redirects=False)
        self.headers = {"Authorization": "Bearer " + api_key}
        self.lock = threading.Lock()
        self.next_request = 0.0
        self.stop = threading.Event()
        self.allowed = (
            {r["source_symbol"] for r in self.plan["candidates"]}
            | set(self.plan["required_benchmarks"])
            | set(self.plan["local_history"])
        )

    def close(self):
        self.client.close()

    def job(self, kind, key):
        if Path(key).name != key or key in (".", ".."):
            raise AcquisitionError("INVALID_JOB_PATH")
        if kind == "reference" and not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]*", key):
            raise AcquisitionError("INVALID_EXACT_SYMBOL")
        if kind == "grouped" and key not in self.plan["history_sessions"]:
            raise AcquisitionError("UNPLANNED_SESSION")
        if kind == "reference" and key not in self.plan["reference_candidates"]:
            raise AcquisitionError("UNPLANNED_IDENTITY")
        if kind == "splits" and key != "history-window":
            raise AcquisitionError("UNPLANNED_SPLIT_WINDOW")
        if kind not in ("grouped", "reference", "splits"):
            raise AcquisitionError("UNSUPPORTED_JOB")
        path = self.root / "acquisition" / kind / key
        path.mkdir(parents=True, exist_ok=True)
        receipt_path = path / "receipt.json"
        page = path / "data.json.gz"
        receipt = (
            json.loads(receipt_path.read_text())
            if receipt_path.exists()
            else {
                "plan_sha256": self.plan_hash,
                "kind": kind,
                "key": key,
                "attempts": [],
            }
        )
        if receipt["plan_sha256"] != self.plan_hash:
            raise AcquisitionError("ACQUISITION_PLAN_CHANGED")
        if receipt.get("complete"):
            if digest(page) != receipt["sha256"]:
                raise AcquisitionError("ACQUISITION_HASH_MISMATCH")
            return json.loads(gzip.decompress(page.read_bytes()))
        daily = self.plan.get("authorization") == "PUBLISHED_COVERAGE_DAILY_INCREMENT"
        today = datetime.now(UTC).date().isoformat()
        attempted = (
            sum(a["started_at"][:10] == today for a in receipt["attempts"])
            if daily
            else len(receipt["attempts"])
        )
        for _ in range(attempted, self.plan["acquisition_bounds"]["attempts_per_job"]):
            if self.stop.is_set():
                raise AcquisitionError("BATCH_STOPPED")
            if (
                shutil.disk_usage(self.root).free
                < self.plan["acquisition_bounds"]["storage_reserve_bytes"]
            ):
                self.stop.set()
                raise AcquisitionError("DISK_RESERVE_REQUIRED")
            with self.lock:
                delay = self.next_request - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                self.next_request = (
                    time.monotonic()
                    + 1 / self.plan["acquisition_bounds"]["requests_per_second"]
                )
            attempt = {
                "started_at": datetime.now(UTC).isoformat(),
                "outcome": "RESERVED",
            }
            receipt["attempts"].append(attempt)
            write_json(receipt_path, receipt)
            if kind == "grouped":
                url = f"https://api.massive.com/v2/aggs/grouped/locale/us/market/stocks/{key}"
                params = {"adjusted": "true", "include_otc": "false"}
            elif kind == "splits":
                url = "https://api.massive.com/stocks/v1/splits"
                params = {
                    "execution_date.gte": self.plan["history_sessions"][0],
                    "execution_date.lte": self.plan["market_session"],
                    "limit": 5000,
                    "sort": "execution_date.asc",
                }
            else:
                url = f"https://api.massive.com/v3/reference/tickers/{quote(key, safe='')}"
                params = {}
            try:
                with self.client.stream(
                    "GET", url, params=params, headers=self.headers
                ) as response:
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > self.plan["acquisition_bounds"]["response_bytes_max"]:
                            raise AcquisitionError("RESPONSE_BYTES_CAP")
                        chunks.append(chunk)
                    raw = b"".join(chunks)
                    status = response.status_code
                    attempt["http_status"] = status
                    if status in (401, 403):
                        self.stop.set()
                        raise AcquisitionError("PROVIDER_AUTHORIZATION_REQUIRED")
                    if status == 429 or status >= 500:
                        header = response.headers.get("Retry-After", "15")
                        try:
                            retry = max(1, int(header))
                        except ValueError:
                            try:
                                retry_at = parsedate_to_datetime(header)
                                retry = max(
                                    1,
                                    math.ceil(
                                        (retry_at - datetime.now(UTC)).total_seconds()
                                    ),
                                )
                            except (TypeError, ValueError):
                                self.stop.set()
                                raise AcquisitionError(
                                    "PROVIDER_RETRY_AFTER_INVALID"
                                ) from None
                        if retry > 300:
                            self.stop.set()
                            raise AcquisitionError(
                                "PROVIDER_RETRY_AFTER_EXCEEDS_BATCH_BOUND"
                            )
                        with self.lock:
                            self.next_request = max(
                                self.next_request, time.monotonic() + retry
                            )
                        raise AcquisitionError("PROVIDER_RETRYABLE")
                    if status == 404 and kind == "reference":
                        result = {"rows": [], "status": "REFERENCE_NOT_FOUND"}
                    elif status != 200:
                        raise AcquisitionError("PROVIDER_HTTP_REFUSED")
                    elif kind == "splits":
                        payload = json.loads(raw)
                        if (
                            payload.get("next_url")
                            or not isinstance(payload.get("results"), list)
                            or len(payload["results"]) > 5000
                        ):
                            raise AcquisitionError("SPLIT_WINDOW_PAGINATION_REQUIRED")
                        rows = []
                        for item in payload["results"]:
                            if item.get("ticker") not in self.allowed:
                                continue
                            if (
                                not self.plan["history_sessions"][0]
                                <= item.get("execution_date", "")
                                <= self.plan["market_session"]
                            ):
                                raise AcquisitionError("SPLIT_DATE_OUTSIDE_PLAN")
                            for field in ("split_from", "split_to"):
                                v = item.get(field)
                                if (
                                    isinstance(v, bool)
                                    or not isinstance(v, (float, int))
                                    or not math.isfinite(v)
                                    or v <= 0
                                ):
                                    raise AcquisitionError("INVALID_SPLIT_RATIO")
                            rows.append(
                                {
                                    k: item.get(k)
                                    for k in (
                                        "ticker",
                                        "execution_date",
                                        "split_from",
                                        "split_to",
                                        "adjustment_type",
                                        "historical_adjustment_factor",
                                        "id",
                                    )
                                }
                            )
                        if len(
                            {(r["ticker"], r["execution_date"], r["id"]) for r in rows}
                        ) != len(rows):
                            raise AcquisitionError("DUPLICATE_SPLIT_EVENT")
                        result = {
                            "rows": rows,
                            "status": "VERIFIED",
                            "source_version": "massive-splits-v1",
                            "complete_window": True,
                        }
                    elif kind == "grouped":
                        result = {
                            "rows": grouped_rows(json.loads(raw), key, self.allowed),
                            "status": "VERIFIED",
                            "source_version": "massive-grouped-daily-split-adjusted-v1",
                            "adjustment_basis": "split_adjusted",
                            "dividend_adjusted": False,
                        }
                    else:
                        checked = httpx.Response(200, content=raw)
                        rows, source = normalized_page(
                            "reference", {"ticker": key}, checked, []
                        )
                        result = {"rows": rows, "source": source, "status": "VERIFIED"}
                if (
                    daily
                    and kind == "grouped"
                    and {r["ticker"] for r in result["rows"]} != self.allowed
                ):
                    raise AcquisitionError("PUBLISHED_SYMBOL_COMPLETED_BAR_MISSING")
                if (
                    daily
                    and kind == "reference"
                    and (
                        len(result["rows"]) != 1
                        or any(
                            result["rows"][0].get(f) is None
                            for f in ("active", "type", "locale", "primary_exchange")
                        )
                    )
                ):
                    raise AcquisitionError("PUBLISHED_SYMBOL_CURRENT_IDENTITY_MISSING")
                result["retrieved_at"] = datetime.now(UTC).isoformat()
                payload = gzip.compress(
                    json.dumps(result, sort_keys=True).encode(), mtime=0
                )
                from market_dashboard.workstation.refresh.operations import (
                    atomic_replace,
                )

                atomic_replace(page, payload)
                attempt["outcome"] = "COMPLETE"
                receipt.update(
                    complete=True,
                    sha256=hashlib.sha256(payload).hexdigest(),
                    rows=len(result["rows"]),
                )
                write_json(receipt_path, receipt)
                return result
            except (
                httpx.HTTPError,
                AcquisitionError,
                ValueError,
                KeyError,
                TypeError,
            ) as exc:
                attempt["outcome"] = (
                    str(exc)
                    if isinstance(exc, AcquisitionError)
                    else type(exc).__name__
                )
                write_json(receipt_path, receipt)
                if (
                    self.stop.is_set()
                    or isinstance(exc, AcquisitionError)
                    and str(exc) != "PROVIDER_RETRYABLE"
                ):
                    raise AcquisitionError(attempt["outcome"]) from None
        raise AcquisitionError("JOB_ATTEMPT_BUDGET_EXHAUSTED")

    def batch(self, kind, keys):
        keys = sorted(set(keys))
        result = {"kind": kind, "requested": len(keys), "complete": 0, "failures": {}}

        def one(key):
            try:
                self.job(kind, key)
                return key, None
            except AcquisitionError as exc:
                return key, str(exc)

        with ThreadPoolExecutor(
            max_workers=self.plan["acquisition_bounds"]["workers"]
        ) as pool:
            for key, error in pool.map(one, keys):
                if error:
                    result["failures"][key] = error
                else:
                    result["complete"] += 1
                if (result["complete"] + len(result["failures"])) % 100 == 0:
                    print(
                        json.dumps(
                            {
                                "kind": kind,
                                "complete": result["complete"],
                                "failed": len(result["failures"]),
                            }
                        ),
                        flush=True,
                    )
        write_json(self.root / f"{kind}-acquisition-summary.json", result)
        return result


def verify_overlap(root, grouped):
    plan = json.loads((Path(root) / "plan.json").read_text())
    current = {r["ticker"]: r for r in grouped["rows"]}
    changed, missing, checked = [], [], 0
    for symbol, artifact in plan["local_history"].items():
        if digest(artifact["path"]) != artifact["sha256"]:
            raise AcquisitionError("RETAINED_HISTORY_CHANGED")
        frame = pd.read_parquet(artifact["path"])
        row = frame[
            pd.to_datetime(frame.date).dt.date.astype(str) == plan["market_session"]
        ]
        if row.empty:
            continue
        if symbol not in current:
            missing.append(symbol)
        elif any(
            float(row.iloc[0][f]) != float(current[symbol][f])
            for f in ("open", "high", "low", "close", "volume")
        ):
            changed.append(symbol)
        else:
            checked += 1
    receipt = {
        "checked": checked,
        "changed": changed,
        "missing": missing,
        "session": plan["market_session"],
    }
    write_json(Path(root) / "overlap-check.json", receipt)
    if changed or missing:
        raise AcquisitionError("GROUPED_RETAINED_OVERLAP_MISMATCH")
    return receipt
