"""AuthRateStats — pre-seeded historical authorization rate for a scheme + card profile."""

from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class AuthRateStats:
    scheme_id: str
    bin_bucket: str
    mcc: str
    currency: str
    amount_bucket: str
    auth_rate_7d: float
    auth_rate_30d: float
    sample_count: int
    decline_breakdown: Dict[str, float] = field(default_factory=dict)
