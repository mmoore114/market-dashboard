"""Explicit boundary between reference identities and market-data symbols."""
from dataclasses import dataclass

import pandas as pd

IDENTITY_VERSION = 'provider-ticker-exact-case-v1'
COMPATIBILITY_VERSION = 'reference-to-market-data-v2-exact-precedence'
# This registry is an audited migration gate, not an operator override. Add new
# unsafe reference readers here until their boundary tests and migration pass.
UNSAFE_REFERENCE_READERS = ()


def exact_ticker(value):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError('Provider ticker must be a nonblank exact string without surrounding whitespace')
    return value


@dataclass(frozen=True)
class ReferenceTicker:
    value: str

    def __post_init__(self):
        exact_ticker(self.value)


@dataclass(frozen=True)
class MarketDataSymbol:
    value: str

    def __post_init__(self):
        exact_ticker(self.value)
        if self.value != self.value.upper():
            raise ValueError('MarketDataSymbol requires uppercase; implicit reference conversion prohibited')


@dataclass(frozen=True)
class Conversion:
    reference: ReferenceTicker
    symbol: MarketDataSymbol | None
    reason: str


@dataclass(frozen=True)
class ReferenceResolution:
    reference: ReferenceTicker | None
    reason: str
    diagnostic_candidates: tuple[str, ...] = ()


def case_collision_groups(tickers):
    """Non-unique diagnostic buckets, never keys or automatic joins."""
    groups = {}
    for ticker in tickers:
        groups.setdefault(ticker.casefold(), set()).add(ticker)
    return {alias: sorted(values) for alias, values in sorted(groups.items()) if len(values) > 1}


class CompatibilityBoundary:
    """Conversion requires the complete dated reference identity set."""
    version = COMPATIBILITY_VERSION

    def __init__(self, references):
        references = list(references)
        if any(not isinstance(t, ReferenceTicker) for t in references):
            raise TypeError('ReferenceTicker values required')
        self.tickers = frozenset(t.value for t in references)
        if len(self.tickers) != len(references):
            raise ValueError('Duplicate exact reference identity')
        self.ambiguous = case_collision_groups(self.tickers)

    def convert(self, reference):
        if not isinstance(reference, ReferenceTicker):
            raise TypeError('Explicit ReferenceTicker required')
        ticker = reference.value
        if ticker not in self.tickers:
            return Conversion(reference, None, 'REFERENCE_NOT_IN_SNAPSHOT')
        if ticker != ticker.upper():
            return Conversion(reference, None, 'MIXED_CASE_REFERENCE_ONLY')
        return Conversion(reference, MarketDataSymbol(ticker), 'COMPATIBLE')

    def resolve_reference(self, requested):
        """Exact identity first; non-exact casefold candidates never resolve.

        Exact mixed-case lookup is valid reference resolution, not permission
        to convert that reference into a market-data symbol.
        """
        value = requested.value if isinstance(requested, MarketDataSymbol) else exact_ticker(requested)
        if value in self.tickers:
            return ReferenceResolution(ReferenceTicker(value), 'EXACT_REFERENCE_MATCH')
        candidates = tuple(sorted(t for t in self.tickers if t.casefold() == value.casefold()))
        return ReferenceResolution(None, 'AMBIGUOUS_NO_EXACT_IDENTITY', candidates)


def compatibility_projection(frame):
    """Return eligible market-data rows and an audit row for EVERY reference.

    Input must be one complete dated reference snapshot, before type/universe
    filtering. The original frame and exact identities are never changed.
    """
    if 'snapshot_date' in frame and frame.snapshot_date.nunique() > 1:
        raise ValueError('Projection requires one dated snapshot')
    refs = [ReferenceTicker(t) for t in frame.ticker]
    boundary = CompatibilityBoundary(refs)
    converted = [boundary.convert(t) for t in refs]
    audit = pd.DataFrame({
        'reference_ticker': [c.reference.value for c in converted],
        'market_data_symbol': [c.symbol.value if c.symbol else None for c in converted],
        'reason': [c.reason for c in converted],
        'compatibility_version': [COMPATIBILITY_VERSION] * len(converted),
    })
    if 'security_type' in frame:
        audit['security_type'] = frame.security_type.to_numpy()
    compatible = frame.loc[[c.symbol is not None for c in converted]].copy()
    # The values are identical, but this assignment makes the typed conversion
    # explicit rather than letting a reference ticker cross domains implicitly.
    compatible['ticker'] = [c.symbol.value for c in converted if c.symbol is not None]
    return compatible, audit


def publication_blockers(tickers):
    blockers = list(UNSAFE_REFERENCE_READERS)
    boundary = CompatibilityBoundary([ReferenceTicker(t) for t in tickers])
    for ticker in boundary.tickers:
        converted = boundary.convert(ReferenceTicker(ticker))
        if ticker == ticker.upper():
            if converted.symbol != MarketDataSymbol(ticker) or boundary.resolve_reference(converted.symbol).reference != ReferenceTicker(ticker):
                blockers.append('Exact uppercase round-trip conversion failed')
        elif converted.symbol is not None or not converted.reason:
            blockers.append('Mixed-case exclusion contract failed')
    return blockers
