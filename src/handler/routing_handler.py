"""API Gateway Lambda entry point: orchestrates the routing flow.

    event ─► parse JSON body
          ─► build TransactionContext
          ─► BedrockRoutingAgent.run() → RoutingDecision
          ─► MockSchemeGateway.simulate_auth()
          ─► JSON response (200)

Validation errors return 400. Anything else returns 500 with a generic
error message; full details go to CloudWatch logs.
"""

import json
import logging
from dataclasses import asdict
from typing import Any, Dict

from src.agent import bedrock_routing_agent
from src.gateway import mock_scheme_gateway
from src.model.transaction_context import TransactionContext

LOG = logging.getLogger()
LOG.setLevel(logging.INFO)

_REQUIRED_FIELDS = (
    "transaction_id", "bin", "last4", "card_type",
    "amount", "currency", "mcc", "merchant_country",
)


def _parse_body(event: Dict[str, Any]) -> Dict[str, Any]:
    body = event.get("body")
    if body is None:
        raise ValueError("Missing request body")
    if isinstance(body, str):
        body = json.loads(body)
    return body


def _build_context(body: Dict[str, Any]) -> TransactionContext:
    missing = [f for f in _REQUIRED_FIELDS if f not in body]
    if missing:
        raise ValueError(f"Missing required fields: {missing}")
    return TransactionContext(
        transaction_id=str(body["transaction_id"]),
        bin=str(body["bin"]),
        last4=str(body["last4"]),
        card_type=str(body["card_type"]),
        amount=float(body["amount"]),
        currency=str(body["currency"]),
        mcc=str(body["mcc"]),
        merchant_country=str(body["merchant_country"]),
        card_country=str(body["card_country"]) if body.get("card_country") else None,
    )


def _response(status: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        body = _parse_body(event)
        ctx = _build_context(body)
    except (ValueError, json.JSONDecodeError) as e:
        LOG.warning("Bad request: %s", e)
        return _response(400, {"error": str(e)})

    try:
        decision = bedrock_routing_agent.run(ctx)
        auth_result = mock_scheme_gateway.simulate_auth(decision.selected_scheme)
        response_body = {
            "transaction_id": ctx.transaction_id,
            "selected_scheme": decision.selected_scheme,
            "confidence": decision.confidence,
            "rationale": decision.rationale,
            "fallback_chain": [asdict(f) for f in decision.fallback_chain],
            "score_breakdown": {k: asdict(v) for k, v in decision.score_breakdown.items()},
            "mock_auth_result": auth_result,
        }
        return _response(200, response_body)
    except Exception as e:
        LOG.exception("Routing failed")
        return _response(500, {"error": "Internal error during routing", "detail": str(e)})
