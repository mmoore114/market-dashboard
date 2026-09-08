"""Explicit operator reuse of verified captures; publication is separate from status."""

import argparse
import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from market_dashboard.aperture.contracts import ContractModel
from market_dashboard.workstation.materialization.bootstrap import verify_hashes
from market_dashboard.workstation.materialization.contracts import GroupScheduleV1

from .operations import atomic_replace, digest, exclusive_lock


class AgeLimitV1(ContractModel):
    max_age_days: int = Field(gt=1, le=366)
    warn_before_days: int = Field(ge=1)

    @model_validator(mode="after")
    def warning(self):
        if self.warn_before_days >= self.max_age_days:
            raise ValueError("WARNING_MUST_PRECEDE_EXPIRY")
        return self


class CaptureV1(ContractModel):
    role: Literal["hierarchy", "themes"]
    workspace: str
    capture_date: date
    published_at: datetime
    registered_at: datetime
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    schedule_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def clocks(self):
        if any(
            d.utcoffset() is None for d in (self.published_at, self.registered_at)
        ) or not (
            self.capture_date <= self.published_at.date()
            and self.published_at <= self.registered_at
        ):
            raise ValueError("INVALID_CAPTURE_REGISTRATION_CLOCKS")
        return self


class MembershipPolicyV1(ContractModel):
    schema_version: Literal["membership-reuse-policy-v1"] = "membership-reuse-policy-v1"
    scope: Literal["CURRENT_COHORT_AT_E"] = "CURRENT_COHORT_AT_E"
    authority: Literal["OPERATOR_APPROVED_REUSE_NOT_PROVIDER_RECONFIRMATION"] = (
        "OPERATOR_APPROVED_REUSE_NOT_PROVIDER_RECONFIRMATION"
    )
    authorized_at: datetime
    hierarchy: AgeLimitV1 = AgeLimitV1(max_age_days=14, warn_before_days=3)
    themes: AgeLimitV1 = AgeLimitV1(max_age_days=7, warn_before_days=2)
    captures: tuple[CaptureV1, ...]

    @model_validator(mode="after")
    def clocks(self):
        if self.authorized_at.utcoffset() is None or any(
            c.registered_at > self.authorized_at for c in self.captures
        ):
            raise ValueError("INVALID_POLICY_AUTHORIZATION_CLOCKS")
        if {c.role for c in self.captures} != {"hierarchy", "themes"}:
            raise ValueError("BOTH_CAPTURE_ROLES_REQUIRED")
        keys = [(c.role, c.capture_date) for c in self.captures]
        if len(keys) != len(set(keys)):
            raise ValueError("AMBIGUOUS_SAME_DATE_CAPTURE")
        return self


def policy_path(config):
    return Path(
        config.get(
            "membership_policy", Path(config["workspace"]) / "membership-policy.json"
        )
    )


def read_publication(workspace, role):
    root = Path(workspace)
    receipt_path = root / "publication-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    verify_hashes(receipt["files"])
    name = "taxonomy" if role == "hierarchy" else "themes"
    path = root / f"{name}-schedule.json"
    if receipt["files"].get(str(path)) != digest(path):
        raise ValueError("CAPTURE_SCHEDULE_HASH_MISMATCH")
    schedule = GroupScheduleV1.model_validate_json(path.read_bytes())
    allowed = (
        {"THEME"}
        if role == "themes"
        else {"SECTOR", "GROUP", "INDUSTRY", "SUB_INDUSTRY"}
    )
    if any(g.group_type not in allowed for g in schedule.snapshots):
        raise ValueError("CAPTURE_ROLE_MISMATCH")
    dates = {g.provenance.source_as_of_date for g in schedule.snapshots}
    if len(dates) != 1 or not schedule.snapshots:
        raise ValueError("EXACT_CAPTURE_DATE_REQUIRED")
    if any(
        type(g.provenance).__name__ != "DatedProvenanceV1" for g in schedule.snapshots
    ):
        raise ValueError("ORIGINAL_CAPTURE_SCHEDULE_REQUIRED")
    return (
        schedule,
        dates.pop(),
        datetime.fromisoformat(receipt["published_at"]),
        receipt_path,
        path,
    )


