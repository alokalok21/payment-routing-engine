"""Tests for the Bedrock ReAct loop using a scripted fake client.

The fake client replays a canned sequence of Converse responses, simulating
a 5-step ReAct: lookup_bin → 2x get_scheme_status → 2x get_scheme_auth_stats
→ 2x estimate_interchange → final JSON. This exercises the loop logic without
needing live Bedrock or live DynamoDB.
"""

import json
from typing import Any, Dict, List

import pytest

from src.agent import bedrock_routing_agent
from src.model.transaction_context import TransactionContext


class _FakeBedrockClient:
    def __init__(self, scripted_responses: List[Dict[str, Any]]):
        self._responses = scripted_responses
        self._call_count = 0
        self.calls: List[Dict[str, Any]] = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        if self._call_count >= len(self._responses):
            raise RuntimeError("Fake client out of scripted responses")
        resp = self._responses[self._call_count]
        self._call_count += 1
        return resp


def _tool_use(tool_use_id: str, name: str, input_payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"toolUse": {
                    "toolUseId": tool_use_id, "name": name, "input": input_payload,
                }}],
            }
        },
        "stopReason": "tool_use",
    }


def _final_json(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": json.dumps(payload)}],
            }
        },
        "stopReason": "end_turn",
    }


def test_react_loop_converges(mocked_dynamodb, local_onnx_env, monkeypatch):
    final_payload = {
        "selected_scheme": "CB",
        "confidence": 0.89,
        "rationale": "Test rationale",
        "fallback_chain": [{"scheme": "VISA", "reason": "Second highest."}],
        "score_breakdown": {
            "CB":   {"auth_rate": 0.948, "estimated_interchange_pct": 0.244, "score": 0.567, "weight_auth": 0.6, "weight_ic": 0.4},
            "VISA": {"auth_rate": 0.941, "estimated_interchange_pct": 0.428, "score": 0.563, "weight_auth": 0.6, "weight_ic": 0.4},
        },
    }
    scripted = [
        _tool_use("t1", "lookup_bin", {"bin": "476173"}),
        _tool_use("t2", "get_scheme_status", {"scheme_id": "CB"}),
        _tool_use("t3", "get_scheme_status", {"scheme_id": "VISA"}),
        _tool_use("t4", "get_scheme_auth_stats", {"scheme_id": "CB", "bin_bucket": "4761", "mcc": "5411", "currency": "EUR", "amount_bucket": "50-200"}),
        _tool_use("t5", "get_scheme_auth_stats", {"scheme_id": "VISA", "bin_bucket": "4761", "mcc": "5411", "currency": "EUR", "amount_bucket": "50-200"}),
        _tool_use("t6", "estimate_interchange", {"scheme_id": "CB", "card_type": "CREDIT", "card_product": "CLASSIC", "mcc": "5411", "amount": 150.0, "merchant_country": "FR", "card_country": "FR"}),
        _tool_use("t7", "estimate_interchange", {"scheme_id": "VISA", "card_type": "CREDIT", "card_product": "CLASSIC", "mcc": "5411", "amount": 150.0, "merchant_country": "FR", "card_country": "FR"}),
        _final_json(final_payload),
    ]
    fake = _FakeBedrockClient(scripted)
    monkeypatch.setattr(
        bedrock_routing_agent, "get_bedrock_client", lambda: fake
    )

    ctx = TransactionContext(
        transaction_id="txn-test-001", bin="476173", last4="9999",
        card_type="CREDIT", amount=150.0, currency="EUR", mcc="5411",
        merchant_country="FR", card_country="FR",
    )
    decision = bedrock_routing_agent.run(ctx)

    assert decision.selected_scheme == "CB"
    assert len(fake.calls) == 8
    assert fake.calls[0]["modelId"]


def test_react_loop_blows_up_on_runaway(monkeypatch):
    # Always returns tool_use — never ends the conversation.
    forever = _tool_use("tx", "lookup_bin", {"bin": "476173"})
    fake = _FakeBedrockClient([forever] * 50)
    monkeypatch.setattr(bedrock_routing_agent, "get_bedrock_client", lambda: fake)

    # Stub the dispatcher to avoid hitting moto since we don't use the fixture here.
    monkeypatch.setattr(
        bedrock_routing_agent, "dispatch", lambda name, inp: {"stub": True}
    )

    ctx = TransactionContext(
        transaction_id="t", bin="476173", last4="9999", card_type="CREDIT",
        amount=1.0, currency="EUR", mcc="5411", merchant_country="FR", card_country="FR",
    )
    with pytest.raises(RuntimeError, match="did not converge"):
        bedrock_routing_agent.run(ctx)
