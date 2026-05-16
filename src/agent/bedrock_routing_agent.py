"""Bedrock Converse-API ReAct loop for payment scheme routing.

Flow per invocation:
    1. Send the transaction context + system prompt + tool specs to Bedrock.
    2. If the model returns toolUse blocks, dispatch them, append the
       toolResults to the message history, and call Bedrock again.
    3. When the model stops with end_turn, parse its final text into a
       RoutingDecision and return.

Hard cap of MAX_ITERATIONS protects against runaway loops. A typical
dual-brand decision converges in 4-5 iterations.
"""

import json
import logging
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List

from src.agent.agent_tool_dispatcher import dispatch
from src.agent.routing_decision_parser import parse as parse_decision
from src.config.bedrock_config import MODEL_ID, TOOL_SPECS, get_bedrock_client
from src.model.routing_decision import RoutingDecision
from src.model.transaction_context import TransactionContext

LOG = logging.getLogger(__name__)

MAX_ITERATIONS = 10
SYSTEM_PROMPT_FILE = (
    Path(__file__).parent.parent.parent / "resources" / "agent-system-prompt.txt"
)

_system_prompt_cache: str = ""


def _load_system_prompt() -> str:
    global _system_prompt_cache
    if not _system_prompt_cache:
        with open(SYSTEM_PROMPT_FILE) as f:
            _system_prompt_cache = f.read()
    return _system_prompt_cache


def _to_json_safe(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_json_safe(v) for v in obj]
    return obj


def _build_initial_user_message(ctx: TransactionContext) -> str:
    payload = {
        "transaction_id":   ctx.transaction_id,
        "bin":              ctx.bin,
        "last4":            ctx.last4,
        "card_type":        ctx.card_type,
        "amount":           ctx.amount,
        "currency":         ctx.currency,
        "mcc":              ctx.mcc,
        "merchant_country": ctx.merchant_country,
        "card_country":     ctx.card_country,
    }
    return (
        "Route this card transaction to the optimal payment scheme. "
        "Follow the decision process from your instructions.\n\n"
        f"Transaction:\n{json.dumps(payload, indent=2)}\n\n"
        "Derived context (already computed for you):\n"
        f"  bin_bucket:    {ctx.bin_bucket}\n"
        f"  amount_bucket: {ctx.amount_bucket}\n"
        f"  cross_border:  {ctx.cross_border}\n"
    )


def _extract_tool_uses(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [b["toolUse"] for b in message.get("content", []) if "toolUse" in b]


def _extract_text(message: Dict[str, Any]) -> str:
    return "\n".join(b["text"] for b in message.get("content", []) if "text" in b).strip()


def run(ctx: TransactionContext) -> RoutingDecision:
    client = get_bedrock_client()
    messages: List[Dict[str, Any]] = [
        {"role": "user", "content": [{"text": _build_initial_user_message(ctx)}]}
    ]
    system = [{"text": _load_system_prompt()}]

    for iteration in range(1, MAX_ITERATIONS + 1):
        LOG.info("Bedrock iteration %d", iteration)
        response = client.converse(
            modelId=MODEL_ID,
            messages=messages,
            system=system,
            toolConfig={"tools": TOOL_SPECS},
            inferenceConfig={"maxTokens": 4096, "temperature": 0.0},
        )

        output_message = response["output"]["message"]
        stop_reason = response["stopReason"]
        messages.append(output_message)

        if stop_reason == "tool_use":
            tool_uses = _extract_tool_uses(output_message)
            if not tool_uses:
                raise RuntimeError("stopReason=tool_use but no toolUse blocks found")
            tool_result_blocks = []
            for tu in tool_uses:
                LOG.info("  → tool %s(%s)", tu["name"], tu["input"])
                result = dispatch(tu["name"], tu["input"])
                tool_result_blocks.append({
                    "toolResult": {
                        "toolUseId": tu["toolUseId"],
                        "content": [{"json": _to_json_safe(result)}],
                    }
                })
            messages.append({"role": "user", "content": tool_result_blocks})
            continue

        if stop_reason in ("end_turn", "stop_sequence"):
            final_text = _extract_text(output_message)
            return parse_decision(final_text)

        raise RuntimeError(f"Unexpected Bedrock stopReason: {stop_reason}")

    raise RuntimeError(f"Agent did not converge within {MAX_ITERATIONS} iterations")