def publish_policy(
    config, *, source_workspace=None, hierarchy=None, themes=None, now=None
):
    """Operator command only. Never called by refresh, status, API or timer."""
    now = now or datetime.now(UTC)
    root = Path(config["workspace"])
    root.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(root):
        path = policy_path(config)
        previous = (
            MembershipPolicyV1.model_validate_json(path.read_bytes())
            if path.exists()
            else None
        )
        captures = list(previous.captures) if previous else []
        workspace = str(Path(source_workspace or config["group_workspace"]).resolve())
        for role in ("hierarchy", "themes"):
            _, capture_date, published, receipt_path, schedule_path = read_publication(
                workspace, role
            )
            matching = [
                c for c in captures if (c.role, c.capture_date) == (role, capture_date)
            ]
            if matching:
                c = matching[0]
                if c.schedule_sha256 != digest(schedule_path):
                    raise ValueError("AMBIGUOUS_SAME_DATE_CAPTURE")
                continue  # Registration and capture clocks never reset.
            captures.append(
                CaptureV1(
                    role=role,
                    workspace=workspace,
                    capture_date=capture_date,
                    published_at=published,
                    registered_at=now,
                    receipt_sha256=digest(receipt_path),
                    schedule_sha256=digest(schedule_path),
                )
            )
        limits = {
            "hierarchy": hierarchy
            or (
                previous.hierarchy
                if previous
                else AgeLimitV1(max_age_days=14, warn_before_days=3)
            ),
            "themes": themes
            or (
                previous.themes
                if previous
                else AgeLimitV1(max_age_days=7, warn_before_days=2)
            ),
        }
        if (
            previous
            and tuple(captures) == previous.captures
            and all(getattr(previous, k) == v for k, v in limits.items())
        ):
            return {
                "state": "ALREADY_PUBLISHED",
                "path": str(path),
                "sha256": digest(path),
            }
        policy = MembershipPolicyV1(
            authorized_at=now, captures=tuple(captures), **limits
        )
        raw = policy.model_dump_json(indent=2).encode()
        backups = root / "membership-policy-backups"
        backups.mkdir(exist_ok=True)
        # Archive both predecessor and new authorization before switching the pointer.
        import hashlib

        for content in ([path.read_bytes()] if path.exists() else []) + [raw]:
            sha = hashlib.sha256(content).hexdigest()
            backup = backups / f"{sha}.json"
            if not backup.exists():
                atomic_replace(backup, content)
            if digest(backup) != sha:
                raise ValueError("POLICY_BACKUP_MISMATCH")
        atomic_replace(path, raw)
        if path.read_bytes() != raw:
            raise ValueError("POLICY_READBACK_MISMATCH")
        return {"state": "PUBLISHED", "path": str(path), "sha256": digest(path)}


