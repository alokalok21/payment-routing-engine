"""SchemeConfig — scheme enablement record (simplified per academic scope)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SchemeConfig:
    scheme_id: str
    display_name: str
    enabled: bool
