"""Routes a Bedrock toolUse block to the appropriate service function.

The dispatcher converts the service's result (a dataclass instance) into
a JSON-serializable dict for the Bedrock toolResult content block. If the
service returns None (no data), an error dict is returned so the agent
can adapt — typically by excluding the scheme from scoring.
"""

import logging
from dataclasses import asdict
from typing import Any, Dict

from src.service import (
    auth_rate_stats_service,
    bin_lookup_service,
    interchange_estimation_service,
    scheme_status_service,
)

LOG = logging.getLogger(__name__)


def dispatch(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    LOG.info("Dispatching tool %s with input %s", tool_name, tool_input)

    if tool_name == "lookup_bin":
        result = bin_lookup_service.lookup_bin(tool_input["bin"])
        if result is None:
            return {"error": f"No BIN_Table entry for {tool_input['bin']}"}
        return asdict(result)

    if tool_name == "get_scheme_status":
        result = scheme_status_service.get_scheme_status(tool_input["scheme_id"])
        if result is None:
            return {"error": f"Scheme {tool_input['scheme_id']} not found in Scheme_Config"}
        return asdict(result)

    if tool_name == "get_scheme_auth_stats":
        result = auth_rate_stats_service.get_auth_rate_stats(
            scheme_id=tool_input["scheme_id"],
            bin_bucket=tool_input["bin_bucket"],
            mcc=tool_input["mcc"],
            currency=tool_input["currency"],
            amount_bucket=tool_input["amount_bucket"],
        )
        if result is None:
            return {
                "error": (
                    f"No auth_rate_stats for "
                    f"{tool_input['scheme_id']}#{tool_input['bin_bucket']} / "
                    f"{tool_input['mcc']}#{tool_input['currency']}#{tool_input['amount_bucket']}"
                )
            }
        return asdict(result)

    if tool_name == "estimate_interchange":
        result = interchange_estimation_service.estimate_interchange(
            scheme_id=tool_input["scheme_id"],
            card_type=tool_input["card_type"],
            card_product=tool_input["card_product"],
            mcc=tool_input["mcc"],
            amount=float(tool_input["amount"]),
            merchant_country=tool_input["merchant_country"],
            card_country=tool_input["card_country"],
        )
        return asdict(result)

    return {"error": f"Unknown tool: {tool_name}"}
