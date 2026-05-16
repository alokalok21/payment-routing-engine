"""DynamoDB access for Auth_Rate_Stats.

Composite key:
    scheme_bin_bucket  (PK)  e.g., "VISA#4761"
    mcc_currency_amount (SK) e.g., "5411#EUR#50-200"
"""

from typing import Optional

from src.config.dynamodb_config import get_dynamodb_resource, AUTH_RATE_STATS_TABLE_NAME
from src.model.auth_rate_stats import AuthRateStats


def get_auth_rate_stats(
    scheme_id: str,
    bin_bucket: str,
    mcc: str,
    currency: str,
    amount_bucket: str,
) -> Optional[AuthRateStats]:
    table = get_dynamodb_resource().Table(AUTH_RATE_STATS_TABLE_NAME)
    pk = f"{scheme_id}#{bin_bucket}"
    sk = f"{mcc}#{currency}#{amount_bucket}"
    response = table.get_item(Key={
        "scheme_bin_bucket": pk,
        "mcc_currency_amount": sk,
    })
    item = response.get("Item")
    if not item:
        return None
    return AuthRateStats(
        scheme_id=scheme_id,
        bin_bucket=bin_bucket,
        mcc=mcc,
        currency=currency,
        amount_bucket=amount_bucket,
        auth_rate_7d=float(item["auth_rate_7d"]),
        auth_rate_30d=float(item["auth_rate_30d"]),
        sample_count=int(item["sample_count"]),
        decline_breakdown={k: float(v) for k, v in item.get("decline_breakdown", {}).items()},
    )
