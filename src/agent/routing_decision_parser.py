"""Parse the agent's final text into a RoutingDecision dataclass.

The agent is instructed to emit strict JSON with no markdown. We tolerate
stray code fences in case the model still wraps the answer, then validate
required keys and convert into typed dataclasses.
"""

import json
import re
from typing import Any, Dict

from src.model.routing_decision import FallbackEntry, RoutingDecision, SchemeScore

_REQUIRED_KEYS = (
    "selected_scheme",
    "confidence",
    "rationale",
    "fallback_chain",
    "score_breakdown",
)


def _strip_markdown_fence(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def parse(raw: str) -> RoutingDecision:
    text = _strip_markdown_fence(raw)
    try:
        data: Dict[str, Any] = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Agent did not emit valid JSON: {e}\nRaw text:\n{raw[:500]}") from e

    missing = [k for k in _REQUIRED_KEYS if k not in data]
    if missing:
        raise ValueError(f"Agent output missing required keys: {missing}")

    fallback_chain = [
        FallbackEntry(scheme=str(item["scheme"]), reason=str(item["reason"]))
        for item in data["fallback_chain"]
    ]

    score_breakdown: Dict[str, SchemeScore] = {}
    for scheme_id, scores in data["score_breakdown"].items():
        score_breakdown[scheme_id] = SchemeScore(
            auth_rate=float(scores["auth_rate"]),
            estimated_interchange_pct=float(scores["estimated_interchange_pct"]),
            score=float(scores["score"]),
            weight_auth=float(scores["weight_auth"]),
            weight_ic=float(scores["weight_ic"]),
        )

    return RoutingDecision(
        selected_scheme=str(data["selected_scheme"]),
        confidence=float(data["confidence"]),
        rationale=str(data["rationale"]),
        fallback_chain=fallback_chain,
        score_breakdown=score_breakdown,
    )
