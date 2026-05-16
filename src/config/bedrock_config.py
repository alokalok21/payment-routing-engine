"""Bedrock runtime client, model ID, and Converse-API tool specifications."""

import os
import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")

_client = None


def get_bedrock_client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=REGION)
    return _client


TOOL_SPECS = [
    {
        "toolSpec": {
            "name": "lookup_bin",
            "description": (
                "Look up a card BIN to determine eligible payment schemes, card type, "
                "card product, issuer country, dual-brand status, and the domestic "
                "scheme hint. Call this first for every transaction."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "bin": {
                            "type": "string",
                            "description": "6-8 digit BIN prefix from the card.",
                        }
                    },
                    "required": ["bin"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_scheme_status",
            "description": (
                "Check whether a payment scheme is currently enabled for routing. "
                "Disabled schemes must be excluded from scoring."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "scheme_id": {
                            "type": "string",
                            "description": "Scheme identifier: VISA | MASTERCARD | CB | DISCOVER | AMEX | UNIONPAY | MAESTRO",
                        }
                    },
                    "required": ["scheme_id"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_scheme_auth_stats",
            "description": (
                "Get pre-seeded historical authorization rates for a (scheme, BIN bucket, "
                "MCC, currency, amount bucket) profile. Use these to compare auth-rate "
                "expectations across schemes."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "scheme_id": {"type": "string"},
                        "bin_bucket": {
                            "type": "string",
                            "description": "First 4 digits of the BIN.",
                        },
                        "mcc": {"type": "string"},
                        "currency": {
                            "type": "string",
                            "description": "ISO 4217 currency code.",
                        },
                        "amount_bucket": {
                            "type": "string",
                            "enum": ["0-50", "50-200", "200-1000", "1000+"],
                        },
                    },
                    "required": [
                        "scheme_id",
                        "bin_bucket",
                        "mcc",
                        "currency",
                        "amount_bucket",
                    ],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "estimate_interchange",
            "description": (
                "Estimate the interchange rate (%) for routing the transaction on a "
                "specific scheme. Uses an XGBoost regression model. Result includes "
                "the category band and a cross_border flag."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "scheme_id": {"type": "string"},
                        "card_type": {
                            "type": "string",
                            "enum": ["CREDIT", "DEBIT", "PREPAID"],
                        },
                        "card_product": {
                            "type": "string",
                            "enum": ["CLASSIC", "GOLD", "PLATINUM", "INFINITE"],
                        },
                        "mcc": {"type": "string"},
                        "amount": {"type": "number"},
                        "merchant_country": {
                            "type": "string",
                            "description": "ISO 3166-1 alpha-2.",
                        },
                        "card_country": {
                            "type": "string",
                            "description": "ISO 3166-1 alpha-2 (issuer country).",
                        },
                    },
                    "required": [
                        "scheme_id",
                        "card_type",
                        "card_product",
                        "mcc",
                        "amount",
                        "merchant_country",
                        "card_country",
                    ],
                }
            },
        }
    },
]
