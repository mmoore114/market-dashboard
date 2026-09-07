"""Pure opt-in adapters. Caller owns loading and point-in-time attestation."""
import hashlib
import json

import pandas as pd

from market_dashboard.aperture.leadership_contracts import (
    GroupMemberV1, GroupMembershipV1, GroupType, ResearchUniverseV1,
    SetupStrengthContextV1, StrengthContextV1,
)
from market_dashboard.data.security_identity import ReferenceTicker

DISPOSITION_FINGERPRINT = 'a53c27e79f7e540a8dc135c7eb4e3f50d1f4198595729f24271819ebc405da35'


def exact_disposition(config):
    """Validate caller-loaded canonical v1 identities; never use its crosswalks."""
    keys = ('version','source_as_of_date','NON_SECURITY_MARKET_SERIES','DEEPVUE_BREADTH_INDICATOR')
    content = {k:config[k] for k in keys}
    digest = hashlib.sha256(json.dumps(content,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if digest != DISPOSITION_FINGERPRINT:
        raise ValueError('Unrecognized exact versioned non-security disposition')
    return {symbol:category for category in keys[2:] for symbol in content[category]}


def identity_member(symbol, group_id, boundary, disposition):
    reference = ReferenceTicker(symbol)
    if symbol in disposition:
        return GroupMemberV1(group_id=group_id,source_symbol=symbol,market_data_symbol=None,
            identity_reason=disposition[symbol],non_security=True)
    conversion = boundary.convert(reference)
    return GroupMemberV1(group_id=group_id,source_symbol=symbol,
        market_data_symbol=conversion.symbol.value if conversion.symbol else None,identity_reason=conversion.reason)


def deepvue_membership(frame, *, provenance, group_type, boundary, disposition_config, catalog=None):
    """Return snapshot plus every-source-row identity audit (including unclassified)."""
    group_type = GroupType(group_type)
    if group_type not in (GroupType.SUB_INDUSTRY,GroupType.THEME):
        raise ValueError('Deepvue does not supply parent sector/industry membership')
    disposition = exact_disposition(disposition_config)
    column = 'sub_industry' if group_type==GroupType.SUB_INDUSTRY else 'theme'
    required = {'source_as_of_date','ticker',column}
    if not required<=set(frame.columns):
        raise ValueError('Missing Deepvue membership columns')
    if any(pd.Timestamp(d).date()!=provenance.source_as_of_date for d in frame.source_as_of_date):
        raise ValueError('Mixed or incorrect Deepvue source dates')
    keys = ['ticker'] if group_type==GroupType.SUB_INDUSTRY else ['ticker',column]
    if frame.duplicated(keys).any():
        raise ValueError('Duplicate Deepvue source membership')
    members, audit = [], []
    for row in frame.to_dict('records'):
        label = row[column]
        classified = not pd.isna(label) and isinstance(label,str) and bool(label.strip())
        member = identity_member(row['ticker'],label if classified else '__UNCLASSIFIED_SOURCE_ROW__',boundary,disposition)
        audit.append(member)
        if classified:
            members.append(member)
    groups = set(m.group_id for m in members)
    if catalog is not None:
        if not {'source_as_of_date',column}<=set(catalog.columns) or catalog[column].duplicated().any():
            raise ValueError('Invalid dated group catalog')
        if any(pd.Timestamp(d).date()!=provenance.source_as_of_date for d in catalog.source_as_of_date):
            raise ValueError('Incorrect catalog source date')
        groups = set(catalog[column])
    snapshot = GroupMembershipV1(provenance=provenance,group_type=group_type,group_ids=tuple(sorted(groups)),
        members=tuple(sorted(members,key=lambda m:(m.group_id,m.source_symbol))),identity_version=boundary.version,
        disposition_version=disposition_config['version'])
    return snapshot, tuple(audit)


def research_universe(decisions, *, provenance, policy_version):
    """Existing SymbolDecisionSnapshotV1 rows; select research, never trade, flag."""
    tickers = [d.ticker for d in decisions]
    if len(tickers)!=len(set(tickers)):
        raise ValueError('Duplicate universe decision')
    if any(d.as_of_date!=provenance.source_as_of_date for d in decisions):
        raise ValueError('Universe decisions do not match dated provenance')
    if any(d.versions.universe_policy_version!=policy_version or d.freshness.is_stale for d in decisions):
        raise ValueError('Stale universe decision or inconsistent policy version')
    return research_memberships({d.ticker:d.universes for d in decisions},provenance=provenance,policy_version=policy_version)


def research_memberships(memberships, *, provenance, policy_version):
    """Existing UniverseMemberships with explicit caller-attested dated provenance."""
    return ResearchUniverseV1(provenance=provenance,policy_version=policy_version,
        symbols=tuple(sorted(symbol for symbol,m in memberships.items() if m.equity_research.eligible)))


def engine_context(*, symbol, session, source, structure=None, setup=None, legacy=None):
    """Unavailable/replay-blocked engine context stays missing, never fabricated."""
    expected = {k:getattr(source,k) for k in ('data_vendor','dataset_id','price_basis','dividend_treatment','volume_convention')}
    for evidence in (structure,setup):
        if evidence is not None:
            inputs = evidence.inputs
            if inputs.symbol!=symbol or inputs.session_date!=session or inputs.source.model_dump()!=expected:
                raise ValueError('Context identity, date or source mismatch')
    state = structure.state if structure is not None and structure.error is None else None
    setups = None
    if setup is not None:
        active = tuple(s for s in setup.setups if s.instance.status in ('FORMING','NEAR_TRIGGER','TRIGGERED'))
        if not setup.errors and all(s.evaluated and not s.instance.replay_required for s in active):
            setups = tuple(SetupStrengthContextV1(family=s.instance.family,status=s.instance.status) for s in active)
    return StrengthContextV1(legacy=legacy,structure_state=state,setups=setups)