def resolve_policy(config, now, window, *, require=True):
    """Read-only selection. New captures supersede prospectively at registration."""
    path = policy_path(config)
    policy = MembershipPolicyV1.model_validate_json(path.read_bytes())
    if now.utcoffset() is None or policy.authorized_at > now:
        raise ValueError("MEMBERSHIP_POLICY_NOT_YET_AUTHORIZED")
    selected = []
    for role in ("hierarchy", "themes"):
        eligible = [
            c for c in policy.captures if c.role == role and c.registered_at <= now
        ]
        if not eligible:
            raise ValueError(f"{role.upper()}_VERIFIED_CAPTURE_REQUIRED")
        capture = max(eligible, key=lambda c: c.capture_date)
        schedule, source_date, published, receipt, source = read_publication(
            capture.workspace, role
        )
        if (digest(receipt), digest(source), source_date, published) != (
            capture.receipt_sha256,
            capture.schedule_sha256,
            capture.capture_date,
            capture.published_at,
        ):
            raise ValueError(f"{role.upper()}_CAPTURE_PROVENANCE_CHANGED")
        limit = getattr(policy, role)
        expires = datetime.combine(
            source_date + timedelta(days=limit.max_age_days), time(), UTC
        )
        warning = expires - timedelta(days=limit.warn_before_days)
        age = (now.astimezone(UTC).date() - source_date).days
        action_valid = window["opening"] < expires and all(
            g.provenance.effective_session <= window["action"]
            for g in schedule.snapshots
        )
        state = (
            "EXPIRED"
            if now >= expires
            else (
                "ACTION_OUTSIDE_POLICY"
                if not action_valid
                else "REFRESH_DUE"
                if now >= warning
                else "REUSABLE"
            )
        )
        reason = (
            None
            if state in ("REUSABLE", "REFRESH_DUE")
            else (
                f"{role.upper()}_SOURCE_REFRESH_REQUIRED_CAPTURE_{source_date}_EXPIRES_{expires.date()}_ACTION_{window['action']}"
            )
        )
        if require and reason:
            raise ValueError(reason)
        selected.append(
            {
                "capture": capture,
                "schedule": schedule,
                "limit": limit,
                "status": {
                    "role": role,
                    "capture_date": str(source_date),
                    "age_days": age,
                    "reuse_status": state,
                    "expires_at": expires.isoformat(),
                    "warning_at": warning.isoformat(),
                    "max_age_days": limit.max_age_days,
                    "warn_before_days": limit.warn_before_days,
                    "original_valid_through": str(
                        min(g.provenance.valid_through for g in schedule.snapshots)
                    ),
                    "policy_sha256": digest(path),
                    "reason": reason,
                },
            }
        )
    return policy, selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--source-workspace", type=Path)
    parser.add_argument("--hierarchy-max-age-days", type=int)
    parser.add_argument("--hierarchy-warn-before-days", type=int)
    parser.add_argument("--themes-max-age-days", type=int)
    parser.add_argument("--themes-warn-before-days", type=int)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    limits = {}
    for role in ("hierarchy", "themes"):
        age, warning = (
            getattr(args, role + "_max_age_days"),
            getattr(args, role + "_warn_before_days"),
        )
        if (age is None) != (warning is None):
            parser.error(
                "Supply both maximum age and warning days for each changed role"
            )
        if age is not None:
            limits[role] = AgeLimitV1(max_age_days=age, warn_before_days=warning)
    print(
        json.dumps(
            publish_policy(config, source_workspace=args.source_workspace, **limits),
            indent=2,
        )
    )


def authorized_groups(config, now, window):
    """Bind policy and original schedules into newly materialized evidence only."""
    from market_dashboard.aperture.leadership_contracts import CurrentGroupProvenanceV3
    from market_dashboard.workstation.models import InputClockBindingV1

    policy, selected = resolve_policy(config, now, window)
    path = policy_path(config)
    policy_sha = digest(path)
    archive = (
        Path(config["workspace"]) / "membership-policy-backups" / f"{policy_sha}.json"
    )
    if not archive.exists() or digest(archive) != policy_sha:
        raise ValueError("VERIFIED_POLICY_ARCHIVE_REQUIRED")
    hashes = {str(archive): policy_sha}
    groups, bindings = [], []
    for item in selected:
        capture, schedule, limit = item["capture"], item["schedule"], item["limit"]
        root = Path(capture.workspace)
        receipt_path = root / "publication-receipt.json"
        receipt = json.loads(receipt_path.read_text())
        hashes.update(receipt["files"])
        hashes[str(receipt_path)] = capture.receipt_sha256
        for g in schedule.snapshots:
            p = CurrentGroupProvenanceV3.model_validate(
                g.provenance.model_dump()
                | {
                    "market_as_of_session": window["market"],
                    "evaluation_timestamp": now,
                    "action_session": window["action"],
                    "known_at": capture.published_at,
                    "reuse_policy_sha256": policy_sha,
                    "source_schedule_sha256": capture.schedule_sha256,
                    "reuse_authorized_at": policy.authorized_at,
                    "max_source_age_days": limit.max_age_days,
                    "warn_before_days": limit.warn_before_days,
                }
            )
            groups.append(g.model_copy(update={"provenance": p}))
        bindings.append(
            InputClockBindingV1(
                name=capture.role,
                role="decision_control",
                effective_date=schedule.snapshots[0].provenance.effective_session,
                available_at=capture.published_at,
                artifact_sha256=capture.schedule_sha256,
            )
        )
    bindings.append(
        InputClockBindingV1(
            name="membership_reuse_policy",
            role="decision_control",
            effective_date=policy.authorized_at.date(),
            available_at=policy.authorized_at,
            artifact_sha256=policy_sha,
        )
    )
    return GroupScheduleV1(snapshots=tuple(groups)), bindings, hashes


if __name__ == "__main__":
    main()
