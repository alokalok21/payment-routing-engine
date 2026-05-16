"""Auth rate stats — thin service wrapper over the repository."""

from typing import Optional

from src.model.auth_rate_stats import AuthRateStats
from src.repository import auth_rate_stats_repository


def get_auth_rate_stats(
    scheme_id: str,
    bin_bucket: str,
    mcc: str,
    currency: str,
    amount_bucket: str,
) -> Optional[AuthRateStats]:
    return auth_rate_stats_repository.get_auth_rate_stats(
        scheme_id, bin_bucket, mcc, currency, amount_bucket
    )
