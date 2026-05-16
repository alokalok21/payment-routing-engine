"""DynamoDB access for Scheme_Config."""

from typing import Optional

from src.config.dynamodb_config import get_dynamodb_resource, SCHEME_CONFIG_TABLE_NAME
from src.model.scheme_config import SchemeConfig


def get_scheme_config(scheme_id: str) -> Optional[SchemeConfig]:
    table = get_dynamodb_resource().Table(SCHEME_CONFIG_TABLE_NAME)
    response = table.get_item(Key={"scheme_id": scheme_id})
    item = response.get("Item")
    if not item:
        return None
    return SchemeConfig(
        scheme_id=item["scheme_id"],
        display_name=item["display_name"],
        enabled=bool(item["enabled"]),
    )
