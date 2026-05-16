"""Tests for routing_decision_parser — pure offline, no AWS dependencies."""

import json

import pytest

from src.agent.routing_decision_parser import parse


def _valid_payload():
    return {
        "selected_scheme": "CB",
        "confidence": 0.89,
        "rationale": "CB wins on lower interchange (0.244% vs 0.428%).",
        "fallback_chain": [
            {"scheme": "VISA", "reason": "Second highest score; strong international auth."}
        ],
        "score_breakdown": {
            "CB":   {"auth_rate": 0.948, "estimated_interchange_pct": 0.244, "score": 0.566, "weight_auth": 0.6, "weight_ic": 0.4},
            "VISA": {"auth_rate": 0.941, "estimated_interchange_pct": 0.428, "score": 0.563, "weight_auth": 0.6, "weight_ic": 0.4},
        },
    }


def test_parses_valid_json():
    d = parse(json.dumps(_valid_payload()))
    assert d.selected_scheme == "CB"
    assert d.confidence == pytest.approx(0.89)
    assert len(d.fallback_chain) == 1
    assert d.fallback_chain[0].scheme == "VISA"
    assert set(d.score_breakdown) == {"CB", "VISA"}
    assert d.score_breakdown["CB"].auth_rate == pytest.approx(0.948)


def test_strips_markdown_code_fence():
    payload = "```json\n" + json.dumps(_valid_payload()) + "\n```"
    d = parse(payload)
    assert d.selected_scheme == "CB"


def test_rejects_invalid_json():
    with pytest.raises(ValueError, match="valid JSON"):
        parse("this is not json")


def test_rejects_missing_keys():
    payload = _valid_payload()
    del payload["fallback_chain"]
    with pytest.raises(ValueError, match="missing required keys"):
        parse(json.dumps(payload))
