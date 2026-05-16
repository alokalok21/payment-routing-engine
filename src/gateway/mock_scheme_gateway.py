"""Mock payment-scheme gateway — simulates the authorization response.

The academic contribution of this project is the routing decision, not real
scheme connectivity. This gateway returns APPROVED unless the scheme has been
manually disabled in Scheme_Config — in which case the demo flow shouldn't
have selected it anyway, but we treat the call as DECLINED as a safety net.
"""

from src.service import scheme_status_service


def simulate_auth(scheme_id: str) -> str:
    config = scheme_status_service.get_scheme_status(scheme_id)
    if config is None or not config.enabled:
        return "DECLINED"
    return "APPROVED"
