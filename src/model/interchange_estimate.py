"""InterchangeEstimate — ML model output for a scheme."""

from dataclasses import dataclass


@dataclass(frozen=True)
class InterchangeEstimate:
    scheme_id: str
    estimated_interchange_pct: float
    interchange_category: str
    confidence: float
    cross_border: bool
