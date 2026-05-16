"""RoutingDecision — final explainable AI output."""

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class FallbackEntry:
    scheme: str
    reason: str


@dataclass(frozen=True)
class SchemeScore:
    auth_rate: float
    estimated_interchange_pct: float
    score: float
    weight_auth: float
    weight_ic: float


@dataclass(frozen=True)
class RoutingDecision:
    selected_scheme: str
    confidence: float
    rationale: str
    fallback_chain: List[FallbackEntry]
    score_breakdown: Dict[str, SchemeScore]
