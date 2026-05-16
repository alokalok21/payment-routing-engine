"""DynamoDB access for BIN_Table — longest-prefix-match BIN lookup."""

from typing import Optional

from src.config.dynamodb_config import get_dynamodb_resource, BIN_TABLE_NAME
from src.model.bin_info import BinInfo


def lookup_bin(bin_value: str) -> Optional[BinInfo]:
    """Look up a BIN — tries 8, 7, 6 digit prefixes in order (longest-match-first).

    BINs in the table may be 6, 7, or 8 digits. This walks down to find a match.
    """
    table = get_dynamodb_resource().Table(BIN_TABLE_NAME)
    for prefix_len in (8, 7, 6):
        if len(bin_value) < prefix_len:
            continue
        prefix = bin_value[:prefix_len]
        response = table.get_item(Key={"bin_prefix": prefix})
        item = response.get("Item")
        if item:
            return BinInfo(
                bin_prefix=item["bin_prefix"],
                eligible_schemes=list(item["eligible_schemes"]),
                card_type=item["card_type"],
                card_product=item["card_product"],
                issuer_country=item["issuer_country"],
                issuer_bank=item["issuer_bank"],
                dual_brand=bool(item["dual_brand"]),
                domestic_scheme=item.get("domestic_scheme"),
            )
    return None
