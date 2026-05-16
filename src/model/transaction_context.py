"""TransactionContext — input payload to the routing agent."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TransactionContext:
    transaction_id: str
    bin: str
    last4: str
    card_type: str
    amount: float
    currency: str
    mcc: str
    merchant_country: str
    card_country: Optional[str] = None

    @property
    def bin_bucket(self) -> str:
        return self.bin[:4]

    @property
    def amount_bucket(self) -> str:
        if self.amount < 50:
            return "0-50"
        if self.amount < 200:
            return "50-200"
        if self.amount < 1000:
            return "200-1000"
        return "1000+"

    @property
    def cross_border(self) -> bool:
        if self.card_country is None:
            return False
        return self.merchant_country != self.card_country
