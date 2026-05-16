"""Scheme status — thin service wrapper over the repository."""

from typing import Optional

from src.model.scheme_config import SchemeConfig
from src.repository import scheme_config_repository


def get_scheme_status(scheme_id: str) -> Optional[SchemeConfig]:
    return scheme_config_repository.get_scheme_config(scheme_id)
