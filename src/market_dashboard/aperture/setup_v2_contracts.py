"""Explicit V2 inputs/output; reusable geometry/lifecycle facts retain their schemas."""

from typing import Literal

from market_dashboard.aperture.setup_contracts import SetupInputV1, SetupOutputV1
from market_dashboard.aperture.structure_v2 import StructureEvidenceV2


class SetupInputV2(SetupInputV1):
    schema_version: Literal["setup-input-v2"] = "setup-input-v2"
    feature_version: Literal["setup-features-v2"] = "setup-features-v2"
    structure: StructureEvidenceV2 | None = None
    tr5: float | None
    tr20: float | None
    median_atr20: float | None
    word_s20: float | None
    median_volume5: float | None
    median_volume20: float | None


class SetupOutputV2(SetupOutputV1):
    schema_version: Literal["setup-output-v2"] = "setup-output-v2"
    engine_version: Literal["setup-engine-v2"] = "setup-engine-v2"
    feature_version: Literal["setup-features-v2"] = "setup-features-v2"
    threshold_version: Literal["setup-thresholds-v2"] = "setup-thresholds-v2"
    inputs: SetupInputV2
