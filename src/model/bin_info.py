"""BinInfo — BIN lookup result (eligible schemes, card profile, dual-brand flag)."""

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class BinInfo:
    bin_prefix: str
    eligible_schemes: List[str]
    card_type: str
    card_product: str
    issuer_country: str
    issuer_bank: str
    dual_brand: bool
    domestic_scheme: Optional[str] = None
